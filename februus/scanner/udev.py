"""USB keys seen by udev (pyudev): plugged in, removed.

Only whole disks on the USB bus are followed. USBGuard (deploy/usbguard)
already refuses every USB device that is not a plain mass storage. Such a
refused device never becomes a disk, so the only trace is the USB device
itself with ``authorized`` = 0: it is reported as "blocked" (the screen asks
the agent to unplug it), and as "unblocked" when it is unplugged.
FR : USBGuard refuse les appareils qui ne sont pas des clés ; l'écran
demande alors de le débrancher.
"""

import time
from collections.abc import Callable, Iterator

import pyudev

from februus.scanner.service import KeyEvent

# MBR extended partitions: containers, not file systems (never mounted).
EXTENDED_TYPES = {"0x5", "0xf", "0x85"}


class BlockedDevices:
    """Follows USB devices plugged in after the start, to report the ones
    that USBGuard still refuses ``settle_seconds`` later (USBGuard needs a
    moment to allow a device: it starts as not authorized)."""

    def __init__(
        self,
        settle_seconds: float,
        is_blocked: Callable[[str], bool],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settle = settle_seconds
        self._is_blocked = is_blocked
        self._clock = clock
        self._waiting: dict[str, float] = {}  # sys path -> time to check
        self._blocked: set[str] = set()

    def added(self, path: str) -> None:
        self._waiting[path] = self._clock() + self._settle

    def removed(self, path: str) -> KeyEvent | None:
        self._waiting.pop(path, None)
        if path in self._blocked:
            self._blocked.discard(path)
            return KeyEvent("unblocked", path)
        return None

    def due(self) -> list[KeyEvent]:
        """Devices whose delay is over and that are still refused."""
        now = self._clock()
        events = []
        for path in [p for p, when in self._waiting.items() if when <= now]:
            del self._waiting[path]
            if self._is_blocked(path):
                self._blocked.add(path)
                events.append(KeyEvent("blocked", path))
        return events


def _usb_device_blocked(context: pyudev.Context, path: str) -> bool:
    # FAIL-CLOSED: a device that cannot be read is reported as blocked.
    # FR : appareil illisible : signalé comme bloqué.
    try:
        value = pyudev.Devices.from_sys_path(context, path).attributes.get("authorized")
    except Exception:
        return True
    return value is not None and value != b"1"


def key_events(settle_seconds: int, poll_seconds: float) -> Iterator[KeyEvent | None]:
    """USB disk events. Yields None every ``poll_seconds`` without event
    (to let the scanner run its delayed actions). Keys already plugged in
    at startup are reported as plugged in."""
    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem="block", device_type="disk")
    monitor.filter_by(subsystem="usb", device_type="usb_device")
    monitor.start()
    blocked = BlockedDevices(settle_seconds, lambda path: _usb_device_blocked(context, path))
    for disk in context.list_devices(subsystem="block", DEVTYPE="disk"):
        if _is_usb(disk):
            yield _event("add", context, disk)
    while True:
        device = monitor.poll(timeout=poll_seconds)
        yield from blocked.due()
        if device is None:
            yield None
        elif device.subsystem == "usb":
            if device.action == "add":
                blocked.added(device.sys_path)
            elif device.action == "remove":
                gone = blocked.removed(device.sys_path)
                if gone is not None:
                    yield gone
        elif _is_usb(device) and device.action in ("add", "remove"):
            if device.action == "add":
                # Partitions appear just after the disk.
                time.sleep(settle_seconds)
            yield _event(device.action, context, device)


def _is_usb(device: pyudev.Device) -> bool:
    return device.get("ID_BUS") == "usb" and device.device_node is not None


def _event(action: str, context: pyudev.Context, disk: pyudev.Device) -> KeyEvent:
    partitions: tuple[str, ...] = ()
    if action == "add":
        partitions = tuple(
            sorted(
                part.device_node
                for part in context.list_devices(subsystem="block", DEVTYPE="partition", parent=disk)
                if part.get("ID_PART_ENTRY_TYPE") not in EXTENDED_TYPES
            )
        )
    return KeyEvent(action=action, disk=disk.device_node, partitions=partitions)
