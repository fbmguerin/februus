"""Tests for the ``februus`` command line interface."""

import signal
import subprocess
import sys
import threading
import types
from pathlib import Path

import pytest

from februus import __version__
from februus.cli import _printable, main

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_help_exits_zero_and_shows_program_name(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    assert "usage: februus" in capsys.readouterr().out


def test_version_shows_package_version(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"februus {__version__}"


def test_no_argument_prints_help(capsys):
    assert main([]) == 0
    assert "usage: februus" in capsys.readouterr().out


def test_unknown_option_fails(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--no-such-option"])
    assert exc_info.value.code != 0


def test_printable_escapes_control_characters():
    assert _printable("evil\x1b[2Jname\n.txt") == "evil\\x1b[2Jname\\n.txt"
    assert _printable("été.pdf") == "été.pdf"


def test_python_m_februus_runs():
    result = subprocess.run(
        [sys.executable, "-m", "februus", "--version"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert __version__ in result.stdout


class FakeServer:
    """Stands for ``uvicorn.Server``: waits for the SIGTERM instead of serving."""

    stopped = threading.Event()
    port_in_use = False

    def __init__(self, config):
        self.config = types.SimpleNamespace(bind_socket=self.bind_socket)

    def bind_socket(self):
        if FakeServer.port_in_use:
            raise SystemExit(1)
        return "socket"

    def run(self, sockets):
        FakeServer.stopped.wait(10)


@pytest.fixture
def serving(monkeypatch, tmp_path):
    """Run ``februus serve`` without real servers: returns (config, key_events calls)."""
    config = tmp_path / "dev.toml"
    config.write_text((REPO_ROOT / "config" / "februus.dev.toml").read_text())
    FakeServer.stopped = threading.Event()
    FakeServer.port_in_use = False
    monkeypatch.setattr("februus.web.app.create_app", lambda config, status, scanner_alive, stopping: object())
    monkeypatch.setattr("uvicorn.Config", lambda app, host, port: None)
    monkeypatch.setattr("uvicorn.Server", FakeServer)
    previous = signal.signal(signal.SIGTERM, lambda signum, frame: FakeServer.stopped.set())
    yield config
    signal.signal(signal.SIGTERM, previous)


def test_serve_stops_when_the_key_watcher_fails(monkeypatch, serving):
    # FAIL-CLOSED: without the key watcher the station checks nothing. The
    # screens must say "out of service" and the service must stop (systemd
    # starts it again).
    alive = []

    def broken_events(settle_seconds, poll_seconds):
        raise RuntimeError("udev is gone")
        yield  # makes this a generator, like the real key_events

    monkeypatch.setattr("februus.scanner.udev.key_events", broken_events)
    monkeypatch.setattr(
        "februus.web.app.create_app",
        lambda config, status, scanner_alive, stopping: alive.append(scanner_alive) or object(),
    )
    code = main(["serve", "-c", str(serving)])
    assert FakeServer.stopped.is_set()
    assert code == 1
    assert alive[0]() is False


def test_second_service_never_watches_the_keys(monkeypatch, serving):
    # The port is in use (another service runs): stop before any key is analyzed.
    watched = []
    monkeypatch.setattr("februus.scanner.udev.key_events", lambda *a: watched.append(a) or iter(()))
    FakeServer.port_in_use = True
    with pytest.raises(SystemExit):
        main(["serve", "-c", str(serving)])
    assert watched == []
