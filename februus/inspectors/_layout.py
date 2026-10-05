"""Read the layout of a device: partition table and file systems.

Shared by the inspectors.

The goal is to see the device as the Linux kernel sees it: the station
mounts what the kernel exposes, so the inspectors must check the same
partitions. The rules below follow the kernel (block/partitions/msdos.c
and efi.c).

SECURITY: every byte comes from the key and is untrusted. Offsets and
counts are checked; anything inconsistent raises ``LayoutError`` (the
session engine turns it into a red finding).
FR : chaque octet vient de la clé : les valeurs sont vérifiées, toute
incohérence lève LayoutError (donc ROUGE).
"""

import struct
import uuid
import zlib
from dataclasses import dataclass

from februus.core.checks import BlockDevice

SECTOR = 512
MBR_SIGNATURE = b"\x55\xaa"
MBR_EXTENDED_TYPES = {0x05, 0x0F, 0x85}
MBR_GPT_PROTECTIVE = 0xEE
MBR_EFI_SYSTEM = 0xEF
MAX_LOGICAL_PARTITIONS = 128
GPT_SIGNATURE = b"EFI PART"
GPT_MAX_ENTRIES = 128
GPT_EFI_SYSTEM = uuid.UUID("c12a7328-f81f-11d2-ba4b-00a0c93ec93b")
GPT_BIOS_BOOT = uuid.UUID("21686148-6449-6e6f-744e-656564454649")
ISO_DESCRIPTORS = 16 * 2048  # ISO 9660 volume descriptors start here.


class LayoutError(Exception):
    """The partition table cannot be read safely."""


@dataclass(frozen=True, slots=True)
class Partition:
    offset: int  # in bytes from the start of the device
    size: int  # in bytes
    # MBR: partition type byte; GPT: type GUID.
    kind: int | uuid.UUID
    active: bool = False  # MBR "boot" flag (0x80)


@dataclass(frozen=True, slots=True)
class Layout:
    # "none": a file system directly on the device (no partition table).
    table: str  # "none", "mbr" or "gpt"
    # Data partitions: MBR primary and logical ones, or GPT entries.
    partitions: tuple[Partition, ...]
    has_extended: bool = False
    # GPT only: the other entries of a "hybrid" MBR (next to the 0xEE one).
    # Old firmwares boot from them, so they are inspected too.
    legacy: tuple[Partition, ...] = ()

    def volumes(self, device_size: int) -> tuple[tuple[int, int], ...]:
        """(offset, size) of each place that may hold a file system."""
        if self.table == "none":
            return ((0, device_size),)
        return tuple((p.offset, p.size) for p in (*self.partitions, *self.legacy))


def read_layout(device: BlockDevice) -> Layout:
    """Partition table of the device (MBR, GPT, or none)."""
    first = device.read_at(0, SECTOR)
    if len(first) < SECTOR or first[510:512] != MBR_SIGNATURE:
        return Layout("none", ())
    # Same rule as the kernel: with the 55 AA signature, the first sector
    # is a partition table, unless a "boot" byte is neither 0x00 nor 0x80
    # (it is then the boot sector of a file system, "superfloppy"). The
    # magic bytes of a file system are NOT used here: a crafted sector can
    # hold both, and the kernel would see the partitions.
    # FR : même règle que le noyau ; les octets « magiques » d'un système
    # de fichiers ne suffisent pas à ignorer une table de partitions.
    if any(first[446 + 16 * i] not in (0x00, 0x80) for i in range(4)):
        return Layout("none", ())
    entries = _mbr_entries(first, base=0)
    if not entries:
        return Layout("none", ())
    if any(p.kind == MBR_GPT_PROTECTIVE for p in entries):
        legacy = tuple(p for p in entries if p.kind != MBR_GPT_PROTECTIVE)
        return Layout("gpt", _gpt_partitions(device), legacy=legacy)
    extended = [p for p in entries if p.kind in MBR_EXTENDED_TYPES]
    logical = [q for p in extended for q in _logical_partitions(device, p)]
    primary = [p for p in entries if p.kind not in MBR_EXTENDED_TYPES]
    return Layout("mbr", tuple(primary + logical), has_extended=bool(extended))


def filesystem_at(device: BlockDevice, offset: int, size: int | None = None) -> str:
    """Type of the file system starting at ``offset``, from its magic
    bytes: "fat", "exfat", "ntfs", "iso9660", "ext", "hfsplus", "apfs",
    "refs" or "unknown". Never reads beyond ``size`` bytes (the partition):
    the magic bytes of the next partition must not be taken for this one.
    FR : ne lit jamais au-delà de la partition."""

    def read(start: int, length: int) -> bytes:
        if size is not None and start + length > size:
            return b""
        return device.read_at(offset + start, length)

    boot = read(0, SECTOR)
    if boot[3:11] == b"NTFS    ":
        return "ntfs"
    if boot[3:11] == b"EXFAT   ":
        return "exfat"
    if boot[3:7] == b"ReFS":
        return "refs"
    if boot[32:36] == b"NXSB":
        return "apfs"
    if boot[510:512] == MBR_SIGNATURE and (
        boot[54:59] in (b"FAT12", b"FAT16", b"FAT  ") or boot[82:87] == b"FAT32"
    ):
        return "fat"
    superblock = read(1024, 64)
    if superblock[56:58] == b"\x53\xef":
        return "ext"
    if superblock[0:2] in (b"H+", b"HX"):
        return "hfsplus"
    if read(ISO_DESCRIPTORS + 1, 5) == b"CD001":
        return "iso9660"
    return "unknown"


def has_el_torito(device: BlockDevice, offset: int = 0, size: int | None = None) -> bool:
    """True if a bootable CD/DVD image (ISO 9660 with an El Torito boot
    record) starts at ``offset``: the whole device (ISO file written with
    ``dd``) or a partition of ``size`` bytes holding such an image."""
    # Boot record: second volume descriptor (sector 17 of 2048 bytes).
    start = ISO_DESCRIPTORS + 2048
    if size is not None and size < start + 32:
        return False  # never read beyond the partition
    record = device.read_at(offset + start, 32)
    return record[0:1] == b"\x00" and record[1:6] == b"CD001" and record[7:30] == (
        b"EL TORITO SPECIFICATION"
    )


def _mbr_entries(sector: bytes, base: int, count: int = 4) -> list[Partition]:
    """Non-empty entries of a MBR (or of an extended boot record); their
    start is relative to ``base`` (bytes)."""
    entries = []
    for index in range(count):
        raw = sector[446 + 16 * index : 446 + 16 * (index + 1)]
        status, kind = raw[0], raw[4]
        start, sectors = struct.unpack_from("<II", raw, 8)
        if kind == 0:
            continue
        if status not in (0x00, 0x80):
            raise LayoutError(f"partition entry {index}: invalid status {status:#x}")
        entries.append(
            Partition(
                offset=base + start * SECTOR,
                size=sectors * SECTOR,
                kind=kind,
                active=status == 0x80,
            )
        )
    return entries


def _logical_partitions(device: BlockDevice, extended: Partition) -> list[Partition]:
    """Logical partitions of an extended partition: a chain of extended
    boot records (EBR). Entry 1 is a partition (relative to its EBR),
    entry 2 points to the next EBR (relative to the extended partition)."""
    partitions: list[Partition] = []
    ebr = extended.offset
    seen: set[int] = set()
    for _ in range(MAX_LOGICAL_PARTITIONS):
        if ebr in seen:
            raise LayoutError("loop in the extended partition")
        seen.add(ebr)
        sector = device.read_at(ebr, SECTOR)
        if len(sector) < SECTOR or sector[510:512] != MBR_SIGNATURE:
            raise LayoutError("invalid extended boot record")
        entries = _mbr_entries(sector, base=ebr, count=2)
        links = [p for p in entries if p.kind in MBR_EXTENDED_TYPES]
        partitions += [p for p in entries if p.kind not in MBR_EXTENDED_TYPES]
        if not links:
            return partitions
        # The link is relative to the start of the extended partition.
        ebr = extended.offset + (links[0].offset - ebr)
    raise LayoutError("too many logical partitions")


def _gpt_partitions(device: BlockDevice) -> tuple[Partition, ...]:
    """Partitions of the GPT. Like the kernel: the primary header (second
    block) if it is valid (signature, checksums), else the backup header
    (last block). Both invalid: LayoutError."""
    for block in (512, 4096):
        for lba in (1, device.size // block - 1):
            partitions = _read_gpt(device, block, lba)
            if partitions is not None:
                return partitions
    raise LayoutError("protective MBR without a valid GPT")


def _read_gpt(device: BlockDevice, block: int, lba: int) -> tuple[Partition, ...] | None:
    """Partitions of the GPT header at ``lba``, or None if it is not a
    valid header (signature, size, position or checksums wrong)."""
    if lba < 1:
        return None
    header = device.read_at(lba * block, block)
    if header[0:8] != GPT_SIGNATURE or len(header) < 92:
        return None
    header_size, header_crc = struct.unpack_from("<II", header, 12)
    (my_lba,) = struct.unpack_from("<Q", header, 24)
    if not 92 <= header_size <= block or my_lba != lba:
        return None
    blank_crc = header[:16] + bytes(4) + header[20:header_size]
    if zlib.crc32(blank_crc) != header_crc:
        return None
    entries_lba, count, entry_size, entries_crc = struct.unpack_from("<QIII", header, 72)
    if not 0 < count <= GPT_MAX_ENTRIES or not 128 <= entry_size <= 1024:
        return None
    table = device.read_at(entries_lba * block, count * entry_size)
    if entries_lba < 1 or len(table) < count * entry_size:
        return None
    if zlib.crc32(table) != entries_crc:
        return None
    partitions = []
    for index in range(count):
        raw = table[index * entry_size : (index + 1) * entry_size]
        if raw[0:16] == bytes(16):
            continue
        first, last = struct.unpack_from("<QQ", raw, 32)
        if last < first:
            raise LayoutError(f"GPT entry {index}: last block before first")
        partitions.append(
            Partition(
                offset=first * block,
                size=(last - first + 1) * block,
                kind=uuid.UUID(bytes_le=bytes(raw[0:16])),
            )
        )
    return tuple(partitions)
