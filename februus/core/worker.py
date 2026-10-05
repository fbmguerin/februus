"""Analyzer worker: the session side of the analyzer process.

The session engine gives one file at a time. The worker opens it and
sends its descriptor to the analyzer process (a child process of the
service, ``februus/analyzer/service.py``), then waits for the answer with
a timeout (``februus/core/analyzer_protocol.py``). If the analysis hangs
or the process dies, the process is killed and a new one is used for the
next file: a bad file cannot block or crash the station.

FR : les analyseurs tournent dans un processus fils. Si l'analyse d'un
fichier bloque ou plante, ce processus est tué et un nouveau est utilisé.
"""

import multiprocessing
import os
import select
import socket
import threading
import time
from pathlib import Path

from februus.core.analyzer_protocol import (
    FileResult,
    ProtocolError,
    receive_answer,
    send_request,
)
from februus.core.config import FINDING_CODE_RE, AnalyzersConfig
from februus.core.files import open_regular

# "spawn" starts a fresh Python process: nothing is shared with the
# scanner by accident (open files, threads, database connections).
_CONTEXT = multiprocessing.get_context("spawn")


class WorkerTimeout(Exception):
    """The analysis did not finish in time (the analyzer was stopped)."""


class WorkerDied(Exception):
    """The analyzer process cannot be reached, stopped without answering
    or gave a malformed answer."""


class WorkerCancelled(Exception):
    """The analysis was cancelled (key removed): the analyzer was stopped."""


class AnalyzerWorker:
    """One connection to an analyzer process. Use as a context manager."""

    def __init__(self, analyzers: AnalyzersConfig) -> None:
        self._analyzers = analyzers
        self._process: multiprocessing.process.BaseProcess | None = None
        self._sock: socket.socket | None = None

    def __enter__(self) -> "AnalyzerWorker":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    def analyze(
        self,
        path: Path,
        name: str,
        timeout_seconds: float,
        cancel: threading.Event | None = None,
        check_seconds: float = 0.2,
    ) -> FileResult:
        """Analyze one file; ``name`` (its path relative to the key) is
        only information for the analyzers. Raises WorkerTimeout,
        WorkerDied, or WorkerCancelled when ``cancel`` is set (checked
        every ``check_seconds``)."""
        deadline = time.monotonic() + timeout_seconds
        try:
            # Opened HERE, by the scanner: the analyzer never gets a path.
            # FR : ouvert ICI par le scanner ; l'analyseur ne reçoit jamais
            # de chemin, seulement le descripteur (lien jamais suivi).
            fd = open_regular(path)
        except OSError as exc:
            return FileResult(error=f"unreadable file: {exc!r}")
        try:
            if self._sock is None:
                self._start()
            sock = self._sock
            assert sock is not None

            def wait() -> None:
                # Checked before EVERY read, also when data is there: an
                # analyzer sending its answer byte by byte cannot go past
                # the timeout nor hide the removal of the key.
                # FR : vérifié avant CHAQUE lecture : un analyseur qui
                # répond octet par octet ne contourne ni le délai ni le
                # retrait de la clé.
                while True:
                    if cancel is not None and cancel.is_set():
                        raise WorkerCancelled("analysis cancelled")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise WorkerTimeout(f"no answer after {timeout_seconds:.0f} s")
                    if select.select([sock], [], [], min(check_seconds, remaining))[0]:
                        return

            # Sending never blocks longer than the time left for the file
            # (a timeout here is an OSError: WorkerDied, red).
            sock.settimeout(max(0.001, deadline - time.monotonic()))
            send_request(sock, name, fd)
            result = receive_answer(sock, wait)
            self._check(result)
            return result
        except (ProtocolError, OSError) as exc:
            # FAIL-CLOSED: no analyzer, no answer or a malformed answer is
            # an error. Never a fallback to another mode.
            # FR : pas d'analyseur, pas de réponse ou réponse invalide =
            # erreur (ROUGE). Jamais de repli silencieux vers un autre mode.
            self.stop()
            raise WorkerDied(f"analyzer stopped: {exc!r}") from exc
        except (WorkerCancelled, WorkerTimeout):
            self.stop()
            raise
        finally:
            os.close(fd)

    def stop(self) -> None:
        """Kill the analyzer process (a new one is used for the next file)."""
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        if self._process is not None:
            self._process.kill()
            self._process.join()
            self._process.close()
            self._process = None

    def _check(self, result: FileResult) -> None:
        """The answer comes from the process that reads hostile content:
        only findings of the configured analyzers are accepted."""
        for module, code, _ in result.findings:
            if module not in self._analyzers.names or not FINDING_CODE_RE.match(code):
                raise ProtocolError(f"unexpected finding: {module!r} {code!r}")

    def _start(self) -> None:
        parent_sock, child_sock = socket.socketpair()
        self._sock = parent_sock
        try:
            process = _CONTEXT.Process(
                target=_local_main,
                args=(self._analyzers, child_sock),
                daemon=True,
            )
            process.start()
            # Kept only once started: stop() can always kill it.
            self._process = process
        finally:
            child_sock.close()


def _local_main(analyzers: AnalyzersConfig, sock: socket.socket) -> None:
    """Body of the analyzer process. No supervisor: the session kills its
    own child process."""
    from februus.analyzer.service import serve
    from februus.analyzers import build_analyzers

    serve(sock, build_analyzers(analyzers))
