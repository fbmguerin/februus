"""Reader ``kernel_mount``: mount a partition of a real USB key with udisks2.

udisks2 (``udisksctl``) mounts the partition for the ``februus`` account,
without any root code in Februus (decision D7). The polkit rule and
``mount_options.conf`` in ``deploy/udisks2`` allow it only for this
account and only with safe options.

SECURITY: after the mount, the real options are read back from
``/proc/self/mountinfo``: ``ro,noexec,nosuid,nodev``. Anything else: the
partition is unmounted and the session is red. Nothing is ever written
on the key.
FR : après le montage, les options réelles sont relues ; si
ro,noexec,nosuid,nodev manque, la partition est démontée (ROUGE). Rien
n'est jamais écrit sur la clé.
"""

import logging
import re
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


LOG = logging.getLogger(__name__)

# A partition (or a whole disk without partition table) of a USB key.
SOURCE_RE = re.compile(r"^/dev/sd[a-z]{1,3}[0-9]{0,3}$")
READ_ONLY = ("ro", "noexec", "nosuid", "nodev")
# Mount types accepted (ntfs3: kernel NTFS driver; fuseblk: ntfs-3g). The
# file systems the station reads: FAT, exFAT, NTFS.
FILESYSTEMS = frozenset({"vfat", "exfat", "ntfs3", "fuseblk"})
UDISKSCTL = "/usr/bin/udisksctl"
MOUNTINFO = Path("/proc/self/mountinfo")


class MountError(Exception):
    """The partition could not be mounted safely."""


@dataclass(frozen=True, slots=True)
class Mount:
    point: Path
    options: frozenset[str]
    filesystem: str


class KernelMountReader:
    def __init__(
        self, timeout_seconds: float, check_seconds: float, udisksctl: str = UDISKSCTL
    ) -> None:
        """``timeout_seconds``: longest wait for one udisksctl command.
        ``check_seconds``: how often to check that the key is still there
        while a command runs."""
        self.udisksctl = udisksctl
        self.timeout = timeout_seconds
        self.check_seconds = check_seconds

    @contextmanager
    def open(self, source: str) -> Iterator[Path]:
        if not SOURCE_RE.match(source):
            raise MountError(f"not a USB partition: {source!r}")
        mount = self._mount(source)
        try:
            yield mount.point
        finally:
            # An unmount error must not change the verdict: the key is
            # read-only and the station forgets it when it is removed.
            self._unmount(source)

    def _mount(self, source: str) -> Mount:
        if find_mounts(source):
            # Already mounted (stale mount, automount...): unknown state.
            # FR : déjà montée ailleurs : état inconnu, refusé.
            raise MountError(f"{source}: already mounted before Februus")
        self._run("mount", source, "--options", ",".join(READ_ONLY))
        mounts = find_mounts(source)
        if len(mounts) != 1:
            self._unmount(source)
            raise MountError(f"{source}: expected one mount, found {len(mounts)}")
        mount = mounts[0]
        missing = set(READ_ONLY) - mount.options
        if missing or mount.filesystem not in FILESYSTEMS:
            # FAIL-CLOSED / FR : options ou type inattendus : on démonte.
            self._unmount(source)
            raise MountError(
                f"{source}: unsafe mount (missing {sorted(missing)},"
                f" file system {mount.filesystem!r})"
            )
        return mount

    def _unmount(self, source: str) -> None:
        """Unmount, never raise: an error is only logged."""
        try:
            self._run("unmount", source)
        except MountError:
            LOG.warning("could not unmount %s", source, exc_info=True)

    def _run(self, action: str, source: str, *options: str) -> None:
        """Run ``udisksctl <action>`` on the partition ``source``."""
        command = [str(self.udisksctl), action, "--block-device", source, *options,
                   "--no-user-interaction"]
        deadline = time.monotonic() + self.timeout
        try:
            process = subprocess.Popen(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
            )
        except OSError as exc:
            raise MountError(f"udisksctl {action} failed: {exc}") from exc
        with process:
            while True:
                try:
                    _, stderr = process.communicate(timeout=self.check_seconds)
                    break
                except subprocess.TimeoutExpired:
                    # Seen on a real key: when the key is pulled out during
                    # an unmount, udisksctl waits about 20 s before failing.
                    # FR : clé retirée pendant la commande : on n'attend pas.
                    removed = not device_exists(source)
                    if removed or time.monotonic() >= deadline:
                        process.kill()
                        reason = (
                            f"{source} was removed" if removed
                            else f"no answer after {self.timeout} s"
                        )
                        raise MountError(f"udisksctl {action} failed: {reason}") from None
        if process.returncode != 0:
            raise MountError(f"udisksctl {action} failed: {stderr.strip()[:300]}")


def device_exists(source: str) -> bool:
    """True while the kernel still knows the partition (key plugged in)."""
    return Path(source).exists()


def find_mount(source: str, mountinfo: Path | None = None) -> Mount | None:
    """The mount of ``source`` if there is exactly one, else None."""
    mounts = find_mounts(source, mountinfo)
    return mounts[0] if len(mounts) == 1 else None


def find_mounts(source: str, mountinfo: Path | None = None) -> list[Mount]:
    """Every mount of ``source`` (mount point, options, file system), read
    from mountinfo: the truth of the kernel, not what was asked."""
    mounts = []
    for line in (mountinfo or MOUNTINFO).read_text().splitlines():
        # Fields: id parent major:minor root point options [optional...] -
        # fstype source super-options
        left, separator, right = line.partition(" - ")
        if not separator:
            continue
        fields, after = left.split(), right.split()
        if len(fields) < 6 or len(after) < 3 or after[1] != source:
            continue
        mounts.append(
            Mount(
                point=Path(_unescape(fields[4])),
                options=frozenset(fields[5].split(",")),
                filesystem=after[0],
            )
        )
    return mounts


def _unescape(text: str) -> str:
    """mountinfo writes spaces and some characters as octal (\\040)."""
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), text)

