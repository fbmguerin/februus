"""Inspector ``partitions``: a key with several partitions is unusual.

Finding ``device.multi_partition`` (orange in the example rules) when the
partition table holds more than one partition (logical ones included),
an extended partition, or a "hybrid" MBR next to a GPT.
"""

from februus.core.checks import BlockDevice, Finding
from februus.inspectors._layout import read_layout


def inspect(device: BlockDevice) -> list[Finding]:
    layout = read_layout(device)
    count = len(layout.partitions)
    if count > 1 or layout.has_extended or layout.legacy:
        detail = f"{layout.table}: {count} partition(s)"
        if layout.has_extended:
            detail += " + extended partition"
        if layout.legacy:
            detail += f" + hybrid MBR ({len(layout.legacy)} entries)"
        return [Finding("device.multi_partition", detail)]
    return []
