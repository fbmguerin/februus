"""Block devices for the inspectors (see ``checks.BlockDevice``).

- ``ImageDevice`` reads a disk image file: tests and development
  (``februus inspect <image>``).
- ``KernelDevice`` reads a real USB key (``/dev/sdb``). The ``februus``
  account may read USB keys thanks to the udev rule
  ``deploy/udev/70-februus.rules`` (read only, never write).
"""

import os
import re
from pathlib import Path

# Only whole SCSI/USB disks: "/dev/sdb", never a path chosen by a key.
DISK_RE = re.compile(r"^/dev/sd[a-z]{1,3}$")
SYSFS_BLOCK = Path("/sys/class/block")
SYSFS_SECTOR = 512  # sysfs always counts sizes in 512-byte sectors


class ImageDevice:
    """A disk image file seen as a block device (read-only access)."""

    def __init__(self, path: Path) -> None:
        self.path = str(path)
        self.size = path.stat().st_size
        self._path = path

    def read_at(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0:
            raise ValueError("negative offset or length")
        fd = os.open(self._path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            return os.pread(fd, length, offset)
        finally:
            os.close(fd)


class KernelDevice:
    """A USB key seen through the kernel, opened read-only for each read."""

    def __init__(self, path: str, sysfs: Path = SYSFS_BLOCK) -> None:
        if not DISK_RE.match(path):
            raise ValueError(f"not a disk device: {path!r}")
        name = path.removeprefix("/dev/")
        self.path = path
        self.size = int((sysfs / name / "size").read_text()) * SYSFS_SECTOR

    def read_at(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0:
            raise ValueError("negative offset or length")
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            return os.pread(fd, length, offset)
        finally:
            os.close(fd)
