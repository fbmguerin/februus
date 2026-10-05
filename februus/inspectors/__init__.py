"""The inspectors: they look at the raw key before any file is read.

Each one is a function ``inspect(device) -> list[Finding]``. The list below
is the list run on every key, in this order; it is not configurable.
"""

from collections.abc import Callable

from februus.core.checks import BlockDevice, Finding
from februus.inspectors import bootable, filesystem, partitions

INSPECTORS: tuple[tuple[str, Callable[[BlockDevice], list[Finding]]], ...] = (
    ("partitions", partitions.inspect),
    ("bootable", bootable.inspect),
    ("filesystem", filesystem.inspect),
)
