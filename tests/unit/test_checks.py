"""Tests for the plain checks: the analyzer list, the directory reader and
the fake analyzer (development)."""

from pathlib import Path

import pytest

from februus.analyzers import build_analyzers, fake
from februus.analyzers.clamav import ClamavAnalyzer
from februus.core.checks import Finding
from februus.core.config import AnalyzersConfig, ClamavConfig, FakeConfig
from februus.readers.directory import DirectoryReader
from tests.scanned import scanned

MARKER = "FEBRUUS-FAKE-MALWARE"
FAKE = FakeConfig(
    marker=MARKER,
    slow_marker="FEBRUUS-FAKE-SLOW",
    error_marker="FEBRUUS-FAKE-ERROR",
    delay_ms=0,
)
CLAMAV = ClamavConfig(socket=Path("/run/clamav/clamd.ctl"), timeout_seconds=60)


def make_fake() -> fake.FakeAnalyzer:
    [analyzer] = build_analyzers(AnalyzersConfig(("fake",), None, FAKE))
    return analyzer


def test_the_enabled_analyzers_are_built_in_order():
    config = AnalyzersConfig(("fake", "clamav"), CLAMAV, FAKE)
    assert [a.name for a in build_analyzers(config)] == ["fake", "clamav"]
    clamav = build_analyzers(config)[1]
    assert isinstance(clamav, ClamavAnalyzer)
    assert (clamav.socket_path, clamav.timeout_seconds) == (Path("/run/clamav/clamd.ctl"), 60)


def test_an_analyzer_without_settings_is_never_skipped():
    # FAIL-CLOSED: never run with fewer analyzers than asked.
    with pytest.raises(ValueError, match="clamav"):
        build_analyzers(AnalyzersConfig(("clamav",), None, None))


def test_finding_code_is_checked():
    assert Finding("clamav.detected").code == "clamav.detected"
    with pytest.raises(ValueError):
        Finding("Not A Code")


def test_directory_reader(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    with DirectoryReader().open(str(tmp_path)) as root:
        assert (root / "a.txt").read_bytes() == b"hello"


def test_directory_reader_refuses_a_file(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("hello")
    with pytest.raises(NotADirectoryError):
        with DirectoryReader().open(str(path)):
            pass


def test_fake_analyzer_clean_file(tmp_path):
    path = tmp_path / "clean.txt"
    path.write_bytes(b"nothing to see")
    with scanned(path) as file:
        assert make_fake().analyze(file) == [Finding("fake.clean")]


def test_fake_analyzer_detects_marker(tmp_path):
    path = tmp_path / "bad.bin"
    path.write_bytes(b"\x00\x01" + MARKER.encode() + b"\xff")
    with scanned(path) as file:
        assert [f.code for f in make_fake().analyze(file)] == ["fake.detected"]


def test_fake_analyzer_marker_split_between_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(fake, "CHUNK_SIZE", 4)
    path = tmp_path / "split.bin"
    path.write_bytes(b"abc" + MARKER.encode() + b"xyz")
    with scanned(path) as file:
        assert [f.code for f in make_fake().analyze(file)] == ["fake.detected"]


def test_fake_analyzer_empty_file(tmp_path):
    path = tmp_path / "empty"
    path.write_bytes(b"")
    with scanned(path) as file:
        assert make_fake().analyze(file) == [Finding("fake.clean")]


def test_fake_analyzer_error_marker(tmp_path):
    path = tmp_path / "boom"
    path.write_bytes(b"FEBRUUS-FAKE-ERROR")
    with scanned(path) as file, pytest.raises(fake.FakeAnalyzerError):
        make_fake().analyze(file)
