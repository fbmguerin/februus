"""Analyzer ``clamav``: asks the ClamAV daemon (clamd) through its socket.

The descriptor of the file, opened by the scanner, is passed on to clamd
(FILDES command): neither this analyzer nor clamd needs read access to
the key, and there is no size limit of a stream. clamd only reads bytes.

clamd must run with the settings of ``deploy/clamav/clamd-februus.conf``
(AlertEncrypted, AlertExceedsMax): otherwise encrypted or oversized files
would be answered "OK".

Findings:
- ``clamav.detected``     a signature matched (detail: its name)
- ``archive.encrypted``   encrypted archive (Heuristics.Encrypted.*)
- ``pdf.encrypted``       encrypted PDF (Heuristics.Encrypted.PDF)
- ``scan.limit_exceeded`` file too big or too deep (Heuristics.Limits.*)
No finding when clamd answers OK. Any other answer raises ``ClamdError``:
the session engine turns it into ``internal.error`` (red).
"""

import os
import socket
from pathlib import Path

from februus.core.checks import Analyzer, Finding, ScannedFile

ENCRYPTED_PDF = "Heuristics.Encrypted.PDF"
ENCRYPTED_PREFIX = "Heuristics.Encrypted."
LIMITS_PREFIX = "Heuristics.Limits.Exceeded."
MAX_REPLY_BYTES = 64 * 1024


class ClamdError(Exception):
    """clamd could not be reached or gave an unexpected answer."""


class ClamavAnalyzer(Analyzer):
    name = "clamav"

    def __init__(self, socket_path: Path, timeout_seconds: float) -> None:
        self.socket_path = socket_path
        self.timeout_seconds = timeout_seconds

    def analyze(self, file: ScannedFile) -> list[Finding]:
        # The offset is shared with whoever read the descriptor before.
        os.lseek(file.fd, 0, os.SEEK_SET)
        return parse_reply(self._scan_fd(file.fd))

    def version(self) -> str | None:
        """Engine and signatures, like "ClamAV 1.4.3/28140/Thu Oct  1 2026".
        None when clamd does not answer (the scan will fail anyway)."""
        try:
            with self._connect() as sock:
                sock.sendall(b"zVERSION\0")
                return _receive(sock)
        except (OSError, ClamdError):
            return None

    def ping(self) -> bool:
        """True if clamd answers. For health checks, never raises."""
        try:
            with self._connect() as sock:
                sock.sendall(b"zPING\0")
                return _receive(sock) == "PONG"
        except (OSError, ClamdError):
            return False

    def _scan_fd(self, fd: int) -> str:
        with self._connect() as sock:
            sock.sendall(b"zFILDES\0")
            # The descriptor travels as ancillary data with one dummy byte.
            socket.send_fds(sock, [b"\0"], [fd])
            return _receive(sock)

    def _connect(self) -> socket.socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout_seconds)
        try:
            sock.connect(str(self.socket_path))
        except OSError as exc:
            sock.close()
            raise ClamdError(f"cannot connect to clamd ({self.socket_path}): {exc}") from exc
        return sock


def parse_reply(reply: str) -> list[Finding]:
    """Turn one clamd answer ("fd[5]: Eicar-Signature FOUND") into findings."""
    _, sep, result = reply.partition(": ")
    if not sep:
        raise ClamdError(f"unexpected clamd answer: {reply!r}")
    if result == "OK":
        return []
    if result.endswith(" FOUND"):
        signature = result.removesuffix(" FOUND")
        if signature == ENCRYPTED_PDF:
            return [Finding("pdf.encrypted", signature)]
        if signature.startswith(ENCRYPTED_PREFIX):
            return [Finding("archive.encrypted", signature)]
        if signature.startswith(LIMITS_PREFIX):
            return [Finding("scan.limit_exceeded", signature)]
        return [Finding("clamav.detected", signature)]
    # "... ERROR" or anything else: fail-closed, never "clean".
    # FR : « ERROR » ou toute autre réponse : erreur, jamais « sain ».
    raise ClamdError(f"clamd could not scan the file: {result!r}")


def _receive(sock: socket.socket) -> str:
    """Read one answer, terminated by a NUL byte (z-commands)."""
    data = b""
    while not data.endswith(b"\0"):
        chunk = sock.recv(4096)
        if not chunk:
            raise ClamdError("clamd closed the connection without answering")
        data += chunk
        if len(data) > MAX_REPLY_BYTES:
            raise ClamdError("clamd answer too long")
    return data[:-1].decode("utf-8", errors="replace")

