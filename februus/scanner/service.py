"""The scanner: reacts to USB keys plugged in and removed.

One key at a time:
- key plugged in: a session starts in a thread (inspectors, then the
  files of every partition);
- key removed during the session: the session is cancelled, it ends red
  ("key removed too early"); after ``removed_screen_seconds`` the screen
  goes back to idle;
- key removed after the result: the session is closed (idle screen);
- a second key plugged in meanwhile is never analyzed: the screen says
  "remove the other key" until it is removed. If the first key is removed
  first, the second one stays unchecked: it must be plugged in again.

The scanner is the part of the Februus service that follows the keys.
The events come from udev (``februus/scanner/udev.py``); this module does
not depend on udev, so it is tested with simulated events.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from februus.core.checks import BlockDevice, Reader
from februus.core.config import Config
from februus.core.session import run_session
from februus.core.status import Status

LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class KeyEvent:
    # "add" or "remove" (a key); "blocked" or "unblocked" (a USB device
    # refused by USBGuard, then unplugged).
    action: str
    disk: str  # "/dev/sdb" (for "blocked": the sys path of the device)
    # Partitions holding data ("/dev/sdb1"...). Empty: the file system is
    # directly on the disk.
    partitions: tuple[str, ...] = ()


class UnavailableDevice:
    """A device that could not be opened: every read fails."""

    def __init__(self, path: str, error: Exception) -> None:
        self.path = path
        self.size = 0
        self._error = error

    def read_at(self, offset: int, length: int) -> bytes:
        raise OSError(f"device {self.path} unavailable: {self._error!r}")


class Scanner:
    def __init__(
        self,
        config: Config,
        status: Status,
        reader: Reader,
        open_device: Callable[[str], BlockDevice | None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._reader = reader
        self._status = status
        self._open_device = open_device
        self._clock = clock
        self._disk: str | None = None  # disk of the current session
        self._extra: set[str] = set()  # other keys plugged in, ignored
        self._blocked: set[str] = set()  # devices refused by USBGuard
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._close_at: float | None = None  # back to idle after "removed"

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def handle(self, event: KeyEvent) -> None:
        if event.action == "add":
            self._key_added(event)
        elif event.action == "remove":
            self._key_removed(event)
        elif event.action == "blocked":
            self._blocked.add(event.disk)
            self._status.set_blocked_devices(len(self._blocked))
        elif event.action == "unblocked":
            self._blocked.discard(event.disk)
            self._status.set_blocked_devices(len(self._blocked))

    def tick(self) -> None:
        """Called regularly: actions that wait for a delay."""
        if self._close_at is not None and self._clock() >= self._close_at:
            self._close_at = None
            self._status.close()

    def wait(self) -> None:
        """Wait for the current session to end (tests, shutdown)."""
        if self._thread is not None:
            self._thread.join()

    def _key_added(self, event: KeyEvent) -> None:
        if self.busy or self._disk is not None:
            # One key at a time: a second key is ignored until the first
            # one is removed.
            LOG.warning("key %s ignored: %s is still plugged in", event.disk, self._disk)
            self._extra.add(event.disk)
            self._status.set_extra_keys(len(self._extra))
            return
        self._close_at = None
        self._disk = event.disk
        self._cancel = threading.Event()
        sources = list(event.partitions) or [event.disk]
        self._thread = threading.Thread(
            target=self._run_session,
            args=(event.disk, sources, self._cancel),
            name=f"session-{event.disk}",
            daemon=True,
        )
        self._thread.start()

    def _key_removed(self, event: KeyEvent) -> None:
        if event.disk in self._extra:
            self._extra.discard(event.disk)
            self._status.set_extra_keys(len(self._extra))
            return
        if event.disk != self._disk:
            return
        self._disk = None
        if self.busy:
            # FAIL-CLOSED: removed during the analysis -> red.
            # FR : clé retirée pendant l'analyse -> ROUGE.
            self._cancel.set()
            self.wait()
            self._close_at = self._clock() + self._config.scanner.removed_screen_seconds
        else:
            self._status.close()

    def _run_session(self, disk: str, sources: list[str], cancel: threading.Event) -> None:
        try:
            try:
                device = self._open_device(disk)
            except Exception as exc:
                # FAIL-CLOSED: the inspectors will fail on it (red), and
                # the key is never mounted.
                # FR : périphérique illisible : ROUGE, jamais monté.
                device = UnavailableDevice(disk, exc)
            run_session(
                self._config, self._status, self._reader, sources,
                device=device, cancel=cancel,
            )
        except Exception:
            # run_session never raises for a key problem; this is a
            # station problem. FAIL-CLOSED: the screen shows red, never
            # "analysis in progress" for ever.
            # FR : problème de la station : écran ROUGE, jamais « analyse
            # en cours » indéfiniment.
            LOG.exception("session on %s failed", disk)
            self._status.update(
                state="result", verdict="red", eta_seconds=0, problems=("internal.error",)
            )
