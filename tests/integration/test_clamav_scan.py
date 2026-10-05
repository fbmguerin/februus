"""ClamAV analyzer against a real clamd (``pytest -m clamav``).

Skipped when clamd does not answer. Socket: $FEBRUUS_CLAMD_SOCKET or
/run/clamav/clamd.ctl. clamd must use deploy/clamav/clamd-februus.conf.
"""

import os
from pathlib import Path

import pytest

from februus.analyzers.clamav import ClamavAnalyzer
from februus.core.verdict import Color, compute_verdict
from tests.scanned import scanned
from tests.samples import EICAR, encrypted_pdf, encrypted_zip, nested_zip

pytestmark = pytest.mark.clamav

SOCKET = os.environ.get("FEBRUUS_CLAMD_SOCKET", "/run/clamav/clamd.ctl")
RULES = {
    "clamav.detected": Color.RED,
    "archive.encrypted": Color.RED,
    "pdf.encrypted": Color.RED,
    "scan.limit_exceeded": Color.RED,
}


@pytest.fixture(scope="module")
def analyzer():
    analyzer = ClamavAnalyzer(Path(SOCKET), 60)
    if not analyzer.ping():
        pytest.skip(f"clamd does not answer on {SOCKET}")
    return analyzer


def scan(analyzer, tmp_path, name, content):
    path = tmp_path / name
    path.write_bytes(content)
    try:
        with scanned(path) as file:
            return analyzer.analyze(file)
    finally:
        path.unlink()


def test_eicar_is_red(analyzer, tmp_path):
    findings = scan(analyzer, tmp_path, "eicar.com", EICAR)
    assert [f.code for f in findings] == ["clamav.detected"]
    assert "Eicar" in findings[0].detail
    assert compute_verdict([f.code for f in findings], RULES) is Color.RED


def test_clean_file_is_green(analyzer, tmp_path):
    findings = scan(analyzer, tmp_path, "letter.txt", b"Dear colleague,\n")
    assert findings == []
    assert compute_verdict([], RULES) is Color.GREEN


def test_encrypted_zip_is_red(analyzer, tmp_path):
    findings = scan(analyzer, tmp_path, "secret.zip", encrypted_zip())
    assert [f.code for f in findings] == ["archive.encrypted"]


def test_encrypted_pdf_is_red(analyzer, tmp_path):
    findings = scan(analyzer, tmp_path, "secret.pdf", encrypted_pdf())
    assert [f.code for f in findings] == ["pdf.encrypted"]


def test_limit_exceeded_is_red(analyzer, tmp_path):
    findings = scan(analyzer, tmp_path, "deep.zip", nested_zip(25))
    assert [f.code for f in findings] == ["scan.limit_exceeded"]


def test_normal_archive_is_green(analyzer, tmp_path):
    assert scan(analyzer, tmp_path, "normal.zip", nested_zip(3)) == []
