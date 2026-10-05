"""The small types shared by the checks of a key.

- Inspector: a function ``inspect(device) -> list[Finding]``, one per file
  of ``februus/inspectors/`` (listed in ``inspectors/__init__.py``).
- Analyzer:  an object with ``analyze(file) -> list[Finding]`` for one open
  file (``februus/analyzers/``, chosen in ``[analyzers]`` of the TOML).
- Reader:    an object with ``open(source)`` that gives a folder to read
  (``februus/readers/``: ``kernel_mount`` on a station, ``directory`` for
  development).

SECURITY: nothing here executes, opens or renders a file from a scanned
device. Checks only read bytes.
FR : les contrôles n'exécutent, n'ouvrent ni n'affichent jamais un fichier
de la clé. Ils lisent seulement des octets.
"""

import os
from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from februus.core.config import FINDING_CODE_RE


@dataclass(frozen=True, slots=True)
class Finding:
    """Something a check found. Its color comes from the verdict rules."""

    code: str
    detail: str = ""

    def __post_init__(self) -> None:
        if not FINDING_CODE_RE.match(self.code):
            raise ValueError(f"invalid finding code: {self.code!r}")


@dataclass(frozen=True, slots=True)
class ScannedFile:
    """One file of a key, already opened by the scanner, for the analyzers.

    An analyzer never gets a path it could open: only this descriptor.
    FR : un analyseur ne reçoit jamais un chemin qu'il pourrait ouvrir,
    seulement ce descripteur de fichier déjà ouvert en lecture seule.
    """

    # Path relative to the key, for information only (file extension...).
    # It comes from the key: untrusted text.
    name: str
    # Descriptor of the regular file, read-only. Its offset is shared by
    # all the analyzers: read with ``read_chunks`` / ``os.pread``, or do
    # ``os.lseek(fd, 0, os.SEEK_SET)`` first. Never close it.
    fd: int


class BlockDevice(Protocol):
    """A device (USB key) seen as raw bytes, for the inspectors.

    The station gives it read-only access (udisks2 on the mini-PC, an
    image file in tests). Its content is untrusted.
    """

    # Device name, for information only (for example "/dev/sdb").
    path: str
    # Size in bytes.
    size: int

    def read_at(self, offset: int, length: int) -> bytes:
        """Read up to ``length`` bytes at ``offset`` (fewer at the end)."""
        ...


class Reader(Protocol):
    def open(self, source: str) -> AbstractContextManager[Path]:
        """Give access to the files of ``source`` (read-only).

        Use as ``with reader.open(source) as root:``. The files are
        available under ``root`` until the block ends.
        """
        ...


class Analyzer:
    """Base of the analyzers: ``name`` is the one used in the TOML."""

    name = ""

    def analyze(self, file: ScannedFile) -> list[Finding]:
        """Analyze one open file, reading it only as bytes."""
        raise NotImplementedError

    def version(self) -> str | None:
        """Version of the analyzer data (antivirus signatures...), shown on
        screen and stored with each session. None when not relevant."""
        return None


def read_chunks(fd: int, chunk_size: int) -> Iterator[bytes]:
    """Read an open file from its start as raw bytes, chunk by chunk
    (never interpreted). The offset of the descriptor is not used."""
    offset = 0
    while chunk := os.pread(fd, chunk_size, offset):
        offset += len(chunk)
        yield chunk
