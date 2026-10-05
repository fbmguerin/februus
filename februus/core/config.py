"""Load and validate the Februus configuration (TOML).

The main file (``/etc/februus/februus.toml``) is shared by all stations.
Optional local overrides live in ``conf.d/*.toml`` next to it and are
merged in alphabetical order.

Validation is strict: a missing key, an unknown key or a wrong type is an
error. There are no default values in the code: every tunable value lives
in the TOML file (see ``config/februus.example.toml``).
"""

import re
import socket
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from februus.core.verdict import Color

DEFAULT_CONFIG_PATH = Path("/etc/februus/februus.toml")
CONF_D_NAME = "conf.d"

# Finding codes look like "clamav.detected" or "device.multi_partition".
FINDING_CODE_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
# The analyzers that exist (februus/analyzers/): the TOML chooses among them.
ANALYZER_NAMES = ("clamav", "fake")
ANALYZER_NAME_RE = re.compile(f"^({'|'.join(ANALYZER_NAMES)})$")
# The station name is shown on screen: printable, limited.
STATION_NAME_MAX_LENGTH = 64


class ConfigError(Exception):
    """The configuration is invalid. ``errors`` lists every problem found."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass(frozen=True, slots=True)
class StationConfig:
    name: str


@dataclass(frozen=True, slots=True)
class LogConfig:
    path: Path


@dataclass(frozen=True, slots=True)
class ScanConfig:
    file_timeout_seconds: int
    session_timeout_minutes: int
    long_scan_warning_minutes: int
    progress_update_seconds: int
    cancel_check_ms: int
    max_entries: int
    mount_timeout_seconds: int


@dataclass(frozen=True, slots=True)
class ScannerConfig:
    settle_seconds: int
    removed_screen_seconds: int
    poll_interval_ms: int


@dataclass(frozen=True, slots=True)
class VerdictConfig:
    rules: Mapping[str, Color]


@dataclass(frozen=True, slots=True)
class WebConfig:
    host: str
    port: int
    preview_screens: bool
    poll_interval_ms: int
    stream_seconds: int
    tip_change_seconds: int
    sounds: bool


@dataclass(frozen=True, slots=True)
class ClamavConfig:
    socket: Path
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class FakeConfig:
    marker: str
    slow_marker: str
    error_marker: str
    delay_ms: int


@dataclass(frozen=True, slots=True)
class AnalyzersConfig:
    """The analyzers to run on every file, with their settings."""

    names: tuple[str, ...]
    clamav: ClamavConfig | None
    fake: FakeConfig | None


@dataclass(frozen=True, slots=True)
class Config:
    station: StationConfig
    log: LogConfig
    scan: ScanConfig
    scanner: ScannerConfig
    verdict: VerdictConfig
    web: WebConfig
    analyzers: AnalyzersConfig
    # Files read, in merge order (main file first).
    sources: tuple[Path, ...]


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Read the main file and its ``conf.d`` overrides, then validate.

    Raises ``ConfigError`` with every problem found.
    """
    sources = [path, *sorted((path.parent / CONF_D_NAME).glob("*.toml"))]
    data: dict[str, Any] = {}
    for source in sources:
        _merge(data, _read_toml(source))
    return parse_config(data, tuple(sources))


def parse_config(data: Mapping[str, Any], sources: tuple[Path, ...] = ()) -> Config:
    """Validate raw TOML data and build a ``Config``."""
    errors: list[str] = []
    root = TableReader(data, "", errors)

    station = root.get_table("station")
    name = station.get_optional_str("name")
    if name is not None and not name.strip():
        station.error("name", "must not be empty (remove it to use the hostname)")
    elif name is not None and not _is_station_name(name):
        station.error(
            "name",
            f"must be printable text of at most {STATION_NAME_MAX_LENGTH} characters",
        )
    station.finish()

    log = root.get_table("log")
    log_path = log.get_path("path")
    log.finish()

    scan = root.get_table("scan")
    file_timeout = scan.get_int("file_timeout_seconds", minimum=1)
    session_timeout = scan.get_int("session_timeout_minutes", minimum=1)
    long_scan_warning = scan.get_int("long_scan_warning_minutes", minimum=0)
    progress_update = scan.get_int("progress_update_seconds", minimum=1)
    cancel_check = scan.get_int("cancel_check_ms", minimum=10)
    max_entries = scan.get_int("max_entries", minimum=1)
    mount_timeout = scan.get_int("mount_timeout_seconds", minimum=1)
    scan.finish()

    scanner = root.get_table("scanner")
    settle = scanner.get_int("settle_seconds", minimum=0)
    removed_screen = scanner.get_int("removed_screen_seconds", minimum=1)
    scanner_poll = scanner.get_int("poll_interval_ms", minimum=10)
    scanner.finish()

    verdict = root.get_table("verdict")
    rules = _parse_rules(verdict.get_table("rules"))
    verdict.finish()

    web = root.get_table("web")
    host = web.get_str("host")
    port = web.get_int("port", minimum=1)
    if port is not None and port > 65535:
        web.error("port", "must be <= 65535")
    preview_screens = web.get_bool("preview_screens")
    poll_interval = web.get_int("poll_interval_ms", minimum=100)
    stream_seconds = web.get_int("stream_seconds", minimum=1)
    tip_change = web.get_int("tip_change_seconds", minimum=1)
    sounds = web.get_bool("sounds")
    web.finish()

    analyzers = _parse_analyzers(root.get_table("analyzers"))

    root.finish()
    if errors:
        raise ConfigError(errors)

    return Config(
        station=StationConfig(name=name or _hostname()),
        log=LogConfig(path=log_path),
        scan=ScanConfig(
            file_timeout_seconds=file_timeout,
            session_timeout_minutes=session_timeout,
            long_scan_warning_minutes=long_scan_warning,
            progress_update_seconds=progress_update,
            cancel_check_ms=cancel_check,
            max_entries=max_entries,
            mount_timeout_seconds=mount_timeout,
        ),
        scanner=ScannerConfig(
            settle_seconds=settle,
            removed_screen_seconds=removed_screen,
            poll_interval_ms=scanner_poll,
        ),
        verdict=VerdictConfig(rules=rules),
        web=WebConfig(
            host=host,
            port=port,
            preview_screens=preview_screens,
            poll_interval_ms=poll_interval,
            stream_seconds=stream_seconds,
            tip_change_seconds=tip_change,
            sounds=sounds,
        ),
        analyzers=analyzers,
        sources=sources,
    )


def _is_station_name(name: str) -> bool:
    return 0 < len(name) <= STATION_NAME_MAX_LENGTH and name.isprintable()


def _hostname() -> str:
    """System host name, used when no station name is configured."""
    name = socket.gethostname()
    if not _is_station_name(name):
        raise ConfigError(["station.name: the hostname cannot be used, set a name"])
    return name


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except FileNotFoundError:
        raise ConfigError([f"{path}: file not found"]) from None
    except OSError as exc:
        raise ConfigError([f"{path}: cannot read file ({exc.strerror})"]) from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError([f"{path}: invalid TOML ({exc})"]) from None


def _merge(base: dict[str, Any], override: Mapping[str, Any]) -> None:
    """Merge ``override`` into ``base``: tables are merged, values replaced."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value


def _parse_analyzers(table: "TableReader") -> AnalyzersConfig:
    """``enabled`` lists the analyzers to run; each one has its own table
    (``[analyzers.clamav]``), required when enabled, refused otherwise."""
    names = table.get_str_list(
        "enabled", ANALYZER_NAME_RE, f"one of {', '.join(ANALYZER_NAMES)}"
    )
    # FAIL-CLOSED: without an analyzer, nothing would be checked and every
    # key would look clean.
    # FR: sans analyseur, rien ne serait vérifié et toutes les clés
    # paraîtraient saines.
    if names == []:
        table.error("enabled", "must list at least one analyzer")
    clamav = fake = None
    for name in ANALYZER_NAMES:
        if names is None or name not in names:
            # If the list is invalid, nothing more can be said about the tables.
            if name in table.keys():
                table.get_table(name)  # marks it as read: only one error
                if names is not None:
                    table.error(name, "settings of an analyzer that is not enabled")
            continue
        options = table.get_table(name)
        if name == "clamav":
            clamav = ClamavConfig(
                socket=options.get_path("socket"),
                timeout_seconds=options.get_int("timeout_seconds", minimum=1),
            )
        else:
            fake = _parse_fake(options)
        options.finish()
    table.finish()
    return AnalyzersConfig(names=tuple(names or ()), clamav=clamav, fake=fake)


def _parse_fake(options: "TableReader") -> FakeConfig:
    markers = {}
    for key in ("marker", "slow_marker", "error_marker"):
        value = options.get_str(key)
        if value is not None and not value:
            options.error(key, "must not be empty")
        markers[key] = value or ""
    return FakeConfig(
        marker=markers["marker"],
        slow_marker=markers["slow_marker"],
        error_marker=markers["error_marker"],
        delay_ms=options.get_int("delay_ms", minimum=0),
    )


def _parse_rules(rules: "TableReader") -> dict[str, Color]:
    parsed: dict[str, Color] = {}
    for code in rules.keys():
        if not FINDING_CODE_RE.match(code):
            rules.error(code, "is not a valid finding code (like 'clamav.detected')")
        color = rules.get_str(code)
        if color is None:
            continue
        try:
            parsed[code] = Color(color)
        except ValueError:
            allowed = ", ".join(c.value for c in Color)
            rules.error(code, f"'{color}' is not a color ({allowed})")
    rules.finish()
    return parsed


class TableReader:
    """One TOML table being validated. Records errors instead of raising,
    so that ``februus config check`` can report every problem at once."""

    def __init__(
        self, data: Any, path: str, errors: list[str], silent: bool = False
    ) -> None:
        self._path = path
        self._errors = errors
        # A silent table stands for a missing or invalid table that was
        # already reported: do not report each of its keys again.
        self._silent = silent
        self._used: set[str] = set()
        self._data: Mapping[str, Any] = data if isinstance(data, Mapping) else {}

    def keys(self) -> list[str]:
        return list(self._data)

    def error(self, key: str, message: str) -> None:
        if not self._silent:
            self._errors.append(f"{self._key_path(key)}: {message}")

    def get_table(self, key: str) -> "TableReader":
        value = self._get(key, dict, "a table")
        return TableReader(value, self._key_path(key), self._errors, silent=value is None)

    def get_str(self, key: str) -> str | None:
        return self._get(key, str, "a string")

    def get_optional_str(self, key: str) -> str | None:
        if key not in self._data:
            return None
        return self.get_str(key)

    def get_path(self, key: str) -> Path | None:
        value = self.get_str(key)
        if value is None:
            return None
        if not value.startswith("/"):
            self.error(key, "must be an absolute path")
            return None
        return Path(value)

    def get_bool(self, key: str) -> bool | None:
        return self._get(key, bool, "true or false")

    def get_int(self, key: str, minimum: int) -> int | None:
        # bool is a subclass of int in Python: reject it explicitly.
        value = self._get(key, int, "an integer", reject=bool)
        if value is not None and value < minimum:
            self.error(key, f"must be >= {minimum}")
            return None
        return value

    def get_str_list(
        self, key: str, pattern: re.Pattern[str], what: str
    ) -> list[str] | None:
        value = self._get(key, list, "a list")
        if value is None:
            return None
        ok = True
        for item in value:
            if not isinstance(item, str) or not pattern.match(item):
                self.error(key, f"{item!r} is not {what}")
                ok = False
        if ok and len(set(value)) != len(value):
            self.error(key, "contains duplicates")
            ok = False
        return value if ok else None

    def finish(self) -> None:
        """Report keys that were never read: unknown keys are errors."""
        for key in self._data:
            if key not in self._used:
                self.error(key, "unknown key")

    def _get(
        self, key: str, kind: type, what: str, reject: type | None = None
    ) -> Any:
        self._used.add(key)
        if key not in self._data:
            self.error(key, "missing")
            return None
        value = self._data[key]
        if not isinstance(value, kind) or (reject and isinstance(value, reject)):
            self.error(key, f"must be {what}")
            return None
        return value

    def _key_path(self, key: str) -> str:
        if not key:
            return self._path
        # Keys containing dots (finding codes) are quoted, as in TOML.
        name = f'"{key}"' if "." in key else key
        return f"{self._path}.{name}" if self._path else name
