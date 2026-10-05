"""Tests for the device inspectors, on disk images built in memory."""

import random
import shutil
import struct
import subprocess

import pytest

from februus.core.devices import ImageDevice
from februus.core.session import run_inspectors
from februus.core.verdict import Color, compute_verdict
from februus.inspectors import INSPECTORS, bootable, filesystem, partitions
from februus.inspectors._layout import LayoutError, filesystem_at, read_layout
from tests import disk_images as img


@pytest.fixture
def device(tmp_path):
    def make(content: bytes) -> ImageDevice:
        path = tmp_path / "key.img"
        path.write_bytes(bytes(content))
        return ImageDevice(path)

    return make


def codes(inspect, device):
    return [f.code for f in inspect(device)]


# --- Layout ---------------------------------------------------------------


@pytest.mark.parametrize("kind", ["fat", "ntfs", "exfat"])
def test_superfloppy_has_no_partition_table(device, kind):
    layout = read_layout(device(img.superfloppy(kind)))
    assert (layout.table, layout.partitions) == ("none", ())


def test_mbr_layout(device):
    layout = read_layout(device(img.mbr([(0x0C, 2048, 8192, False)])))
    assert layout.table == "mbr"
    [partition] = layout.partitions
    assert (partition.offset, partition.size, partition.kind) == (2048 * 512, 8192 * 512, 0x0C)


def test_gpt_layout(device):
    layout = read_layout(device(img.gpt([(img.MS_BASIC_DATA, 2048, 10239)])))
    assert layout.table == "gpt"
    assert [p.kind for p in layout.partitions] == [img.MS_BASIC_DATA]


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("fat", "fat"), ("ntfs", "ntfs"), ("exfat", "exfat"), ("ext", "ext"),
     ("iso9660", "iso9660"), ("empty", "unknown")],
)
def test_filesystem_detection(device, kind, expected):
    image = img.blank()
    img.put_filesystem(image, 0, kind)
    assert filesystem_at(device(image), 0) == expected


def test_broken_gpt_raises(device):
    image = img.mbr([(0xEE, 1, 0xFFFF, False)], filesystems=["empty"])
    with pytest.raises(LayoutError):
        read_layout(device(image))


def test_gpt_with_both_headers_corrupted_raises(device):
    image = img.gpt([(img.MS_BASIC_DATA, 2048, 4095)])
    last = len(image) // 512 - 1
    image[512 + 80 : 512 + 84] = (100_000).to_bytes(4, "little")  # primary
    image[last * 512 + 20] ^= 0xFF  # backup: header checksum now wrong
    with pytest.raises(LayoutError):
        read_layout(device(image))


def test_backup_gpt_is_used_when_the_primary_is_corrupted(device):
    # Like the kernel and UEFI: a bad primary header (checksum) is
    # replaced by the backup one, which must be inspected.
    image = img.gpt([(img.MS_BASIC_DATA, 2048, 4095)],
                    backup=[(img.EFI_SYSTEM, 2048, 4095)])
    image[512 + 16] ^= 0xFF  # primary header checksum now wrong
    assert [p.kind for p in read_layout(device(image)).partitions] == [img.EFI_SYSTEM]
    assert codes(bootable.inspect, device(image)) == ["device.bootable"]


def test_valid_primary_gpt_is_preferred(device):
    image = img.gpt([(img.MS_BASIC_DATA, 2048, 4095)],
                    backup=[(img.EFI_SYSTEM, 2048, 4095)])
    assert [p.kind for p in read_layout(device(image)).partitions] == [img.MS_BASIC_DATA]


def test_invalid_boot_byte_means_no_partition_table(device):
    # Kernel rule: a "boot" byte other than 00/80 means a file system
    # boot sector, not a partition table. Nothing usable here: red.
    image = img.mbr([(0x0C, 2048, 8192, False)])
    image[446] = 0x42
    assert read_layout(device(image)).table == "none"
    assert codes(filesystem.inspect, device(image)) == ["filesystem.unsupported"]


def test_file_system_magic_does_not_hide_a_partition_table(device):
    # Crafted first sector: NTFS magic AND a valid partition table with an
    # EFI system partition. The kernel sees the partitions: so must we.
    image = img.mbr([(0xEF, 2048, 4096, True), (0x0C, 6144, 4096, False)],
                    filesystems=["fat", "fat"])
    image[3:11] = b"NTFS    "
    layout = read_layout(device(image))
    assert (layout.table, len(layout.partitions)) == ("mbr", 2)
    assert codes(bootable.inspect, device(image)) == ["device.bootable"]
    assert codes(partitions.inspect, device(image)) == ["device.multi_partition"]


def test_hybrid_mbr_entries_are_inspected(device):
    image = img.gpt([(img.MS_BASIC_DATA, 2048, 4095)], hybrid=[(0x0C, 2048, 2048, True)])
    assert codes(bootable.inspect, device(image)) == ["device.boot_flag"]
    assert codes(partitions.inspect, device(image)) == ["device.multi_partition"]


def test_logical_partitions_are_inspected(device):
    image = img.mbr([(0x0C, 2048, 4096, False), (0x0F, 8192, 8192, False)],
                    filesystems=["fat", "empty"])
    img.with_logical(image, 8192, [(0x0C, 63, 1000), (0x83, 63, 1000)])
    img.put_filesystem(image, (8192 + 63) * 512, "fat")
    img.put_filesystem(image, (8192 + 2048 + 63) * 512, "ext")
    layout = read_layout(device(image))
    assert len(layout.partitions) == 3
    [finding] = filesystem.inspect(device(image))
    assert (finding.code, finding.detail) == ("filesystem.unsupported", "volume 3: ext")


def test_extended_partition_loop_raises(device):
    image = img.mbr([(0x0F, 2048, 8192, False)], filesystems=["empty"])
    img.with_logical(image, 2048, [(0x0C, 63, 100)])
    # The EBR points back to itself.
    link = struct.pack("<B3sB3sII", 0, bytes(3), 0x05, bytes(3), 0, 100)
    image[2048 * 512 + 462 : 2048 * 512 + 478] = link
    with pytest.raises(LayoutError, match="loop"):
        read_layout(device(image))


def test_tiny_device(device):
    assert read_layout(device(b"\x00" * 10)).table == "none"


# --- partitions ---------------------------------------------------------------


def test_single_partition_is_fine(device):
    assert codes(partitions.inspect, device(img.mbr([(0x0C, 2048, 8192, False)]))) == []


def test_superfloppy_is_fine(device):
    assert codes(partitions.inspect, device(img.superfloppy())) == []


def test_two_partitions(device):
    image = img.mbr([(0x0C, 2048, 4096, False), (0x07, 6144, 4096, False)],
                    filesystems=["fat", "ntfs"])
    assert codes(partitions.inspect, device(image)) == ["device.multi_partition"]


def test_extended_partition(device):
    image = img.mbr([(0x0C, 2048, 4096, False), (0x0F, 6144, 4096, False)],
                    filesystems=["fat", "empty"])
    img.with_logical(image, 6144, [(0x0C, 63, 1000)])
    assert codes(partitions.inspect, device(image)) == ["device.multi_partition"]


def test_extended_partition_without_valid_ebr_raises(device):
    image = img.mbr([(0x0C, 2048, 4096, False), (0x0F, 6144, 4096, False)],
                    filesystems=["fat", "empty"])
    with pytest.raises(LayoutError):
        read_layout(device(image))


def test_two_gpt_partitions(device):
    image = img.gpt([(img.MS_BASIC_DATA, 2048, 4095), (img.MS_BASIC_DATA, 4096, 8191)])
    assert codes(partitions.inspect, device(image)) == ["device.multi_partition"]


# --- bootable ---------------------------------------------------------------


def test_normal_key_is_not_bootable(device):
    assert codes(bootable.inspect, device(img.mbr([(0x0C, 2048, 8192, False)]))) == []
    assert codes(bootable.inspect, device(img.superfloppy())) == []


def test_iso_written_with_dd_is_bootable(device):
    assert codes(bootable.inspect, device(img.bootable_iso())) == ["device.bootable"]


def test_iso_inside_a_partition_is_bootable(device):
    # Real key seen on the mini-PC: one "Linux" partition holding a Debian
    # live image.
    image = img.mbr([(0x83, 2048, 8192, False)], filesystems=["empty"])
    img.put_bootable_iso(image, 2048 * 512)
    assert codes(bootable.inspect, device(image)) == ["device.bootable"]


def test_el_torito_is_never_read_beyond_its_partition(device):
    # The boot record of a 16 KiB partition would be in the next one.
    image = img.mbr([(0x0C, 2048, 32, False), (0x0C, 2080, 8192, False)])
    img.put_bootable_iso(image, 2048 * 512)
    assert "device.bootable" not in codes(bootable.inspect, device(image))


def test_efi_system_partition_is_bootable(device):
    image = img.gpt([(img.EFI_SYSTEM, 2048, 4095), (img.MS_BASIC_DATA, 4096, 8191)])
    assert codes(bootable.inspect, device(image)) == ["device.bootable"]


def test_bios_boot_partition_is_bootable(device):
    image = img.gpt([(img.BIOS_BOOT, 2048, 4095)], filesystems=["empty"])
    assert codes(bootable.inspect, device(image)) == ["device.bootable"]


def test_mbr_efi_partition_is_bootable(device):
    assert codes(bootable.inspect, device(img.mbr([(0xEF, 2048, 8192, False)]))) == [
        "device.bootable"
    ]


def test_active_flag_has_its_own_code(device):
    assert codes(bootable.inspect, device(img.mbr([(0x0C, 2048, 8192, True)]))) == [
        "device.boot_flag"
    ]


# --- filesystem ---------------------------------------------------------------


@pytest.mark.parametrize("kind", ["fat", "ntfs", "exfat"])
def test_supported_filesystems(device, kind):
    assert codes(filesystem.inspect, device(img.superfloppy(kind))) == []


@pytest.mark.parametrize("kind", ["ext", "iso9660", "empty"])
def test_unsupported_filesystems(device, kind):
    image = img.blank()
    img.put_filesystem(image, 0, kind)
    assert codes(filesystem.inspect, device(image)) == ["filesystem.unsupported"]


def test_every_partition_is_checked(device):
    image = img.mbr([(0x0C, 2048, 4096, False), (0x83, 6144, 4096, False)],
                    filesystems=["fat", "ext"])
    [finding] = filesystem.inspect(device(image))
    assert (finding.code, finding.detail) == ("filesystem.unsupported", "volume 2: ext")


def test_partition_table_without_partition(device):
    image = img.blank()
    image[510:512] = b"\x55\xaa"
    assert codes(filesystem.inspect, device(image)) == ["filesystem.unsupported"]


def test_the_list_of_inspectors_is_fixed():
    assert [name for name, _ in INSPECTORS] == ["partitions", "bootable", "filesystem"]


@pytest.mark.skipif(not shutil.which("mkfs.vfat"), reason="mkfs.vfat not installed")
def test_real_fat_image(device, tmp_path):
    path = tmp_path / "real.img"
    with path.open("wb") as file:
        file.truncate(40 * img.MiB)
    subprocess.run(["mkfs.vfat", str(path)], check=True, capture_output=True)
    real = ImageDevice(path)
    assert read_layout(real).table == "none"
    assert codes(filesystem.inspect, real) == []
    assert codes(bootable.inspect, real) == []
    assert codes(partitions.inspect, real) == []


# --- Fuzzing: random and corrupted images ---------------------------------

RULES = {
    "device.bootable": Color.RED, "device.boot_flag": Color.RED,
    "device.multi_partition": Color.ORANGE, "filesystem.unsupported": Color.RED,
}


def test_random_bytes_never_crash_and_are_never_green(device):
    rng = random.Random(1234)
    for _ in range(200):
        image = bytearray(rng.randbytes(64 * 1024))
        if rng.random() < 0.5:
            image[510:512] = b"\x55\xaa"  # looks like a partition table
        results = run_inspectors(device(image))
        assert compute_verdict([code for _, code, _ in results], RULES) is not Color.GREEN


@pytest.mark.parametrize(
    "build",
    [
        lambda: img.mbr([(0x0C, 2048, 4096, False), (0x07, 6144, 4096, False)],
                        filesystems=["fat", "ntfs"]),
        lambda: img.gpt([(img.MS_BASIC_DATA, 2048, 4095), (img.EFI_SYSTEM, 4096, 8191)]),
        lambda: img.superfloppy("fat"),
        lambda: img.with_logical(
            img.mbr([(0x0C, 2048, 4096, False), (0x0F, 6144, 4096, False)],
                    filesystems=["fat", "empty"]),
            6144, [(0x0C, 63, 1000), (0x83, 63, 1000)],
        ),
    ],
)
def test_corrupted_tables_never_crash(device, build):
    # Flip random bytes in the first sectors: the inspectors must always
    # answer (findings or internal.error), never raise.
    rng = random.Random(42)
    for _ in range(150):
        image = build()
        for _ in range(rng.randint(1, 8)):
            image[rng.randrange(0, 4096)] = rng.randrange(256)
        dev = device(image)
        # The parser only ever raises LayoutError (no IndexError, struct
        # error...): a crafted table can never surprise the code.
        try:
            layout = read_layout(dev)
            for offset, _ in layout.volumes(dev.size):
                filesystem_at(dev, offset)
        except LayoutError:
            pass
        results = run_inspectors(dev)
        assert all(isinstance(code, str) for _, code, _ in results)


def test_filesystem_is_never_read_beyond_its_partition(device):
    # A 1-sector partition: the ext magic (at +1080) lies in the data
    # after it, so it does not belong to this partition.
    image = img.mbr([(0x0C, 2048, 1, False)], filesystems=["empty"])
    img.put_filesystem(image, 2048 * 512, "ext")
    dev = device(image)
    assert filesystem_at(dev, 2048 * 512) == "ext"  # without the bound
    assert filesystem_at(dev, 2048 * 512, 512) == "unknown"
    assert codes(filesystem.inspect, dev) == ["filesystem.unsupported"]


def test_empty_partition_is_unsupported(device):
    image = img.mbr([(0x0C, 2048, 0, False)], filesystems=["empty"])
    assert codes(filesystem.inspect, device(image)) == ["filesystem.unsupported"]
