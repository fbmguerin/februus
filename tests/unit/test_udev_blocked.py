"""Tests for the report of USB devices refused by USBGuard (no real udev)."""

from februus.scanner.service import KeyEvent
from februus.scanner.udev import BlockedDevices


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


def make(blocked_paths):
    clock = Clock()
    return BlockedDevices(2, lambda path: path in blocked_paths, clock), clock


def test_a_refused_device_is_reported_after_the_delay_then_unblocked_when_unplugged():
    watch, clock = make({"/sys/hub"})
    watch.added("/sys/hub")
    assert watch.due() == []  # USBGuard may still be allowing it
    clock.now += 2
    assert watch.due() == [KeyEvent("blocked", "/sys/hub")]
    assert watch.due() == []  # reported once
    assert watch.removed("/sys/hub") == KeyEvent("unblocked", "/sys/hub")


def test_an_allowed_device_is_never_reported():
    watch, clock = make(set())
    watch.added("/sys/key")
    clock.now += 5
    assert watch.due() == []
    assert watch.removed("/sys/key") is None


def test_unplugged_before_the_delay_is_never_reported():
    watch, clock = make({"/sys/hub"})
    watch.added("/sys/hub")
    assert watch.removed("/sys/hub") is None
    clock.now += 5
    assert watch.due() == []
