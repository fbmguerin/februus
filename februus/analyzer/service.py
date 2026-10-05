"""Analyzer process: a child process of the Februus service.

The session sends open files one by one on a socket
(``februus/core/analyzer_protocol.py``); this process reads them, runs
the analyzers and answers. It is started by ``core/worker.py``, which
kills it when a file takes too long or the key is removed: a child stuck
in an analyzer cannot prevent the kill.
FR : le service tue ce processus fils (kill -9) si l'analyse d'un fichier
dure trop ou si la clé est retirée ; un analyseur bloqué ne peut pas
l'empêcher.
"""

import fcntl
import os
import socket
import stat
import traceback
from collections.abc import Sequence

from februus.core.analyzer_protocol import (
    FileResult,
    ProtocolError,
    receive_request,
    send_answer,
)
from februus.core.checks import Analyzer, ScannedFile

READ_CHUNK = 1024 * 1024


def serve(sock: socket.socket, analyzers: Sequence[Analyzer]) -> None:
    """Analyze the files received on ``sock`` until it is closed."""
    try:
        _serve(sock, analyzers)
    except (BrokenPipeError, ConnectionResetError):
        # The scanner closed the connection while an answer was sent.
        return


def _serve(sock: socket.socket, analyzers: Sequence[Analyzer]) -> None:
    while True:
        try:
            file = receive_request(sock)
        except ProtocolError as exc:
            # The stream cannot be trusted any more: answer, then stop.
            send_answer(sock, FileResult(error=f"invalid request: {exc}"))
            sock.shutdown(socket.SHUT_RDWR)
            return
        if file is None:
            return
        try:
            result = analyze_file(analyzers, file)
        finally:
            os.close(file.fd)
        try:
            send_answer(sock, result)
        except ProtocolError as exc:
            # FAIL-CLOSED: an answer too long is an error, not cut short.
            # FR : une réponse trop longue est une erreur, jamais tronquée.
            send_answer(sock, FileResult(error=f"answer not sent: {exc}"))


def analyze_file(analyzers: Sequence[Analyzer], file: ScannedFile) -> FileResult:
    """Run every analyzer on one file. Never raises: errors are returned."""
    try:
        check_readable(file.fd)
    except Exception:
        return FileResult(error=f"unreadable file: {traceback.format_exc(limit=3)}")
    findings: list[tuple[str, str, str]] = []
    for analyzer in analyzers:
        try:
            # The offset is shared: each analyzer starts at the beginning.
            os.lseek(file.fd, 0, os.SEEK_SET)
            for finding in analyzer.analyze(file):
                findings.append((analyzer.name, finding.code, finding.detail))
        except Exception:
            # FAIL-CLOSED: the error is reported, the file is never "clean".
            # FR : l'erreur est remontée, le fichier n'est jamais « sain ».
            return FileResult(
                error=f"{analyzer.name}: {traceback.format_exc(limit=3)}"
            )
    return FileResult(findings=tuple(findings))


def check_readable(fd: int) -> None:
    """Check the descriptor (regular file, read-only) and read the whole
    file once; raises OSError if a part cannot be read.

    FAIL-CLOSED: seen on the mini-PC, clamd answers "OK" for a file it
    could only read in part (damaged key, key pulled out). An analyzer
    cannot be trusted to report read errors, so every byte is read here
    first. The bytes are only read, never used.
    FR : clamd répond « OK » pour un fichier lu seulement en partie (clé
    abîmée). On vérifie donc ici que tout le fichier est lisible ; sinon
    le fichier est en erreur (ROUGE), jamais « sain ».
    """
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        raise OSError("not a regular file")
    if fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
        raise OSError("the file is not opened read-only")
    os.lseek(fd, 0, os.SEEK_SET)
    while os.read(fd, READ_CHUNK):
        pass
