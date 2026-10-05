"""Inspector ``bootable``: a key able to start a computer is refused.

- ``device.bootable``: bootable CD/DVD image written on the key or in one
  of its partitions (ISO 9660 with an El Torito boot record), EFI system
  partition, BIOS boot partition.
- ``device.boot_flag``: a MBR partition marked "active" only. Weaker sign:
  some keys are sold with this flag. Separate code, so that its color can
  be tuned in the TOML after tests with real keys.
"""

from februus.core.checks import BlockDevice, Finding
from februus.inspectors._layout import (
    GPT_BIOS_BOOT,
    GPT_EFI_SYSTEM,
    MBR_EFI_SYSTEM,
    has_el_torito,
    read_layout,
)


def inspect(device: BlockDevice) -> list[Finding]:
    findings = []
    if has_el_torito(device):
        findings.append(Finding("device.bootable", "bootable CD/DVD image (El Torito)"))
    layout = read_layout(device)
    for partition in (*layout.partitions, *layout.legacy):
        if partition.kind in (GPT_EFI_SYSTEM, MBR_EFI_SYSTEM):
            findings.append(Finding("device.bootable", "EFI system partition"))
        elif partition.kind == GPT_BIOS_BOOT:
            findings.append(Finding("device.bootable", "BIOS boot partition"))
        elif partition.active:
            findings.append(Finding("device.boot_flag", "active MBR partition"))
        # Seen on a real key: a Debian live image inside a partition.
        if has_el_torito(device, partition.offset, partition.size):
            findings.append(
                Finding("device.bootable", "bootable CD/DVD image in a partition (El Torito)")
            )
    return findings
