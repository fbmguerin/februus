"""The key log: one line (JSON) per key analyzed.

Written when a session ends, only appended to, read by ``februus stats``.
It holds no file name except the files that gave an orange or red finding
(text from the key: untrusted, made safe, never interpreted).
FR : une ligne par clé ; aucun nom de fichier sauf ceux qui ont provoqué
un constat orange ou rouge.
"""

import json
import logging
import os
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)

MAX_PROBLEMS = 20
MAX_PATH_CHARS = 200


def now() -> str:
    """Current time, ISO 8601 in UTC."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def safe_text(text: object, limit: int = MAX_PATH_CHARS) -> str:
    """A name from a key as printable text, even if it is not valid UTF-8."""
    raw = os.fsencode(str(text))
    return raw.decode("utf-8", errors="backslashreplace")[:limit]


def append(path: Path, entry: Mapping[str, Any]) -> None:
    """Add one line. The line is flushed to the disk before returning.

    ``json.dumps`` escapes every control character: a hostile file name
    can never add a second line.
    FR : json échappe les retours à la ligne : un nom piégé ne peut pas
    ajouter de fausse ligne.
    """
    line = json.dumps(entry, sort_keys=True) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o640)
    try:
        os.write(fd, line.encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def read(path: Path) -> Iterator[dict[str, Any]]:
    """The entries of the log. A missing file is an empty log; a line that
    cannot be read is skipped (and reported in the journal)."""
    try:
        file = path.open(encoding="utf-8")
    except FileNotFoundError:
        return
    with file:
        for number, line in enumerate(file, 1):
            try:
                entry = json.loads(line)
            except ValueError:
                entry = None
            if isinstance(entry, dict):
                yield entry
            else:
                LOG.warning("%s line %d: not a log entry, skipped", path, number)


def statistics(path: Path, since: str | None) -> dict[str, int]:
    """Counts by verdict, files and bytes analyzed, for the keys started
    at or after ``since`` (ISO date; None: all)."""
    numbers = dict.fromkeys(("sessions", "green", "orange", "red", "removed", "files", "bytes"), 0)
    for entry in read(path):
        if since is not None and str(entry.get("started", "")) < since:
            continue
        numbers["sessions"] += 1
        verdict = entry.get("verdict")
        if verdict in ("green", "orange", "red"):
            numbers[verdict] += 1
        numbers["removed"] += bool(entry.get("removed"))
        for key in ("files", "bytes"):
            value = entry.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                numbers[key] += value
    return numbers
