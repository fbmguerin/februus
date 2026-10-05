"""Messages between the scanner and the analyzer process.

One stream socket (Unix). Each message is a 4-byte length followed by a
JSON object of at most ``MAX_MESSAGE_BYTES``.

- Request (scanner -> analyzer): ``{"name": "<relative path>"}`` with
  exactly one file descriptor attached (SCM_RIGHTS): the file to analyze,
  opened by the scanner. The name is for information only.
- Answer (analyzer -> scanner):
  ``{"findings": [[module, code, detail], ...], "error": null | "text"}``,
  without any descriptor.

Both sides treat what they receive as untrusted: anything unexpected (no
descriptor, two descriptors, bad JSON, unknown key, too long) raises
``ProtocolError``, which ends as ``internal.error`` (red), never as
"no finding".
FR : chaque côté valide ce qu'il reçoit ; tout message inattendu est une
erreur (ROUGE), jamais « aucun constat ».
"""

import json
import os
import socket
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from februus.core.checks import ScannedFile

MAX_MESSAGE_BYTES = 64 * 1024
# Room to receive more descriptors than allowed, to see and refuse them.
_MAX_RECEIVED_FDS = 8
_HEADER = struct.Struct("!I")


@dataclass(frozen=True, slots=True)
class FileResult:
    """Findings of all analyzers for one file, or the error that occurred."""

    # (module name, finding code, detail) for each finding.
    findings: tuple[tuple[str, str, str], ...] = ()
    error: str | None = None


class ProtocolError(Exception):
    """A message is malformed, or the connection was closed in a message."""


def send_request(sock: socket.socket, name: str, fd: int) -> None:
    """Scanner side: ask for the analysis of the open file ``fd``."""
    _send(sock, {"name": name}, [fd])


def receive_request(sock: socket.socket) -> ScannedFile | None:
    """Analyzer side: the next file to analyze (the caller closes its
    descriptor), or None when the scanner closed the connection."""
    message = _receive(sock, None)
    if message is None:
        return None
    data, fds = message
    try:
        if len(fds) != 1:
            raise ProtocolError(f"expected one file descriptor, got {len(fds)}")
        if not isinstance(data, dict) or set(data) != {"name"}:
            raise ProtocolError("unexpected request keys")
        if not isinstance(data["name"], str):
            raise ProtocolError("the name must be a string")
    except ProtocolError:
        _close_all(fds)
        raise
    return ScannedFile(name=data["name"], fd=fds[0])


def send_answer(sock: socket.socket, result: FileResult) -> None:
    """Analyzer side: send the result of one file."""
    _send(sock, {"findings": [list(f) for f in result.findings], "error": result.error}, [])


def receive_answer(
    sock: socket.socket, wait: Callable[[], None] | None = None
) -> FileResult:
    """Scanner side: the result of the file just sent. ``wait`` is called
    before each read; it returns when data can be read, or raises (timeout,
    key removed)."""
    message = _receive(sock, wait)
    if message is None:
        raise ProtocolError("connection closed without an answer")
    data, fds = message
    if fds:
        _close_all(fds)
        raise ProtocolError("unexpected file descriptor in an answer")
    if not isinstance(data, dict) or set(data) != {"findings", "error"}:
        raise ProtocolError("unexpected answer keys")
    findings, error = data["findings"], data["error"]
    if error is not None and not isinstance(error, str):
        raise ProtocolError("the error must be a string or null")
    if not isinstance(findings, list):
        raise ProtocolError("the findings must be a list")
    for finding in findings:
        if (
            not isinstance(finding, list)
            or len(finding) != 3
            or not all(isinstance(part, str) for part in finding)
        ):
            raise ProtocolError("a finding must be [module, code, detail]")
    return FileResult(findings=tuple(tuple(f) for f in findings), error=error)


def _send(sock: socket.socket, data: dict[str, Any], fds: list[int]) -> None:
    payload = json.dumps(data).encode("ascii")
    if len(payload) > MAX_MESSAGE_BYTES:
        raise ProtocolError(f"message too long ({len(payload)} bytes)")
    message = _HEADER.pack(len(payload)) + payload
    # The descriptors travel as ancillary data with the first bytes.
    sent = socket.send_fds(sock, [message], fds) if fds else 0
    sock.sendall(message[sent:])


def _receive(
    sock: socket.socket, wait: Callable[[], None] | None
) -> tuple[Any, list[int]] | None:
    """One message and the descriptors that came with it. None if the
    connection was closed between two messages."""
    fds: list[int] = []
    try:
        header = _read_exactly(sock, _HEADER.size, fds, wait, eof_allowed=True)
        if header is None:
            if fds:
                raise ProtocolError("file descriptor without a message")
            return None
        (length,) = _HEADER.unpack(header)
        if length > MAX_MESSAGE_BYTES:
            raise ProtocolError(f"message too long ({length} bytes)")
        payload = _read_exactly(sock, length, fds, wait)
        try:
            data = json.loads(payload)
        except (ValueError, RecursionError) as exc:
            raise ProtocolError(f"invalid JSON: {exc}") from None
    except BaseException:
        _close_all(fds)
        raise
    return data, fds


def _read_exactly(
    sock: socket.socket,
    size: int,
    fds: list[int],
    wait: Callable[[], None] | None,
    eof_allowed: bool = False,
) -> bytes | None:
    """Read ``size`` bytes; descriptors received on the way go to ``fds``.
    None if the connection is closed before the first byte (and
    ``eof_allowed``)."""
    data = b""
    while len(data) < size:
        if wait is not None:
            wait()
        chunk, new_fds, flags, _ = socket.recv_fds(sock, size - len(data), _MAX_RECEIVED_FDS)
        fds += new_fds
        if flags & socket.MSG_CTRUNC:
            raise ProtocolError("too many file descriptors")
        if not chunk:
            if eof_allowed and not data:
                return None
            raise ProtocolError("connection closed in the middle of a message")
        data += chunk
    return data


def _close_all(fds: list[int]) -> None:
    for fd in fds:
        os.close(fd)
    fds.clear()
