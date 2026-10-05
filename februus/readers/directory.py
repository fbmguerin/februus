"""Reader ``directory``: a local folder, for development and tests.

It does not mount anything and does not make the folder read-only:
never use it on a real station.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class DirectoryReader:
    @contextmanager
    def open(self, source: str) -> Iterator[Path]:
        root = Path(source).resolve()
        if not root.is_dir():
            raise NotADirectoryError(f"not a directory: {source}")
        yield root

