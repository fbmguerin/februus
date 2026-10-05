"""Inspector ``filesystem``: every volume must use a supported file system.

Finding ``filesystem.unsupported`` (red in the example rules) for each
volume whose file system is not FAT, exFAT or NTFS (for example ext4,
HFS+, an ISO image, or unknown data). The key is then not mounted.
"""

from februus.core.checks import BlockDevice, Finding
from februus.inspectors._layout import filesystem_at, read_layout

# The file systems the station reads (see FILESYSTEMS in readers/kernel_mount.py).
SUPPORTED = frozenset({"fat", "exfat", "ntfs"})


def inspect(device: BlockDevice) -> list[Finding]:
    layout = read_layout(device)
    volumes = layout.volumes(device.size)
    if not volumes:
        return [Finding("filesystem.unsupported", "no partition")]
    findings = []
    for number, (offset, size) in enumerate(volumes, start=1):
        kind = filesystem_at(device, offset, size)
        if kind not in SUPPORTED:
            findings.append(Finding("filesystem.unsupported", f"volume {number}: {kind}"))
    return findings
