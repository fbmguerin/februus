"""Tests for the key log (one JSON line per key)."""

import json
import os

import pytest

from februus.core import keylog


def entry(**changes):
    base = {"started": "2026-10-04T10:00:00+00:00", "verdict": "green", "files": 3,
            "bytes": 100, "removed": False, "problems": []}
    return {**base, **changes}


def test_one_line_per_entry(tmp_path):
    path = tmp_path / "keys.jsonl"
    keylog.append(path, entry())
    keylog.append(path, entry(verdict="red"))
    assert len(path.read_text().splitlines()) == 2
    assert [e["verdict"] for e in keylog.read(path)] == ["green", "red"]


def test_a_hostile_file_name_cannot_add_a_line(tmp_path):
    path = tmp_path / "keys.jsonl"
    name = "a\n{\"verdict\": \"green\"}\r\x1b[2J"
    keylog.append(path, entry(problems=[{"path": name, "code": "x.y", "color": "red"}]))
    assert len(path.read_text().splitlines()) == 1
    [read] = keylog.read(path)
    assert read["problems"][0]["path"] == name


def test_the_file_is_created_private(tmp_path):
    path = tmp_path / "keys.jsonl"
    keylog.append(path, entry())
    umask = os.umask(0)
    os.umask(umask)
    assert path.stat().st_mode & 0o777 == 0o640 & ~umask


def test_a_symbolic_link_is_not_followed(tmp_path):
    target = tmp_path / "target"
    target.write_text("")
    link = tmp_path / "keys.jsonl"
    link.symlink_to(target)
    with pytest.raises(OSError):
        keylog.append(link, entry())
    assert target.read_text() == ""


def test_missing_file_is_an_empty_log(tmp_path):
    assert list(keylog.read(tmp_path / "none.jsonl")) == []
    assert keylog.statistics(tmp_path / "none.jsonl", None)["sessions"] == 0


def test_bad_lines_are_skipped(tmp_path, caplog):
    path = tmp_path / "keys.jsonl"
    keylog.append(path, entry())
    with path.open("a") as file:
        file.write("not json\n[1, 2]\n\n")
    keylog.append(path, entry(verdict="orange"))
    assert [e["verdict"] for e in keylog.read(path)] == ["green", "orange"]
    assert "skipped" in caplog.text


def test_statistics(tmp_path):
    path = tmp_path / "keys.jsonl"
    keylog.append(path, entry(started="2026-10-01T10:00:00+00:00"))
    keylog.append(path, entry(verdict="orange"))
    keylog.append(path, entry(verdict="red", removed=True, files=1, bytes=5))
    keylog.append(path, entry(verdict="strange", files="many", bytes=True))
    numbers = keylog.statistics(path, None)
    assert numbers == {"sessions": 4, "green": 1, "orange": 1, "red": 1, "removed": 1,
                       "files": 7, "bytes": 205}
    assert keylog.statistics(path, "2026-10-02")["sessions"] == 3
    assert keylog.statistics(path, "2999-01-01")["sessions"] == 0


def test_safe_text_for_names_that_are_not_utf8():
    assert keylog.safe_text(os.fsdecode(b"bad\xffname")) == "bad\\xffname"
    assert len(keylog.safe_text("x" * 1000)) == keylog.MAX_PATH_CHARS


def test_entries_are_json_objects(tmp_path):
    path = tmp_path / "keys.jsonl"
    keylog.append(path, entry())
    assert isinstance(json.loads(path.read_text()), dict)
