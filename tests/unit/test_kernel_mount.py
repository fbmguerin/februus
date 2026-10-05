"""Tests for the kernel_mount reader, with a fake udisksctl."""

import os
import stat
import sys
import time
from pathlib import Path

import pytest

from februus.readers import kernel_mount
from februus.readers.kernel_mount import KernelMountReader, MountError, find_mount

FAKE_UDISKSCTL = '''#!{python}
"""Fake udisksctl: "mounts" by writing a line in a fake mountinfo file."""
import os, sys
from pathlib import Path
args = sys.argv[1:]
log = Path(os.environ["FAKE_LOG"])
log.write_text(log.read_text() + " ".join(args) + "\\n" if log.exists() else " ".join(args) + "\\n")
if os.environ.get("FAKE_FAIL") == args[0]:
    print("Error: not authorized", file=sys.stderr)
    sys.exit(1)
mountinfo = Path(os.environ["FAKE_MOUNTINFO"])
source = args[args.index("--block-device") + 1]
lines = [l for l in mountinfo.read_text().splitlines() if f" - " not in l or l.split(" - ")[1].split()[1] != source]
if args[0] == "mount":
    options = os.environ.get("FAKE_OPTIONS") or args[args.index("--options") + 1]
    point = Path(os.environ["FAKE_MEDIA"]) / ("KEY " + source.rsplit("/", 1)[1])
    point.mkdir(parents=True, exist_ok=True)
    escaped = str(point).replace(" ", "\\\\040")
    fstype = os.environ.get("FAKE_FSTYPE", "vfat")
    lines.append(f"40 25 8:17 / {{escaped}} {{options}},relatime shared:1 - {{fstype}} {{source}} rw")
mountinfo.write_text("\\n".join(lines) + "\\n")
'''


@pytest.fixture
def env(tmp_path, monkeypatch):
    script = tmp_path / "udisksctl"
    script.write_text(FAKE_UDISKSCTL.format(python=sys.executable))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text("22 1 8:1 / / rw,relatime - ext4 /dev/sda1 rw\n")
    log = tmp_path / "log"
    monkeypatch.setenv("FAKE_MOUNTINFO", str(mountinfo))
    monkeypatch.setenv("FAKE_MEDIA", str(tmp_path / "media"))
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setattr(kernel_mount, "MOUNTINFO", mountinfo)
    # The fake partitions (/dev/sdb1...) do not exist on the test machine.
    monkeypatch.setattr(kernel_mount, "device_exists", lambda source: True)
    reader = KernelMountReader(10, 0.05, udisksctl=str(script))
    return reader, mountinfo, log


def commands(log: Path) -> list[str]:
    """udisksctl calls, as "mount <options>" or "unmount"."""
    result = []
    for line in log.read_text().splitlines():
        words = line.split()
        if "--options" in words:
            result.append(f"{words[0]} {words[words.index('--options') + 1]}")
        else:
            result.append(words[0])
    return result


def test_mount_read_only_then_unmount(env):
    reader, mountinfo, log = env
    with reader.open("/dev/sdb1") as root:
        assert root.name == "KEY sdb1"  # "\\040" decoded as a space
        assert find_mount("/dev/sdb1").options >= {"ro", "noexec", "nosuid", "nodev"}
    assert find_mount("/dev/sdb1") is None
    assert commands(log) == ["mount ro,noexec,nosuid,nodev", "unmount"]


def test_unsafe_options_are_refused(env, monkeypatch):
    # udisks2 ignored the options (wrong configuration): never analyze.
    reader, mountinfo, log = env
    monkeypatch.setenv("FAKE_OPTIONS", "rw,nosuid,nodev")
    with pytest.raises(MountError, match="unsafe mount"):
        with reader.open("/dev/sdb1"):
            pytest.fail("must not be reached")
    assert find_mount("/dev/sdb1") is None  # unmounted again


def test_unexpected_file_system_is_refused(env, monkeypatch):
    reader, *_ = env
    monkeypatch.setenv("FAKE_FSTYPE", "ext4")
    with pytest.raises(MountError, match="ext4"):
        with reader.open("/dev/sdb1"):
            pass


def test_only_usb_partitions(env):
    reader, *_ = env
    for source in ("/etc/passwd", "/dev/sda1; rm -rf /", "../dev/sdb1", "/dev/nvme0n1"):
        with pytest.raises(MountError, match="not a USB partition"):
            with reader.open(source):
                pass


def test_mount_failure(env, monkeypatch):
    reader, *_ = env
    monkeypatch.setenv("FAKE_FAIL", "mount")
    with pytest.raises(MountError, match="not authorized"):
        with reader.open("/dev/sdb1"):
            pass


def test_unmount_failure_does_not_raise(env, monkeypatch):
    # The analysis is over: an unmount error must not change the verdict.
    reader, *_ = env
    with reader.open("/dev/sdb1"):
        monkeypatch.setenv("FAKE_FAIL", "unmount")


def test_the_reader_cannot_write_on_the_key(env):
    # Security rule 6: nothing is ever written on a key. The reader has no
    # way to remount it read-write: only one read-only mount and one unmount.
    reader, _, log = env
    assert not hasattr(reader, "write_file")
    with reader.open("/dev/sdb1"):
        pass
    assert commands(log) == ["mount ro,noexec,nosuid,nodev", "unmount"]


@pytest.fixture
def slow(env, tmp_path):
    """A reader whose udisksctl needs 0.3 s (6 device checks) to succeed."""
    reader = env[0]
    script = tmp_path / "slow-udisksctl"
    script.write_text("#!/bin/sh\nexec sleep 0.3\n")
    script.chmod(0o755)
    reader.udisksctl = script
    return reader


def test_slow_command_is_not_stopped_while_the_key_is_in(slow, monkeypatch):
    # Only the partition is looked at, not the other arguments.
    monkeypatch.setattr(kernel_mount, "device_exists", lambda source: source == "/dev/sdb1")
    slow._run("mount", "/dev/sdb1", "--options", "ro,noexec,nosuid,nodev")


def test_command_stops_when_the_key_is_removed(slow, monkeypatch):
    # Seen on the mini-PC: udisksctl waits ~20 s when the key is pulled
    # out during an unmount. Februus stops waiting at once.
    monkeypatch.setattr(kernel_mount, "device_exists", lambda source: False)
    started = time.monotonic()
    with pytest.raises(MountError, match="/dev/sdb1 was removed"):
        slow._run("unmount", "/dev/sdb1")
    assert time.monotonic() - started < 0.25


def test_command_timeout(slow):
    slow.timeout = 0.1
    with pytest.raises(MountError, match="no answer after 0.1 s"):
        slow._run("unmount", "/dev/sdb1")


def test_only_the_file_systems_of_the_station_are_accepted():
    assert kernel_mount.FILESYSTEMS == {"vfat", "exfat", "ntfs3", "fuseblk"}


@pytest.mark.hardware
def test_real_key():
    """On the mini-PC: FEBRUUS_PARTITION=/dev/sdb1 (a FAT key)."""
    source = os.environ.get("FEBRUUS_PARTITION")
    if not source:
        pytest.skip("set FEBRUUS_PARTITION to a partition of a real key")
    reader = KernelMountReader(30, 0.2)
    with reader.open(source) as root:
        assert root.is_dir()
        assert find_mount(source).options >= {"ro", "noexec", "nosuid", "nodev"}


# --- mountinfo format ------------------------------------------------------


def test_mountinfo_with_several_optional_fields(tmp_path):
    info = tmp_path / "mountinfo"
    info.write_text(
        "40 25 8:17 / /media/februus/KEY ro,nosuid,nodev,noexec,relatime"
        " shared:7 master:3 propagate_from:2 - vfat /dev/sdb1 ro,fmask=0022\n"
    )
    mount = find_mount("/dev/sdb1", info)
    assert mount.point == Path("/media/februus/KEY")
    assert mount.options >= {"ro", "noexec", "nosuid", "nodev"}
    assert mount.filesystem == "vfat"


def test_mountinfo_does_not_confuse_similar_devices(tmp_path):
    info = tmp_path / "mountinfo"
    info.write_text("40 25 8:26 / /media/x rw,relatime - vfat /dev/sdb10 rw\n")
    assert find_mount("/dev/sdb1", info) is None


def test_mountinfo_escaped_characters(tmp_path):
    info = tmp_path / "mountinfo"
    info.write_text("40 25 8:17 / /media/a\\040b\\011c\\134d ro - vfat /dev/sdb1 ro\n")
    assert find_mount("/dev/sdb1", info).point == Path("/media/a b\tc\\d")


def test_mountinfo_ignores_broken_lines(tmp_path):
    info = tmp_path / "mountinfo"
    info.write_text("garbage\n40 25 8:17 /\n40 25 8:17 / /m ro - vfat\n")
    assert find_mount("/dev/sdb1", info) is None


def test_already_mounted_partition_is_refused(env):
    # Mounted before Februus (stale or automatic mount): unknown state.
    reader, mountinfo, log = env
    mountinfo.write_text(mountinfo.read_text() + "41 25 8:17 / /media/auto rw - vfat /dev/sdb1 rw\n")
    with pytest.raises(MountError, match="already mounted"):
        with reader.open("/dev/sdb1"):
            pass
    assert not log.exists()  # udisksctl never called


def test_partition_mounted_twice_is_refused(env, monkeypatch):
    # Our mount plus another one appearing at the same time: refused.
    reader, mountinfo, *_ = env
    original = kernel_mount.find_mounts
    calls = []

    def twice(source, mountinfo=None):
        calls.append(source)
        mounts = original(source, mountinfo)
        return mounts * 2 if len(calls) > 1 and mounts else mounts

    monkeypatch.setattr(kernel_mount, "find_mounts", twice)
    with pytest.raises(MountError, match="expected one mount, found 2"):
        with reader.open("/dev/sdb1"):
            pass


def test_mount_not_found_after_mounting(env, monkeypatch):
    reader, *_ = env
    monkeypatch.setattr(kernel_mount, "find_mounts", lambda source, mountinfo=None: [])
    with pytest.raises(MountError, match="expected one mount, found 0"):
        with reader.open("/dev/sdb1"):
            pass
