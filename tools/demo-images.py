#!/usr/bin/env python3
"""Write small disk images to demonstrate "februus inspect" without a key.

Usage: python3 tools/demo-images.py <folder>
Then:  februus inspect -c config/februus.dev.toml <folder>/<image>

The images only hold the bytes the inspectors read (partition tables,
boot sectors), built by the same helpers as the unit tests. They contain
no files and no code.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests import disk_images as img  # noqa: E402

IMAGES = {
    # Expected result: green.
    "clean-key.img": lambda: img.superfloppy("fat"),
    # Orange: device.multi_partition.
    "two-partitions.img": lambda: img.mbr(
        [(0x0C, 2048, 4096, False), (0x0C, 6144, 4096, False)]
    ),
    # Red: device.bootable (an ISO written on a key with dd).
    "bootable-iso.img": img.bootable_iso,
    # Red: device.bootable (EFI system partition).
    "efi-key.img": lambda: img.gpt(
        [(img.EFI_SYSTEM, 2048, 4095), (img.MS_BASIC_DATA, 4096, 12287)]
    ),
    # Red: filesystem.unsupported (ext4, a Linux file system).
    "linux-key.img": lambda: img.superfloppy("ext"),
}


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    folder = Path(sys.argv[1])
    folder.mkdir(parents=True, exist_ok=True)
    for name, build in IMAGES.items():
        (folder / name).write_bytes(bytes(build()))
        print(folder / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
