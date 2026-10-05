"""Unit tests for the ClamAV analyzer, with a fake clamd (no ClamAV needed)."""

import os
import socket
import threading

import pytest

from februus.analyzers.clamav import ClamavAnalyzer, ClamdError, parse_reply
from tests.scanned import scanned


@pytest.mark.parametrize(
    ("reply", "code", "detail"),
    [
        ("fd[5]: Eicar-Test-Signature FOUND", "clamav.detected", "Eicar-Test-Signature"),
        ("fd[5]: Heuristics.Encrypted.Zip FOUND", "archive.encrypted", "Heuristics.Encrypted.Zip"),
        ("fd[5]: Heuristics.Encrypted.RAR FOUND", "archive.encrypted", "Heuristics.Encrypted.RAR"),
        ("fd[5]: Heuristics.Encrypted.PDF FOUND", "pdf.encrypted", "Heuristics.Encrypted.PDF"),
        (
            "fd[5]: Heuristics.Limits.Exceeded.MaxFileSize FOUND",
            "scan.limit_exceeded",
            "Heuristics.Limits.Exceeded.MaxFileSize",
        ),
    ],
)
def test_found_replies(reply, code, detail):
    [finding] = parse_reply(reply)
    assert (finding.code, finding.detail) == (code, detail)


def test_ok_reply_has_no_finding():
    assert parse_reply("fd[5]: OK") == []


@pytest.mark.parametrize(
    "reply",
    [
        "fd[5]: lstat() failed: Permission denied. ERROR",
        "fd[5]: something new",
        "garbage",
        "",
    ],
)
def test_other_replies_raise(reply):
    # FAIL-CLOSED: anything that is not OK or FOUND is an error, never clean.
    with pytest.raises(ClamdError):
        parse_reply(reply)


class FakeClamd:
    """Unix socket server answering one canned reply per connection."""

    def __init__(self, path, reply: bytes):
        self.reply = reply
        self.commands: list[bytes] = []
        self.received_fd_content: list[bytes] = []
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(path))
        self.server.listen()
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with conn:
                command = conn.recv(8)
                self.commands.append(command)
                if command == b"zFILDES\0":
                    _, fds, _, _ = socket.recv_fds(conn, 1, 1)
                    with os.fdopen(fds[0], "rb") as file:
                        self.received_fd_content.append(file.read())
                conn.sendall(self.reply)

    def close(self):
        self.server.close()


@pytest.fixture
def make_analyzer(tmp_path):
    servers = []

    def make(reply: bytes):
        socket_path = tmp_path / "clamd.ctl"
        servers.append(FakeClamd(socket_path, reply))
        return ClamavAnalyzer(socket_path, 5), servers[-1]

    yield make
    for server in servers:
        server.close()


def test_file_descriptor_is_sent(make_analyzer, tmp_path):
    analyzer, server = make_analyzer(b"fd[7]: Eicar-Test-Signature FOUND\0")
    path = tmp_path / "file.bin"
    path.write_bytes(b"content")
    with scanned(path) as file:
        # The offset was moved by an earlier reader: clamd gets the start.
        os.read(file.fd, 3)
        assert [f.code for f in analyzer.analyze(file)] == ["clamav.detected"]
    assert server.commands == [b"zFILDES\0"]
    assert server.received_fd_content == [b"content"]


def test_ping(make_analyzer):
    analyzer, _ = make_analyzer(b"PONG\0")
    assert analyzer.ping() is True


def test_connection_closed_without_answer(make_analyzer, tmp_path):
    analyzer, _ = make_analyzer(b"")
    path = tmp_path / "file.bin"
    path.write_bytes(b"content")
    with scanned(path) as file, pytest.raises(ClamdError, match="without answering"):
        analyzer.analyze(file)


def test_clamd_not_running(tmp_path):
    analyzer = ClamavAnalyzer(tmp_path / "missing.ctl", 5)
    path = tmp_path / "file.bin"
    path.write_bytes(b"content")
    with scanned(path) as file, pytest.raises(ClamdError, match="cannot connect"):
        analyzer.analyze(file)
    assert analyzer.ping() is False


def test_version(make_analyzer):
    analyzer, server = make_analyzer(b"ClamAV 1.4.3/28140/Thu Oct  1 06:24:38 2026\0")
    assert analyzer.version() == "ClamAV 1.4.3/28140/Thu Oct  1 06:24:38 2026"
    assert server.commands == [b"zVERSION"]


def test_version_when_clamd_is_down(tmp_path):
    analyzer = ClamavAnalyzer(tmp_path / "missing.ctl", 5)
    assert analyzer.version() is None
