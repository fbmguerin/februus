"""What the screen shows now, kept in memory.

The session thread writes (``start``, ``update``, ``close``), the web UI
only reads (``snapshot``). Both live in the same process: nothing is
written to a database or a file for the screen.
FR : l'état affiché à l'écran vit en mémoire ; le thread d'analyse écrit,
l'interface web lit seulement.
"""

import threading
from dataclasses import dataclass, replace
from typing import Any

# "idle": no key. "result" and "aborted" (key removed too early) stay on
# screen until the key is removed.
STATES = ("idle", "inspecting", "scanning", "result", "aborted")


@dataclass(frozen=True, slots=True)
class SessionStatus:
    """A snapshot of the current (or last) session."""

    # Number of the last session started since the service started.
    id: int = 0
    state: str = "idle"
    verdict: str | None = None
    files_total: int = 0
    files_done: int = 0
    bytes_total: int = 0
    bytes_done: int = 0
    eta_seconds: int | None = None
    # Finding codes that give orange or red, shown on the result screen.
    problems: tuple[str, ...] = ()
    # Names of the files too big to be checked (at most 5), for the screen.
    big_files: tuple[str, ...] = ()
    # Antivirus signatures of the last session that knew them.
    signatures: str | None = None
    # Other keys plugged in and ignored (one key at a time). Not part of a
    # session: it is added by ``Status.snapshot``.
    extra_keys: int = 0
    # USB devices refused by USBGuard and still plugged in (same remark).
    blocked_devices: int = 0


class Status:
    """The status of the station, safe to use from several threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current = SessionStatus()
        self._extra_keys = 0
        self._blocked_devices = 0

    def snapshot(self) -> SessionStatus:
        with self._lock:
            return replace(
                self._current,
                extra_keys=self._extra_keys,
                blocked_devices=self._blocked_devices,
            )

    def set_extra_keys(self, count: int) -> None:
        """How many more keys than the analyzed one are plugged in."""
        with self._lock:
            self._extra_keys = count

    def set_blocked_devices(self, count: int) -> None:
        """How many USB devices refused by USBGuard are still plugged in."""
        with self._lock:
            self._blocked_devices = count

    def start(self) -> int:
        """A new session begins. Returns its number."""
        with self._lock:
            self._current = SessionStatus(
                id=self._current.id + 1,
                state="scanning",
                signatures=self._current.signatures,
            )
            return self._current.id

    def update(self, **changes: Any) -> None:
        """Change fields of the current session."""
        with self._lock:
            self._current = replace(self._current, **changes)

    def close(self) -> None:
        """The key was removed after the result: back to the idle screen.
        A session still running is left alone."""
        with self._lock:
            if self._current.state in ("result", "aborted"):
                self._current = SessionStatus(
                    id=self._current.id, signatures=self._current.signatures
                )
