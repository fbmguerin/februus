"""Tests for configuration loading and validation."""

import copy
import shutil
import socket
import tomllib
from pathlib import Path

import pytest

from februus.cli import main
from februus.core.config import ConfigError, load_config, parse_config
from februus.core.verdict import Color

EXAMPLE = Path(__file__).resolve().parents[2] / "config" / "februus.example.toml"
DEV = EXAMPLE.with_name("februus.dev.toml")


@pytest.fixture
def data() -> dict:
    """Raw data of the example configuration, safe to modify."""
    with EXAMPLE.open("rb") as file:
        return copy.deepcopy(tomllib.load(file))


def errors_of(data: dict) -> list[str]:
    with pytest.raises(ConfigError) as exc_info:
        parse_config(data)
    return exc_info.value.errors


def test_example_config_is_valid():
    config = load_config(EXAMPLE)
    assert config.sources == (EXAMPLE,)
    assert config.verdict.rules["clamav.detected"] is Color.RED
    assert config.verdict.rules["device.multi_partition"] is Color.ORANGE
    assert config.analyzers.names == ("clamav",)
    assert config.analyzers.clamav.socket.name == "clamd.ctl"


def test_station_name_defaults_to_hostname(data):
    data["station"].pop("name", None)
    assert parse_config(data).station.name == socket.gethostname()


def test_station_name_from_config(data):
    data["station"]["name"] = "f1"
    assert parse_config(data).station.name == "f1"


def test_empty_station_name_is_rejected(data):
    data["station"]["name"] = "  "
    assert errors_of(data) == [
        "station.name: must not be empty (remove it to use the hostname)"
    ]


def test_missing_key_is_rejected(data):
    del data["scan"]["file_timeout_seconds"]
    assert errors_of(data) == ["scan.file_timeout_seconds: missing"]


def test_missing_section_is_reported_once(data):
    del data["scan"]
    assert errors_of(data) == ["scan: missing"]


def test_unknown_key_is_rejected(data):
    data["scan"]["max_speed"] = 3
    assert errors_of(data) == ["scan.max_speed: unknown key"]


def test_unknown_section_is_rejected(data):
    data["extra"] = {}
    assert errors_of(data) == ["extra: unknown key"]


def test_wrong_type_is_rejected(data):
    data["scan"]["file_timeout_seconds"] = "120"
    assert errors_of(data) == ["scan.file_timeout_seconds: must be an integer"]


def test_bool_is_not_an_integer(data):
    data["scan"]["max_entries"] = True
    assert errors_of(data) == ["scan.max_entries: must be an integer"]


def test_integer_below_minimum_is_rejected(data):
    data["scan"]["session_timeout_minutes"] = 0
    assert errors_of(data) == ["scan.session_timeout_minutes: must be >= 1"]


def test_removed_settings_are_unknown_keys(data):
    # An old configuration (SQLite, analyzer service, web account...) is
    # refused, never half understood.
    data["database"] = {"path": "/var/lib/februus/februus.db"}
    data["analyzer_service"] = {"enabled": False}
    data["web"]["require_scanner"] = True
    data["scan"]["eta_history_sessions"] = 20
    assert errors_of(data) == [
        "scan.eta_history_sessions: unknown key",
        "web.require_scanner: unknown key",
        "database: unknown key",
        "analyzer_service: unknown key",
    ]


def test_relative_log_path_is_rejected(data):
    data["log"]["path"] = "keys.jsonl"
    assert errors_of(data) == ["log.path: must be an absolute path"]


def test_invalid_color_is_rejected(data):
    data["verdict"]["rules"]["clamav.detected"] = "blue"
    assert errors_of(data) == [
        'verdict.rules."clamav.detected": \'blue\' is not a color (green, orange, red)'
    ]


def test_invalid_finding_code_is_rejected(data):
    data["verdict"]["rules"]["NoDot"] = "red"
    assert errors_of(data) == [
        "verdict.rules.NoDot: is not a valid finding code (like 'clamav.detected')"
    ]


def test_duplicate_analyzers_are_rejected(data):
    data["analyzers"]["enabled"] = ["clamav", "clamav"]
    assert errors_of(data) == ["analyzers.enabled: contains duplicates"]


def test_at_least_one_analyzer(data):
    # FAIL-CLOSED: no analyzer would mean every key looks clean.
    data["analyzers"]["enabled"] = []
    del data["analyzers"]["clamav"]
    assert errors_of(data) == ["analyzers.enabled: must list at least one analyzer"]


def test_unknown_analyzer_is_rejected(data):
    data["analyzers"]["enabled"] = ["clamav", "yara"]
    assert errors_of(data) == ["analyzers.enabled: 'yara' is not one of clamav, fake"]


def test_an_enabled_analyzer_needs_its_settings(data):
    del data["analyzers"]["clamav"]
    assert errors_of(data) == ["analyzers.clamav: missing"]


def test_settings_of_an_analyzer_that_is_not_enabled_are_rejected(data):
    data["analyzers"]["fake"] = {"marker": "x", "slow_marker": "y", "error_marker": "z", "delay_ms": 0}
    assert errors_of(data) == ["analyzers.fake: settings of an analyzer that is not enabled"]


def test_analyzer_settings_are_validated(data):
    data["analyzers"]["clamav"] = {"socket": "clamd.ctl"}
    assert errors_of(data) == [
        "analyzers.clamav.socket: must be an absolute path",
        "analyzers.clamav.timeout_seconds: missing",
    ]


def test_fake_markers_must_not_be_empty(data):
    data["analyzers"] = {"enabled": ["fake"], "fake": {
        "marker": "", "slow_marker": "y", "error_marker": "z", "delay_ms": 0}}
    assert errors_of(data) == ["analyzers.fake.marker: must not be empty"]


def test_removed_module_tables_are_unknown_keys(data):
    # The old plugin settings are refused, never half understood.
    data["modules"] = {"readers": ["kernel_mount"]}
    data["module"] = {"clamav": {"socket": "/run/clamav/clamd.ctl"}}
    assert errors_of(data) == ["modules: unknown key", "module: unknown key"]


def test_mount_timeout_is_required(data):
    del data["scan"]["mount_timeout_seconds"]
    assert errors_of(data) == ["scan.mount_timeout_seconds: missing"]


def test_all_errors_are_reported_at_once(data):
    del data["log"]
    data["scan"]["file_timeout_seconds"] = -1
    data["web"]["sounds"] = "yes"
    assert errors_of(data) == [
        "log: missing",
        "scan.file_timeout_seconds: must be >= 1",
        "web.sounds: must be true or false",
    ]


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="file not found"):
        load_config(tmp_path / "februus.toml")


def test_invalid_toml(tmp_path):
    path = tmp_path / "februus.toml"
    path.write_text("[scan\n")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(path)


def test_conf_d_overrides_are_merged_in_order(tmp_path):
    path = tmp_path / "februus.toml"
    shutil.copy(EXAMPLE, path)
    conf_d = tmp_path / "conf.d"
    conf_d.mkdir()
    (conf_d / "10-station.toml").write_text('[station]\nname = "first"\n')
    (conf_d / "20-station.toml").write_text(
        '[station]\nname = "second"\n[verdict.rules]\n"device.multi_partition" = "red"\n'
    )
    (conf_d / "notes.txt").write_text("not a toml file, ignored")

    config = load_config(path)

    assert config.station.name == "second"
    # Merged, not replaced: other rules are kept.
    assert config.verdict.rules["device.multi_partition"] is Color.RED
    assert config.verdict.rules["clamav.detected"] is Color.RED
    assert config.sources == (
        path,
        conf_d / "10-station.toml",
        conf_d / "20-station.toml",
    )


def test_invalid_override_is_rejected(tmp_path):
    path = tmp_path / "februus.toml"
    shutil.copy(EXAMPLE, path)
    (tmp_path / "conf.d").mkdir()
    (tmp_path / "conf.d" / "local.toml").write_text("[scan]\nfile_timeout_seconds = 0\n")
    with pytest.raises(ConfigError, match="must be >= 1"):
        load_config(path)


def test_dev_config_is_valid():
    config = load_config(DEV)
    assert config.analyzers.names == ("fake",)
    assert config.analyzers.fake.marker == "FEBRUUS-FAKE-MALWARE"


def test_cli_config_check_ok(capsys):
    assert main(["config", "check", "--config", str(DEV)]) == 0
    out = capsys.readouterr().out
    assert "Configuration OK" in out
    assert "Analyzers: fake" in out


def test_cli_production_example_is_valid(capsys):
    assert main(["config", "check", "--config", str(EXAMPLE)]) == 0
    assert "Analyzers: clamav" in capsys.readouterr().out


def test_cli_config_check_reports_unknown_analyzers(tmp_path, capsys):
    path = tmp_path / "februus.toml"
    path.write_text(EXAMPLE.read_text().replace('enabled = ["clamav"]', 'enabled = ["clamav", "yara"]'))
    assert main(["config", "check", "--config", str(path)]) == 1
    assert "'yara' is not one of clamav, fake" in capsys.readouterr().err


def test_cli_config_check_invalid(tmp_path, capsys):
    path = tmp_path / "februus.toml"
    path.write_text("[station]\n")
    assert main(["config", "check", "-c", str(path)]) == 1
    err = capsys.readouterr().err
    assert "Configuration INVALID" in err
    assert "  - log: missing" in err


@pytest.mark.parametrize("name", ["x" * 65, "evil\x1b[2J"])
def test_station_name_must_be_short_and_printable(data, name):
    data["station"]["name"] = name
    assert errors_of(data) == [
        "station.name: must be printable text of at most 64 characters"
    ]


def test_long_french_station_name_is_accepted(data):
    data["station"]["name"] = "Préfecture de la Moselle - accueil, bâtiment A"
    assert parse_config(data).station.name.startswith("Préfecture")


def test_max_file_mb_matches_the_clamd_limit():
    """Februus stops a file before clamd would: the two limits are equal."""
    root = Path(__file__).resolve().parents[2]
    clamd = (root / "deploy" / "clamav" / "clamd-februus.conf").read_text()
    with (root / "config" / "februus.example.toml").open("rb") as file:
        max_file_mb = tomllib.load(file)["scan"]["max_file_mb"]
    assert f"\nMaxFileSize {max_file_mb}M\n" in clamd


def test_file_timeout_fits_in_the_clamd_scan_time():
    """clamd must not stop a file before Februus would (a clearer finding)."""
    root = Path(__file__).resolve().parents[2]
    clamd = (root / "deploy" / "clamav" / "clamd-februus.conf").read_text()
    with (root / "config" / "februus.example.toml").open("rb") as file:
        timeout = tomllib.load(file)["scan"]["file_timeout_seconds"]
    scan_time_ms = int(clamd.split("\nMaxScanTime ", 1)[1].split()[0])
    assert scan_time_ms >= timeout * 1000
