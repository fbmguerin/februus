"""Small disk images built in memory, to test the inspectors.

Only the bytes the inspectors look at are written (partition tables,
boot sectors, magic numbers): enough to be recognized, nothing more.
"""

import struct
import uuid
import zlib

SECTOR = 512
MiB = 1024 * 1024
EFI_SYSTEM = uuid.UUID("c12a7328-f81f-11d2-ba4b-00a0c93ec93b")
BIOS_BOOT = uuid.UUID("21686148-6449-6e6f-744e-656564454649")
MS_BASIC_DATA = uuid.UUID("ebd0a0a2-b9e5-4433-87c0-68b6d0bfe5ac")


def blank(size: int = 8 * MiB) -> bytearray:
    return bytearray(size)


def fat32_boot_sector() -> bytes:
    sector = bytearray(SECTOR)
    sector[0:3] = b"\xeb\x58\x90"
    sector[3:11] = b"MSDOS5.0"
    sector[82:90] = b"FAT32   "
    sector[510:512] = b"\x55\xaa"
    return bytes(sector)


def boot_sector(kind: str) -> bytes:
    """First sector of a file system of this kind."""
    sector = bytearray(SECTOR)
    if kind == "fat":
        return fat32_boot_sector()
    if kind == "ntfs":
        sector[3:11] = b"NTFS    "
    elif kind == "exfat":
        sector[3:11] = b"EXFAT   "
    sector[510:512] = b"\x55\xaa"
    return bytes(sector)


def put_filesystem(image: bytearray, offset: int, kind: str) -> None:
    if kind in ("fat", "ntfs", "exfat"):
        image[offset : offset + SECTOR] = boot_sector(kind)
    elif kind == "ext":
        image[offset + 1080 : offset + 1082] = b"\x53\xef"
    elif kind == "iso9660":
        image[offset + 0x8001 : offset + 0x8006] = b"CD001"
    elif kind != "empty":
        raise ValueError(kind)


def superfloppy(kind: str = "fat") -> bytearray:
    """A file system directly on the device, no partition table."""
    image = blank()
    put_filesystem(image, 0, kind)
    return image


def mbr(partitions: list[tuple[int, int, int, bool]], filesystems=None) -> bytearray:
    """MBR with (type, start sector, sector count, active) entries."""
    image = blank()
    for index, (kind, start, count, active) in enumerate(partitions):
        entry = struct.pack(
            "<B3sB3sII", 0x80 if active else 0, b"\0\0\0", kind, b"\0\0\0", start, count
        )
        image[446 + 16 * index : 462 + 16 * index] = entry
    image[510:512] = b"\x55\xaa"
    for index, kind in enumerate(filesystems or ["fat"] * len(partitions)):
        if partitions[index][1]:
            put_filesystem(image, partitions[index][1] * SECTOR, kind)
    return image


def gpt_tables(partitions: list[tuple[uuid.UUID, int, int]], my_lba: int,
               entries_lba: int) -> tuple[bytes, bytes]:
    """A GPT header and its entry table, with valid checksums."""
    table = bytearray(128 * 128)
    for index, (kind, first, last) in enumerate(partitions):
        entry = bytearray(128)
        entry[0:16] = kind.bytes_le
        entry[16:32] = uuid.uuid4().bytes_le
        struct.pack_into("<QQ", entry, 32, first, last)
        table[index * 128 : (index + 1) * 128] = entry
    header = bytearray(92)
    header[0:8] = b"EFI PART"
    struct.pack_into("<II", header, 8, 0x00010000, 92)
    struct.pack_into("<Q", header, 24, my_lba)
    struct.pack_into("<QIII", header, 72, entries_lba, 128, 128, zlib.crc32(table))
    struct.pack_into("<I", header, 16, zlib.crc32(header))
    return bytes(header), bytes(table)


def gpt(partitions: list[tuple[uuid.UUID, int, int]], filesystems=None,
        backup: list[tuple[uuid.UUID, int, int]] | None = None,
        hybrid: list[tuple[int, int, int, bool]] = ()) -> bytearray:
    """Protective MBR + primary GPT with (type GUID, first LBA, last LBA)
    entries. ``backup``: other entries for the backup GPT (last block).
    ``hybrid``: more MBR entries next to the protective one."""
    image = mbr([(0xEE, 1, 0xFFFF, False), *hybrid], filesystems=["empty"] * (1 + len(hybrid)))
    header, table = gpt_tables(partitions, my_lba=1, entries_lba=2)
    image[SECTOR : SECTOR + 92] = header
    image[2 * SECTOR : 2 * SECTOR + len(table)] = table
    last = len(image) // SECTOR - 1
    header, table = gpt_tables(backup or partitions, my_lba=last, entries_lba=last - 32)
    image[last * SECTOR : last * SECTOR + 92] = header
    image[(last - 32) * SECTOR : (last - 32) * SECTOR + len(table)] = table
    for index, kind in enumerate(filesystems or ["fat"] * len(partitions)):
        put_filesystem(image, partitions[index][1] * SECTOR, kind)
    return image


def with_logical(image: bytearray, extended_start: int,
                 logical: list[tuple[int, int, int]]) -> bytearray:
    """Write the chain of extended boot records: ``logical`` holds
    (type, start sector relative to its EBR, sector count); each EBR is
    placed 2048 sectors after the previous one."""
    for index, (kind, start, count) in enumerate(logical):
        ebr = (extended_start + index * 2048) * SECTOR
        entry = struct.pack("<B3sB3sII", 0, b"\0\0\0", kind, b"\0\0\0", start, count)
        image[ebr + 446 : ebr + 462] = entry
        if index + 1 < len(logical):
            link = struct.pack(
                "<B3sB3sII", 0, b"\0\0\0", 0x05, b"\0\0\0", (index + 1) * 2048, 2048
            )
            image[ebr + 462 : ebr + 478] = link
        image[ebr + 510 : ebr + 512] = b"\x55\xaa"
    return image


def put_bootable_iso(image: bytearray, offset: int) -> None:
    """ISO 9660 volume descriptors with an El Torito boot record."""
    image[offset + 0x8000 : offset + 0x8006] = b"\x01CD001"
    image[offset + 0x8800 : offset + 0x8806] = b"\x00CD001"
    image[offset + 0x8807 : offset + 0x8807 + 23] = b"EL TORITO SPECIFICATION"


def bootable_iso() -> bytearray:
    """ISO 9660 image with an El Torito boot record (as written by dd)."""
    image = blank()
    put_bootable_iso(image, 0)
    return image
