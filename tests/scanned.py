"""Test helper: open a file the way the scanner does, for an analyzer."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from februus.core.files import open_regular
from februus.core.checks import ScannedFile


@contextmanager
def scanned(path: Path) -> Iterator[ScannedFile]:
    """``path`` as the open file an analyzer receives."""
    fd = open_regular(path)
    try:
        yield ScannedFile(name=path.name, fd=fd)
    finally:
        os.close(fd)
