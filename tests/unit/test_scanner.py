"""Tests for the scanner service, with simulated USB events."""

import copy
import threading
import tomllib
from pathlib import Path

import pytest

from februus.core.config import parse_config
from februus.core.devices import ImageDevice
from februus.core.status import Status
from februus.readers.directory import DirectoryReader
from februus.scanner.service import KeyEvent, Scanner
from tests import disk_images as img

DEV = Path(__file__).resolve().parents[2] / "config" / "februus.dev.toml"
MARKER = b"FEBRUUS-FAKE-MALWARE"


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def setup(tmp_path):
    with DEV.open("rb") as file:
        raw = copy.deepcopy(tomllib.load(file))
    raw["log"]["path"] = str(tmp_path / "keys.jsonl")
    config = parse_config(raw)
    key = tmp_path / "key"  # files of the "partition" (directory reader)
    key.mkdir()
    (key / "a.txt").write_bytes(b"hello")
    image = tmp_path / "key.img"
    image.write_bytes(bytes(img.superfloppy()))
    clock = FakeClock()
    devices: dict[str, Path] = {"/dev/sdb": image}
    status = Status()
    scanner = Scanner(
        config,
        status,
        DirectoryReader(),
        open_device=lambda disk: ImageDevice(devices[disk]),
        clock=clock,
    )
    return scanner, status, key, clock, devices, image


def plug(scanner, key, disk="/dev/sdb"):
    scanner.handle(KeyEvent("add", disk, (str(key),)))


def test_clean_key_then_removal(setup):
    scanner, status, key, *_ = setup
    before = sorted(p.name for p in key.iterdir())
    plug(scanner, key)
    scanner.wait()
    shown = status.snapshot()
    assert (shown.state, shown.verdict) == ("result", "green")
    assert sorted(p.name for p in key.iterdir()) == before  # nothing written on the key
    scanner.handle(KeyEvent("remove", "/dev/sdb"))
    assert status.snapshot().state == "idle"  # back to idle


def test_infected_key_is_red(setup):
    scanner, status, key, *_ = setup
    (key / "bad.txt").write_bytes(MARKER)
    plug(scanner, key)
    scanner.wait()
    assert status.snapshot().verdict == "red"


def test_bootable_key_is_refused(setup):
    scanner, status, key, _, devices, image = setup
    image.write_bytes(bytes(img.bootable_iso()))
    plug(scanner, key)
    scanner.wait()
    shown = status.snapshot()
    assert (shown.verdict, shown.files_total) == ("red", 0)


def test_removed_during_the_analysis(setup):
    scanner, status, key, clock, *_ = setup
    (key / "slow.txt").write_bytes(b"FEBRUUS-FAKE-SLOW")
    plug(scanner, key)
    threading.Event().wait(1.0)  # the analysis is now stuck on slow.txt
    scanner.handle(KeyEvent("remove", "/dev/sdb"))
    shown = status.snapshot()
    assert (shown.state, shown.verdict) == ("aborted", "red")
    # The "key removed" screen stays, then the station goes back to idle.
    scanner.tick()
    assert status.snapshot().state == "aborted"
    clock.now += 30
    scanner.tick()
    assert status.snapshot().state == "idle"


def test_second_key_is_ignored_while_the_first_is_in(setup):
    scanner, status, key, _, devices, image = setup
    devices["/dev/sdc"] = image
    plug(scanner, key)
    scanner.wait()
    plug(scanner, key, disk="/dev/sdc")
    scanner.wait()
    assert status.snapshot().id == 1  # only one session was started
    assert status.snapshot().extra_keys == 1  # the screen says so


def test_extra_key_removed_first_clears_the_notice(setup):
    scanner, status, key, _, devices, image = setup
    devices["/dev/sdc"] = image
    plug(scanner, key)
    scanner.wait()
    plug(scanner, key, disk="/dev/sdc")
    scanner.handle(KeyEvent("remove", "/dev/sdc"))
    shown = status.snapshot()
    assert (shown.state, shown.verdict, shown.extra_keys) == ("result", "green", 0)


def test_first_key_removed_first_leaves_the_other_unchecked(setup):
    # The second key is never analyzed by itself: it must be plugged in again.
    scanner, status, key, _, devices, image = setup
    devices["/dev/sdc"] = image
    plug(scanner, key)
    scanner.wait()
    plug(scanner, key, disk="/dev/sdc")
    scanner.handle(KeyEvent("remove", "/dev/sdb"))
    shown = status.snapshot()
    assert (shown.state, shown.extra_keys, shown.id) == ("idle", 1, 1)
    scanner.handle(KeyEvent("remove", "/dev/sdc"))
    assert status.snapshot().extra_keys == 0
    plug(scanner, key, disk="/dev/sdc")  # plugged in again: analyzed
    scanner.wait()
    assert status.snapshot().id == 2


def test_same_extra_key_is_counted_once(setup):
    scanner, status, key, _, devices, image = setup
    devices["/dev/sdc"] = image
    plug(scanner, key)
    plug(scanner, key, disk="/dev/sdc")
    plug(scanner, key, disk="/dev/sdc")
    scanner.wait()
    assert status.snapshot().extra_keys == 1


def test_unreadable_device_is_red_and_never_read(setup):
    scanner, status, key, _, devices, _ = setup
    del devices["/dev/sdb"]  # opening the device fails
    plug(scanner, key)
    scanner.wait()
    shown = status.snapshot()
    assert (shown.verdict, shown.files_total) == ("red", 0)


def test_a_failing_session_never_stays_on_the_progress_screen(setup, monkeypatch):
    # A station problem (not a key problem) must end on the red screen.
    scanner, status, key, *_ = setup

    def broken(*args, **kwargs):
        raise RuntimeError("station problem")

    monkeypatch.setattr("februus.scanner.service.run_session", broken)
    plug(scanner, key)
    scanner.wait()
    shown = status.snapshot()
    assert (shown.state, shown.verdict, shown.problems) == ("result", "red", ("internal.error",))


def test_blocked_devices_are_counted_until_unplugged(setup):
    scanner, status, *_ = setup
    scanner.handle(KeyEvent("blocked", "/sys/a"))
    scanner.handle(KeyEvent("blocked", "/sys/b"))
    scanner.handle(KeyEvent("blocked", "/sys/b"))
    assert status.snapshot().blocked_devices == 2
    scanner.handle(KeyEvent("unblocked", "/sys/a"))
    scanner.handle(KeyEvent("unblocked", "/sys/b"))
    assert status.snapshot().blocked_devices == 0
    assert status.snapshot().state == "idle"  # no session was started
