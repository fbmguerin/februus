"""Tests for the analyzer process: protocol, service, and the worker that
starts and kills it."""

import copy
import errno
import json
import os
import socket
import struct
import threading
import time
import tomllib
from pathlib import Path

import pytest

from februus.analyzer import service
from februus.analyzers import fake
from februus.core import analyzer_protocol as protocol
from februus.core.analyzer_protocol import FileResult, ProtocolError
from februus.core.checks import Analyzer, Finding
from februus.core.config import parse_config
from februus.core.session import run_session
from februus.core.status import Status
from februus.readers.directory import DirectoryReader
from februus.core.verdict import Color
from februus.core.worker import AnalyzerWorker, WorkerCancelled, WorkerDied, WorkerTimeout
from tests.scanned import scanned

REPO = Path(__file__).resolve().parents[2]
DEV = REPO / "config" / "februus.dev.toml"
MARKER = b"FEBRUUS-FAKE-MALWARE"
SLOW = b"FEBRUUS-FAKE-SLOW"
ERROR = b"FEBRUUS-FAKE-ERROR"


@pytest.fixture
def pair():
    a, b = socket.socketpair()
    yield a, b
    a.close()
    b.close()


def raw_message(payload: bytes) -> bytes:
    return struct.pack("!I", len(payload)) + payload


def make_file(tmp_path, content: bytes, name: str = "file.bin") -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


# --- Protocol ---------------------------------------------------------


def test_request_round_trip(pair, tmp_path):
    scanner, analyzer = pair
    # A name that is not valid UTF-8 (possible on a key) survives.
    name = os.fsdecode(b"docs/caf\xe9.txt")
    with scanned(make_file(tmp_path, b"content")) as file:
        protocol.send_request(scanner, name, file.fd)
    received = protocol.receive_request(analyzer)
    try:
        assert received.name == name
        assert os.pread(received.fd, 100, 0) == b"content"
    finally:
        os.close(received.fd)


def test_answer_round_trip(pair):
    scanner, analyzer = pair
    result = FileResult(findings=(("fake", "fake.detected", "marker found"),))
    protocol.send_answer(analyzer, result)
    protocol.send_answer(analyzer, FileResult(error="boom"))
    assert protocol.receive_answer(scanner) == result
    assert protocol.receive_answer(scanner) == FileResult(error="boom")


def test_closed_connection(pair):
    scanner, analyzer = pair
    scanner.close()
    assert protocol.receive_request(analyzer) is None


def test_connection_closed_in_a_message(pair):
    scanner, analyzer = pair
    scanner.sendall(raw_message(b'{"name": "a"}')[:-3])
    scanner.close()
    with pytest.raises(ProtocolError, match="middle of a message"):
        protocol.receive_request(analyzer)


def test_request_without_descriptor(pair):
    scanner, analyzer = pair
    scanner.sendall(raw_message(b'{"name": "a"}'))
    with pytest.raises(ProtocolError, match="got 0"):
        protocol.receive_request(analyzer)


def test_request_with_two_descriptors(pair, tmp_path):
    scanner, analyzer = pair
    before = len(os.listdir("/proc/self/fd"))
    with scanned(make_file(tmp_path, b"x")) as file:
        socket.send_fds(scanner, [raw_message(b'{"name": "a"}')], [file.fd, file.fd])
    with pytest.raises(ProtocolError, match="got 2"):
        protocol.receive_request(analyzer)
    # The refused descriptors were closed.
    assert len(os.listdir("/proc/self/fd")) == before


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b"[]",
        b"{}",
        b'{"name": 1}',
        b'{"name": "a", "path": "/etc/passwd"}',
    ],
)
def test_malformed_request(pair, tmp_path, payload):
    scanner, analyzer = pair
    with scanned(make_file(tmp_path, b"x")) as file:
        socket.send_fds(scanner, [raw_message(payload)], [file.fd])
    with pytest.raises(ProtocolError):
        protocol.receive_request(analyzer)


def test_oversized_message(pair, tmp_path):
    scanner, analyzer = pair
    long_name = "a" * (protocol.MAX_MESSAGE_BYTES + 1)
    with scanned(make_file(tmp_path, b"x")) as file:
        with pytest.raises(ProtocolError, match="too long"):
            protocol.send_request(scanner, long_name, file.fd)
    # A sender that ignores the limit is refused from the header.
    scanner.sendall(struct.pack("!I", protocol.MAX_MESSAGE_BYTES + 1))
    with pytest.raises(ProtocolError, match="too long"):
        protocol.receive_request(analyzer)


@pytest.mark.parametrize(
    "answer",
    [
        "garbage",
        [],
        {},
        {"findings": []},
        {"findings": [], "error": None, "extra": 1},
        {"findings": "none", "error": None},
        {"findings": [["fake", "fake.clean"]], "error": None},
        {"findings": [["fake", "fake.clean", 3]], "error": None},
        {"findings": [], "error": 12},
    ],
)
def test_malformed_answer_is_never_findings(pair, answer):
    # FAIL-CLOSED: the scanner never reads a broken answer as "no finding".
    scanner, analyzer = pair
    analyzer.sendall(raw_message(json.dumps(answer).encode()))
    with pytest.raises(ProtocolError):
        protocol.receive_answer(scanner)


def test_answer_with_a_descriptor_is_refused(pair, tmp_path):
    scanner, analyzer = pair
    payload = raw_message(b'{"findings": [], "error": null}')
    with scanned(make_file(tmp_path, b"x")) as file:
        socket.send_fds(analyzer, [payload], [file.fd])
    with pytest.raises(ProtocolError, match="descriptor"):
        protocol.receive_answer(scanner)


def test_no_answer(pair):
    scanner, analyzer = pair
    analyzer.close()
    with pytest.raises(ProtocolError, match="without an answer"):
        protocol.receive_answer(scanner)


# --- Service (in a thread, over a socketpair) -------------------------


def make_fake() -> fake.FakeAnalyzer:
    with DEV.open("rb") as file:
        options = tomllib.load(file)["analyzers"]["fake"]
    return fake.FakeAnalyzer(**options)


@pytest.fixture
def served(pair):
    """The scanner end of a connection served by ``service.serve``."""
    scanner, analyzer = pair
    thread = threading.Thread(target=service.serve, args=(analyzer, [make_fake()]))
    thread.start()
    yield scanner
    scanner.close()
    thread.join(5)
    assert not thread.is_alive()


def ask(sock, path: Path) -> FileResult:
    with scanned(path) as file:
        protocol.send_request(sock, file.name, file.fd)
    return protocol.receive_answer(sock)


def test_service_findings(served, tmp_path):
    bad = make_file(tmp_path, b"abc" + MARKER, "bad.bin")
    clean = make_file(tmp_path, b"hello", "clean.txt")
    assert ask(served, bad) == FileResult((("fake", "fake.detected", "marker found"),))
    assert ask(served, clean) == FileResult((("fake", "fake.clean", ""),))


def test_service_analyzer_exception_is_an_error(served, tmp_path):
    result = ask(served, make_file(tmp_path, ERROR))
    assert result.findings == () and "FakeAnalyzerError" in result.error
    # The service goes on with the next file.
    assert ask(served, make_file(tmp_path, b"ok", "next")).error is None


def test_service_refuses_a_pipe(served):
    read_end, write_end = os.pipe()
    try:
        protocol.send_request(served, "pipe", read_end)
        result = protocol.receive_answer(served)
    finally:
        os.close(read_end)
        os.close(write_end)
    assert result.findings == () and "not a regular file" in result.error


def test_service_refuses_a_writable_descriptor(served, tmp_path):
    fd = os.open(make_file(tmp_path, b"x"), os.O_RDWR)
    try:
        protocol.send_request(served, "file", fd)
        result = protocol.receive_answer(served)
    finally:
        os.close(fd)
    assert result.findings == () and "read-only" in result.error


def test_service_answers_an_error_to_a_bad_request(served):
    served.sendall(raw_message(b'{"name": "no descriptor"}'))
    result = protocol.receive_answer(served)
    assert result.findings == () and "invalid request" in result.error
    # Then it closes the connection.
    assert served.recv(1) == b""


def test_file_read_error_is_never_clean(tmp_path, monkeypatch):
    # Seen on the mini-PC: clamd answers "OK" for a file it could only
    # read in part. The service reads every file itself: an I/O error is
    # an error (red), even when the analyzers find nothing.
    def failing_read(fd, size):
        raise OSError(errno.EIO, "Input/output error")

    with scanned(make_file(tmp_path, b"x" * 10)) as file:
        assert service.analyze_file((), file) == FileResult()
        monkeypatch.setattr(service.os, "read", failing_read)
        result = service.analyze_file((), file)
    assert result.findings == () and "Input/output error" in result.error


def test_each_analyzer_starts_at_the_beginning(tmp_path):
    class Reader(Analyzer):
        name = "reader"

        def analyze(self, file):
            content = b""
            while chunk := os.read(file.fd, 4):
                content += chunk
            return [Finding("reader.seen", content.decode())]

    analyzers = [Reader(), Reader()]
    with scanned(make_file(tmp_path, b"whole file")) as file:
        result = service.analyze_file(analyzers, file)
    assert [detail for _, _, detail in result.findings] == ["whole file"] * 2


def test_answer_too_long_is_an_error(pair, tmp_path):
    class Chatty(Analyzer):
        name = "chatty"

        def analyze(self, file):
            return [Finding("chatty.found", "x" * protocol.MAX_MESSAGE_BYTES)]

    scanner, analyzer = pair
    thread = threading.Thread(target=service.serve, args=(analyzer, [Chatty()]))
    thread.start()
    try:
        result = ask(scanner, make_file(tmp_path, b"x"))
    finally:
        scanner.close()
        thread.join(5)
    assert result.findings == () and "too long" in result.error


# --- Worker connected to the analyzer process -------------------------


@pytest.fixture
def raw(tmp_path):
    with DEV.open("rb") as file:
        data = copy.deepcopy(tomllib.load(file))
    data["log"]["path"] = str(tmp_path / "keys.jsonl")
    return data


def make_worker(raw) -> AnalyzerWorker:
    return AnalyzerWorker(parse_config(raw).analyzers)


def fake_peer(monkeypatch, behaviour):
    """The worker talks to ``behaviour(sock)``, run in a thread, instead of
    the real analyzer process (to play a compromised analyzer)."""

    def start(self):
        mine, theirs = socket.socketpair()
        threading.Thread(target=behaviour, args=(theirs,), daemon=True).start()
        self._sock = mine

    monkeypatch.setattr(AnalyzerWorker, "_start", start)


def test_worker_uses_one_process_for_several_files(raw, tmp_path):
    with make_worker(raw) as worker:
        bad = worker.analyze(make_file(tmp_path, MARKER, "bad"), "bad", 10)
        process = worker._process
        clean = worker.analyze(make_file(tmp_path, b"hello", "clean"), "clean", 10)
        assert worker._process is process
    assert [code for _, code, _ in bad.findings] == ["fake.detected"]
    assert [code for _, code, _ in clean.findings] == ["fake.clean"]
    # Stopped with the worker.
    assert worker._process is None


def test_worker_timeout_kills_the_process_and_a_new_one_serves_the_next_file(raw, tmp_path):
    with make_worker(raw) as worker:
        with pytest.raises(WorkerTimeout):
            worker.analyze(make_file(tmp_path, SLOW, "slow"), "slow", 1.5, check_seconds=0.05)
        assert worker._process is None  # killed
        result = worker.analyze(make_file(tmp_path, b"hello", "next"), "next", 10)
    assert [code for _, code, _ in result.findings] == ["fake.clean"]


def test_worker_cancel(raw, tmp_path):
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    started = time.monotonic()
    with make_worker(raw) as worker:
        with pytest.raises(WorkerCancelled):
            worker.analyze(make_file(tmp_path, SLOW), "slow", 60, cancel, 0.05)
        assert worker._process is None
    assert time.monotonic() - started < 10


def test_worker_when_the_process_is_killed(raw, tmp_path):
    with make_worker(raw) as worker:
        assert worker.analyze(make_file(tmp_path, b"hello"), "file", 10).error is None
        worker._process.kill()
        worker._process.join()
        with pytest.raises(WorkerDied):
            worker.analyze(make_file(tmp_path, b"hello", "again"), "again", 10)


@pytest.mark.parametrize(
    "answer",
    [
        b"garbage",
        b'{"findings": [], "error": null, "extra": 1}',
        # A module that is not a configured analyzer, an invalid code.
        b'{"findings": [["session", "device.ok", ""]], "error": null}',
        b'{"findings": [["fake", "Not A Code", ""]], "error": null}',
    ],
)
def test_worker_refuses_a_malformed_answer(raw, tmp_path, monkeypatch, answer):
    def answer_once(conn):
        with conn:
            conn.recv(4096)
            conn.sendall(raw_message(answer))
            conn.recv(1)

    fake_peer(monkeypatch, answer_once)
    with make_worker(raw) as worker:
        with pytest.raises(WorkerDied):
            worker.analyze(make_file(tmp_path, b"hello"), "file", 10)


def test_slow_answer_does_not_bypass_the_timeout(raw, tmp_path, monkeypatch):
    # A compromised analyzer sends its answer byte by byte: data is always
    # there, but the timeout and the removal of the key still apply.
    def trickle(conn):
        with conn:
            try:
                for byte in raw_message(b" " * 60000):
                    conn.sendall(bytes([byte]))
                    time.sleep(0.02)
            except OSError:
                pass

    fake_peer(monkeypatch, trickle)
    with make_worker(raw) as worker:
        started = time.monotonic()
        with pytest.raises(WorkerTimeout):
            worker.analyze(make_file(tmp_path, b"hello"), "file", 0.5, check_seconds=0.05)
        assert time.monotonic() - started < 5
        cancel = threading.Event()
        threading.Timer(0.3, cancel.set).start()
        with pytest.raises(WorkerCancelled):
            worker.analyze(make_file(tmp_path, b"hello", "b"), "b", 60, cancel, 0.05)


def test_failed_start_of_the_process_is_worker_died(raw, tmp_path, monkeypatch):
    from februus.core import worker as worker_module

    def failing_start(self):
        raise OSError(errno.EAGAIN, "Resource temporarily unavailable")

    monkeypatch.setattr(worker_module._CONTEXT.Process, "start", failing_start)
    with make_worker(raw) as worker:
        with pytest.raises(WorkerDied):
            worker.analyze(make_file(tmp_path, b"hello"), "file", 5)


def test_session_with_a_slow_file(raw, tmp_path):
    folder = tmp_path / "key"
    (folder / "docs").mkdir(parents=True)
    (folder / "a.txt").write_bytes(b"hello")
    (folder / "docs" / "bad.bin").write_bytes(MARKER)
    (folder / "slow.bin").write_bytes(SLOW)
    raw["scan"]["file_timeout_seconds"] = 1
    config = parse_config(raw)
    result = run_session(config, Status(), DirectoryReader(), str(folder))
    assert result.verdict is Color.RED
    assert {(f.path, f.code) for f in result.findings} == {
        ("a.txt", "fake.clean"),
        ("docs/bad.bin", "fake.detected"),
        ("slow.bin", "scan.timeout"),
    }
