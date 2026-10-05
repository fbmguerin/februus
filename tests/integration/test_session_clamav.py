"""Full session on a folder with the real ClamAV analyzer (``pytest -m clamav``)."""

import copy
import tomllib
from pathlib import Path

import pytest

from februus.analyzers.clamav import ClamavAnalyzer
from februus.core.config import parse_config
from februus.core.session import run_session
from februus.core.status import Status
from februus.core.verdict import Color
from februus.readers.directory import DirectoryReader
from tests.integration.test_clamav_scan import SOCKET
from tests.samples import EICAR, encrypted_zip

pytestmark = pytest.mark.clamav

EXAMPLE = Path(__file__).resolve().parents[2] / "config" / "februus.example.toml"


@pytest.fixture
def config(tmp_path):
    if not ClamavAnalyzer(Path(SOCKET), 60).ping():
        pytest.skip(f"clamd does not answer on {SOCKET}")
    with EXAMPLE.open("rb") as file:
        data = copy.deepcopy(tomllib.load(file))
    data["log"]["path"] = str(tmp_path / "keys.jsonl")
    # Production rules and analyzer, with the development reader.
    data["analyzers"]["clamav"] = {"socket": SOCKET, "timeout_seconds": 60}
    return parse_config(data)


def run(config, folder):
    return run_session(config, Status(), DirectoryReader(), str(folder))


def test_clean_folder_is_green(config, tmp_path):
    folder = tmp_path / "key"
    folder.mkdir()
    (folder / "report.txt").write_bytes(b"Quarterly report\n")
    assert run(config, folder).verdict is Color.GREEN


def test_folder_with_eicar_and_encrypted_zip_is_red(config, tmp_path):
    folder = tmp_path / "key"
    (folder / "sub").mkdir(parents=True)
    (folder / "report.txt").write_bytes(b"Quarterly report\n")
    (folder / "sub" / "eicar.com").write_bytes(EICAR)
    (folder / "secret.zip").write_bytes(encrypted_zip())
    result = run(config, folder)
    assert result.verdict is Color.RED
    found = sorted((f.path, f.code) for f in result.findings)
    assert found == [
        ("secret.zip", "archive.encrypted"),
        ("sub/eicar.com", "clamav.detected"),
    ]
