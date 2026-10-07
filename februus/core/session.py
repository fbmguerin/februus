"""Session engine: inventory, analysis, progress, ETA, verdict.

One session = one key (a folder for development, the partitions of a key
on a station). When a device is given, the inspectors run first; if their
findings already give RED, the files are never read. Nothing is ever
written on the key.

The screen follows the session through a ``Status`` (in memory); when the
session ends, one line is added to the key log (``core/keylog.py``).

FAIL-CLOSED: any exception, timeout or file left unanalyzed adds a
finding that gives RED. A session never ends green by default.
FR : toute exception, tout dépassement de délai ou fichier non analysé
ajoute un constat qui donne ROUGE. Jamais de vert par défaut.
"""

import logging
import os
import threading
import time
import traceback
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path, PurePath

from februus.analyzers import build_analyzers
from februus.core import keylog
from februus.core.checks import BlockDevice, Reader
from februus.core.config import Config
from februus.core.status import Status
from februus.core.verdict import Color, color_of, compute_verdict
from februus.core.worker import AnalyzerWorker, WorkerCancelled, WorkerDied, WorkerTimeout
from februus.inspectors import INSPECTORS

LOG = logging.getLogger(__name__)

# Module name stored with the findings added by the engine itself.
ENGINE = "session"


class SessionAborted(Exception):
    """The key was removed during the session (``cancel`` was set)."""


@dataclass(frozen=True, slots=True)
class FindingRow:
    path: str | None
    module: str
    code: str
    color: Color
    detail: str


@dataclass(frozen=True, slots=True)
class SessionResult:
    session_id: int
    verdict: Color
    files_total: int
    findings: tuple[FindingRow, ...]


class _Run:
    """What one session has found so far (in memory)."""

    def __init__(self, config: Config, status: Status, session_id: int) -> None:
        self.config = config
        self.status = status
        self.session_id = session_id
        # (path, module, code, detail); the path is None for the key itself.
        self.found: list[tuple[str | None, str, str, str]] = []
        self.files_total = 0
        self.files_done = 0
        self.bytes_done = 0
        # Files not analyzed successfully (yet).
        self.unfinished = 0

    def add(self, path: str | None, module: str, code: str, detail: str) -> None:
        self.found.append((path, module, code, detail))

    def verdict(self) -> Color:
        """Verdict from the findings so far (can be called twice)."""
        codes = [code for _, _, code, _ in self.found]
        if self.unfinished and not {"scan.timeout", "internal.error"} & set(codes):
            # Should never happen: a file was skipped without any reason.
            self.add(None, ENGINE, "internal.error", f"{self.unfinished} file(s) not analyzed")
            codes.append("internal.error")
        return compute_verdict(codes, self.config.verdict.rules)

    def rows(self) -> tuple[FindingRow, ...]:
        rules = self.config.verdict.rules
        return tuple(
            FindingRow(path, module, code, color_of(code, rules), detail)
            for path, module, code, detail in self.found
        )


def run_session(
    config: Config,
    status: Status,
    reader: Reader,
    source: str | Sequence[str],
    clock: Callable[[], float] = time.monotonic,
    device: BlockDevice | None = None,
    cancel: threading.Event | None = None,
) -> SessionResult:
    """Analyze ``source`` (one folder or partition, or the list of all the
    partitions of a key) with ``reader`` and return the verdict. The screen
    follows through ``status``; the end of the session is added to the key
    log.

    ``clock`` measures durations (replaced in tests). ``cancel`` is set
    by the scanner when the key is removed: the session stops and is red
    ("device.removed"), never green.
    """
    sources = [source] if isinstance(source, str) else list(source)
    checker = _Cancel(cancel)
    started = keylog.now()
    started_clock = clock()
    run = _Run(config, status, status.start())
    signatures: str | None = None
    try:
        versions = [v for v in (a.version() for a in build_analyzers(config.analyzers)) if v]
        signatures = " ; ".join(versions) or None
        if signatures:
            status.update(signatures=signatures)
        if device is not None:
            status.update(state="inspecting")
            for module, code, detail in run_inspectors(device):
                run.add(None, module, code, detail)
        checker.check()
        if device is not None and run.verdict() is Color.RED:
            # Refused by the inspectors: the key is never mounted nor read.
            # FR : clé refusée par les inspecteurs : jamais montée ni lue.
            LOG.info("session %s: device refused by the inspectors", run.session_id)
        else:
            status.update(state="scanning")
            _read_source(run, reader, sources, clock, checker)
    except SessionAborted:
        # Key removed: red, never green.
        # FR : clé retirée : ROUGE, jamais vert.
        return _end(run, started, clock() - started_clock, signatures, aborted=True)
    except Exception:
        # FAIL-CLOSED / FR : toute erreur imprévue donne ROUGE.
        # The findings of the files analyzed before stay in ``run.found``.
        run.add(None, ENGINE, "internal.error", traceback.format_exc(limit=5))
        # Seen on a real key: when the key is pulled out, a read error can
        # come just before the removal event. Wait one check period: if the
        # key is gone, the session is "key removed" (still red, and the
        # error stays in the findings).
        # FR : une erreur de lecture peut précéder l'événement de retrait :
        # la session est alors « clé retirée » (toujours ROUGE).
        if checker.wait(config.scan.cancel_check_ms / 1000):
            return _end(run, started, clock() - started_clock, signatures, aborted=True)
    return _end(run, started, clock() - started_clock, signatures, aborted=False)


def _end(
    run: _Run, started: str, seconds: float, signatures: str | None, aborted: bool
) -> SessionResult:
    """Show the result, add the line to the key log, return the result.
    An aborted session (key removed) is always red."""
    if aborted:
        run.add(None, ENGINE, "device.removed", "key removed during the analysis")
        verdict = Color.RED
    else:
        verdict = run.verdict()
    rows = run.rows()
    problems = [row for row in rows if row.color is not Color.GREEN]
    run.status.update(
        state="aborted" if aborted else "result",
        verdict=verdict.value,
        files_done=run.files_done,
        bytes_done=run.bytes_done,
        eta_seconds=0,
        problems=tuple(sorted({row.code for row in problems})),
        big_files=tuple(
            _printable(row.path) for row in problems
            if row.code in BIG_FILE_CODES and row.path
        )[:5],
    )
    entry = {
        "started": started,
        "seconds": round(seconds),
        "station": run.config.station.name,
        "verdict": verdict.value,
        "removed": aborted,
        "files": run.files_total,
        "bytes": run.bytes_done,
        "signatures": signatures,
        "problems": [
            {"path": keylog.safe_text(row.path) if row.path else None,
             "code": row.code, "color": row.color.value}
            for row in problems[: keylog.MAX_PROBLEMS]
        ],
    }
    try:
        keylog.append(run.config.log.path, entry)
    except OSError:
        # The result on screen does not depend on the log: only reported.
        LOG.exception("cannot write the key log %s", run.config.log.path)
    LOG.info("session %s: %s", run.session_id, verdict.value)
    return SessionResult(run.session_id, verdict, run.files_total, rows)


def run_inspectors(device: BlockDevice) -> list[tuple[str, str, str]]:
    """(inspector, code, detail) of every inspector finding. An inspector
    that fails gives ``internal.error`` (red), never "nothing found"."""
    results = []
    for name, inspect in INSPECTORS:
        try:
            for finding in inspect(device):
                results.append((name, finding.code, finding.detail))
        except Exception as exc:
            # FAIL-CLOSED / FR : un inspecteur en échec donne ROUGE.
            results.append((name, "internal.error", repr(exc)[:300]))
    return results


def _read_source(
    run: _Run,
    reader: Reader,
    sources: list[str],
    clock: Callable[[], float],
    checker: "_Cancel",
) -> None:
    """Open every source (all the partitions of the key) and analyze
    their files."""
    with ExitStack() as stack:
        roots = []
        for source in sources:
            # Several partitions: file paths start with the partition name.
            label = PurePath(source).name if len(sources) > 1 else ""
            roots.append((label, stack.enter_context(reader.open(source))))
        _scan(run, roots, clock, checker)
        checker.check()


# Findings of a file too big (or too deep) to be checked: its name is shown.
BIG_FILE_CODES = ("file.too_big", "scan.limit_exceeded")


def _printable(name: str) -> str:
    """A name from the key, safe to show: invisible characters (such as the
    right-to-left mark that can turn "exe.mp4" around) become "?".
    FR : un nom venant de la clé : caractères invisibles remplacés par « ? »."""
    return "".join(c if c.isprintable() else "?" for c in name)


class InventoryStopped(Exception):
    """The inventory was stopped: too many entries or out of time."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def inventory(
    root: Path,
    max_entries: int | None = None,
    check: Callable[[], None] | None = None,
) -> tuple[list[tuple[PurePath, int]], list[PurePath]]:
    """List regular files (relative path, size) and other entries.

    Symbolic links are never followed; they are listed as "other" with
    devices, sockets... Errors (unreadable folder) are raised.
    FR : les liens symboliques ne sont jamais suivis.

    A crafted key may hold millions of entries: ``check`` is called for
    each folder (key removed, session timeout) and more than
    ``max_entries`` entries raises InventoryStopped (red).
    FR : une clé piégée peut contenir des millions d'entrées : limite et
    délai vérifiés pendant l'inventaire.
    """
    files: list[tuple[PurePath, int]] = []
    others: list[PurePath] = []
    folders = [root]
    count = 0
    while folders:
        if check is not None:
            check()
        folder = folders.pop()
        with os.scandir(folder) as entries:
            for entry in sorted(entries, key=lambda e: e.name):
                count += 1
                if max_entries is not None and count > max_entries:
                    raise InventoryStopped(
                        "scan.limit_exceeded", f"more than {max_entries} entries on the key"
                    )
                relative = PurePath(entry.path).relative_to(root)
                if entry.is_dir(follow_symlinks=False):
                    folders.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    files.append((relative, entry.stat(follow_symlinks=False).st_size))
                else:
                    others.append(relative)
    files.sort()
    others.sort()
    return files, others


def _scan(
    run: _Run,
    roots: list[tuple[str, Path]],
    clock: Callable[[], float],
    checker: "_Cancel",
) -> None:
    scan = run.config.scan
    deadline = clock() + scan.session_timeout_minutes * 60

    files: list[tuple[PurePath, int]] = []
    paths: list[Path] = []

    def keep_going() -> None:
        checker.check()
        if clock() >= deadline:
            raise InventoryStopped("scan.timeout", "session timeout during the inventory")

    for label, root in roots:
        try:
            found, others = inventory(
                root, scan.max_entries - len(files), check=keep_going
            )
        except InventoryStopped as stop:
            # FAIL-CLOSED: nothing is analyzed, the finding gives red.
            # FR : rien n'est analysé, le constat donne ROUGE.
            run.add(None, ENGINE, stop.code, stop.detail)
            return
        for other in others:
            run.add(
                None, ENGINE, "file.not_regular",
                keylog.safe_text(PurePath(label) / other),
            )
        files += [(PurePath(label) / relative, size) for relative, size in found]
        paths += [root / relative for relative, _ in found]
    # A file bigger than the antivirus limit cannot be checked: red at once,
    # before reading anything (reading a 5 GB file of a key takes minutes,
    # and the verdict could only be red).
    # FR : fichier trop gros pour l'antivirus : ROUGE tout de suite, sans
    # rien lire (rouge et non orange : gonfler un virus est une ruse connue).
    max_bytes = scan.max_file_mb * 1024 * 1024
    too_big = [(name, size) for name, size in files if size > max_bytes]
    if too_big:
        for name, size in too_big:
            run.add(
                keylog.safe_text(name), ENGINE, "file.too_big",
                f"{size // (1024 * 1024)} MB > {scan.max_file_mb} MB",
            )
        return
    bytes_total = sum(size for _, size in files)
    run.files_total = run.unfinished = len(files)
    run.status.update(files_total=len(files), bytes_total=bytes_total)

    started = last_update = clock()
    with AnalyzerWorker(run.config.analyzers) as worker:
        for (name, size), path in zip(files, paths, strict=True):
            checker.check()
            remaining = deadline - clock()
            if remaining <= 0:
                run.add(None, ENGINE, "scan.timeout", "session timeout")
                break
            timeout = min(scan.file_timeout_seconds, remaining)
            try:
                _analyze_file(run, worker, path, str(name), timeout, checker,
                              scan.cancel_check_ms / 1000)
            except WorkerTimeout:
                if timeout < scan.file_timeout_seconds:
                    run.add(None, ENGINE, "scan.timeout", "session timeout")
                    break
                run.add(keylog.safe_text(name), ENGINE, "scan.timeout", "file timeout")
            run.files_done += 1
            run.bytes_done += size
            if clock() - last_update >= scan.progress_update_seconds:
                last_update = clock()
                run.status.update(
                    files_done=run.files_done,
                    bytes_done=run.bytes_done,
                    eta_seconds=_eta(bytes_total - run.bytes_done, run.bytes_done,
                                     last_update - started),
                )
    run.status.update(files_done=run.files_done, bytes_done=run.bytes_done, eta_seconds=0)


def _analyze_file(
    run: _Run,
    worker: AnalyzerWorker,
    path: Path,
    name: str,
    timeout: float,
    checker: "_Cancel",
    check_seconds: float,
) -> None:
    shown = keylog.safe_text(name)
    try:
        result = worker.analyze(path, name, timeout, checker.event, check_seconds)
    except WorkerCancelled as exc:
        raise SessionAborted from exc
    except WorkerDied as exc:
        run.add(shown, ENGINE, "internal.error", str(exc))
        return
    if result.error is not None:
        run.add(shown, ENGINE, "internal.error", result.error)
        return
    for module, code, detail in result.findings:
        run.add(shown, module, code, detail)
    run.unfinished -= 1


class _Cancel:
    """Wraps the optional cancel event set by the scanner."""

    def __init__(self, event: threading.Event | None) -> None:
        self.event = event

    def check(self) -> None:
        if self.event is not None and self.event.is_set():
            raise SessionAborted

    def wait(self, seconds: float) -> bool:
        """True if the key is removed, now or within ``seconds``."""
        return self.event is not None and self.event.wait(seconds)


def _eta(bytes_left: int, bytes_done: int, seconds: float) -> int | None:
    """Seconds left, from the speed measured since the scan started."""
    if bytes_done <= 0 or seconds <= 0:
        return None
    return round(bytes_left / (bytes_done / seconds))
