"""Tests for the session engine (with the dev analyzer, no ClamAV)."""

import copy
import importlib.util
import itertools
import os
import threading
import time
import tomllib
from pathlib import Path, PurePath

import pytest

from februus.cli import main
from februus.core import keylog
from februus.core.config import parse_config
from februus.core.devices import ImageDevice
from februus.core.session import inventory, run_session
from februus.core.status import Status
from februus.readers.directory import DirectoryReader
from februus.core.verdict import Color
from februus.core.worker import AnalyzerWorker, WorkerDied
from tests import disk_images as img

DEV = Path(__file__).resolve().parents[2] / "config" / "februus.dev.toml"
MARKER = b"FEBRUUS-FAKE-MALWARE"


@pytest.fixture
def raw(tmp_path):
    with DEV.open("rb") as file:
        data = copy.deepcopy(tomllib.load(file))
    data["log"]["path"] = str(tmp_path / "keys.jsonl")
    return data


@pytest.fixture
def status():
    return Status()


def log_entries(raw):
    return list(keylog.read(Path(raw["log"]["path"])))


@pytest.fixture
def folder(tmp_path):
    root = tmp_path / "key"
    (root / "docs").mkdir(parents=True)
    (root / "a.txt").write_bytes(b"hello")
    (root / "docs" / "b.txt").write_bytes(b"world!")
    return root


def scan(raw, status, source, **kwargs):
    config = parse_config(raw)
    source = source if isinstance(source, list) else str(source)
    return run_session(config, status, DirectoryReader(), source, **kwargs)


def codes(result):
    return sorted(f.code for f in result.findings if f.color is not Color.GREEN)


def test_clean_folder_is_green(raw, status, folder):
    result = scan(raw, status, folder)
    assert result.verdict is Color.GREEN
    assert result.files_total == 2
    shown = status.snapshot()
    assert (shown.id, shown.state, shown.verdict) == (result.session_id, "result", "green")
    assert (shown.files_done, shown.bytes_done, shown.bytes_total) == (2, 11, 11)
    assert shown.problems == ()


def test_detected_file_is_red(raw, status, folder):
    (folder / "docs" / "bad.bin").write_bytes(b"\x00" + MARKER)
    result = scan(raw, status, folder)
    assert result.verdict is Color.RED
    [finding] = [f for f in result.findings if f.code == "fake.detected"]
    assert (finding.path, finding.module, finding.color) == ("docs/bad.bin", "fake", Color.RED)


def test_analyzer_exception_is_red(raw, status, folder):
    (folder / "boom.txt").write_bytes(b"FEBRUUS-FAKE-ERROR")
    result = scan(raw, status, folder)
    assert result.verdict is Color.RED
    assert codes(result) == ["internal.error"]
    # The other files were still analyzed.
    assert result.files_total == 3


def test_file_timeout_is_red(raw, status, folder):
    raw["scan"]["file_timeout_seconds"] = 1
    (folder / "slow.txt").write_bytes(b"FEBRUUS-FAKE-SLOW")
    (folder / "z_after.txt").write_bytes(MARKER)
    result = scan(raw, status, folder)
    assert result.verdict is Color.RED
    # The worker was restarted: the file after the slow one was analyzed.
    assert codes(result) == ["fake.detected", "scan.timeout"]


def test_session_timeout_is_red(raw, status, folder):
    # Fake clock: time jumps by one day at each reading, so the session
    # deadline is passed before the first file.
    ticks = itertools.count(start=0, step=86400)
    result = scan(raw, status, folder, clock=lambda: next(ticks))
    assert result.verdict is Color.RED
    assert "scan.timeout" in codes(result)
    # Stopped as early as the inventory: no file was even listed.
    assert result.files_total == 0


def test_unknown_code_is_red(raw, status, folder):
    # Production rules do not know the fake codes: the fake analyzer
    # can never give green on a real station.
    del raw["verdict"]["rules"]["fake.clean"]
    result = scan(raw, status, folder)
    assert result.verdict is Color.RED


def test_missing_source_is_red(raw, status, tmp_path):
    result = scan(raw, status, tmp_path / "missing")
    assert result.verdict is Color.RED
    assert codes(result) == ["internal.error"]


def test_symlink_is_reported_not_followed(raw, status, folder, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_bytes(MARKER)
    (folder / "link").symlink_to(outside)
    result = scan(raw, status, folder)
    assert result.verdict is Color.RED
    assert codes(result) == ["file.not_regular"]
    assert result.files_total == 2


def test_empty_folder_is_green(raw, status, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = scan(raw, status, empty)
    assert (result.verdict, result.files_total) == (Color.GREEN, 0)


def test_inventory_does_not_follow_symlinks(folder, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    (other / "hidden.txt").write_bytes(b"x")
    (folder / "dirlink").symlink_to(other, target_is_directory=True)
    files, others = inventory(folder)
    assert files == [(PurePath("a.txt"), 5), (PurePath("docs/b.txt"), 6)]
    assert others == [PurePath("dirlink")]


def test_undecodable_file_name_is_shown_as_text(raw, status, folder):
    (folder / os.fsdecode(b"bad\xffname.txt")).write_bytes(MARKER)
    result = scan(raw, status, folder)
    assert [f.path for f in result.findings if f.code == "fake.detected"] == ["bad\\xffname.txt"]
    [entry] = log_entries(raw)
    assert entry["problems"] == [
        {"path": "bad\\xffname.txt", "code": "fake.detected", "color": "red"}
    ]


def test_first_estimate_is_measured_not_guessed(raw, status, folder, monkeypatch):
    # No history of earlier keys: the time left is unknown until the speed
    # is measured, and 0 at the end.
    updates = []
    original = status.update
    monkeypatch.setattr(status, "update", lambda **c: (updates.append(c), original(**c)))
    scan(raw, status, folder)
    assert "eta_seconds" not in next(u for u in updates if "files_total" in u)
    assert status.snapshot().eta_seconds == 0


def test_symlink_is_never_read_by_the_worker(raw, tmp_path):
    # The scanner opens the files itself (O_NOFOLLOW): a link found on the
    # key is an error, and nothing is sent to the analyzer process.
    config = parse_config(raw)
    target = tmp_path / "target"
    target.write_bytes(b"x")
    link = tmp_path / "link"
    link.symlink_to(target)
    with AnalyzerWorker(config.analyzers) as worker:
        assert "unreadable file" in worker.analyze(link, "link", 5).error
        assert "not a regular file" in worker.analyze(tmp_path, "folder", 5).error
        assert worker._process is None


def test_worker_died(raw):
    config = parse_config(raw)
    with AnalyzerWorker(config.analyzers) as worker:
        worker._start()
        worker._process.kill()
        worker._process.join()
        with pytest.raises(WorkerDied):
            worker.analyze(DEV, "file", 5)


@pytest.mark.parametrize(
    ("content", "exit_code"),
    [(b"hello", 0), (MARKER, 2)],
)
def test_cli_scan_exit_code(raw, folder, tmp_path, content, exit_code, capsys):
    (folder / "file").write_bytes(content)
    config_path = tmp_path / "dev.toml"
    config_path.write_text(DEV.read_text().replace(
        'path = "/tmp/februus-dev/keys.jsonl"', f'path = "{raw["log"]["path"]}"'
    ))
    assert main(["scan", "-c", str(config_path), str(folder)]) == exit_code
    assert "Verdict:" in capsys.readouterr().out


def test_signatures_are_shown_and_logged(raw, status, folder, monkeypatch):
    from februus.analyzers.fake import FakeAnalyzer

    monkeypatch.setattr(FakeAnalyzer, "version", lambda self: "fake 1.0")
    scan(raw, status, folder)
    assert status.snapshot().signatures == "fake 1.0"
    assert log_entries(raw)[0]["signatures"] == "fake 1.0"


def test_one_log_line_per_key(raw, status, folder):
    scan(raw, status, folder)
    (folder / "bad.txt").write_bytes(MARKER)
    scan(raw, status, folder)
    green, red = log_entries(raw)
    assert (green["verdict"], green["files"], green["bytes"], green["problems"]) == (
        "green", 2, 11, [])
    assert (red["verdict"], red["files"], red["removed"]) == ("red", 3, False)
    assert red["problems"] == [{"path": "bad.txt", "code": "fake.detected", "color": "red"}]


def test_a_log_that_cannot_be_written_does_not_change_the_result(raw, status, folder):
    raw["log"]["path"] = str(folder.parent / "no-such-folder" / "keys.jsonl")
    assert scan(raw, status, folder).verdict is Color.GREEN
    assert status.snapshot().verdict == "green"


def test_the_screen_lists_the_problem_codes(raw, status, folder):
    (folder / "bad.txt").write_bytes(MARKER)
    scan(raw, status, folder)
    assert status.snapshot().problems == ("fake.detected",)


# --- Nothing is written on the key ---------------------------------------------


def snapshot(root):
    """Names and bytes of everything under ``root``."""
    return {str(p.relative_to(root)): p.read_bytes() if p.is_file() else None
            for p in sorted(root.rglob("*"))}


@pytest.mark.parametrize("marker", [b"", MARKER, b"FEBRUUS-FAKE-ERROR"],
                         ids=["green", "red", "error"])
def test_nothing_is_written_on_the_key(raw, status, folder, marker):
    # Security rule 6: green, red or failed, the key is left as it was.
    if marker:
        (folder / "other.txt").write_bytes(marker)
    before = snapshot(folder)
    scan(raw, status, folder)
    assert snapshot(folder) == before


def test_cli_stats(raw, folder, tmp_path, capsys):
    config_path = tmp_path / "dev.toml"
    config_path.write_text(DEV.read_text().replace(
        'path = "/tmp/februus-dev/keys.jsonl"', f'path = "{raw["log"]["path"]}"'
    ))
    assert main(["scan", "-c", str(config_path), str(folder)]) == 0
    assert main(["stats", "-c", str(config_path), "--days", "7"]) == 0
    out = capsys.readouterr().out
    assert "Sessions: 1" in out and "green:  1" in out


def test_cli_stats_without_any_key_yet(tmp_path, capsys):
    config_path = tmp_path / "dev.toml"
    config_path.write_text(DEV.read_text().replace(
        'path = "/tmp/februus-dev/keys.jsonl"', f'path = "{tmp_path}/keys.jsonl"'
    ))
    assert main(["stats", "-c", str(config_path)]) == 0
    assert "Sessions: 0" in capsys.readouterr().out


# --- T11: inspectors before reading the files ------------------------------


def image_device(tmp_path, content):
    path = tmp_path / "key.img"
    path.write_bytes(bytes(content))
    return ImageDevice(path)


def test_bootable_key_is_refused_without_reading_files(raw, status, folder, tmp_path, caplog):
    caplog.set_level("INFO")
    device = image_device(tmp_path, img.bootable_iso())
    result = scan(raw, status, folder, device=device)
    assert result.verdict is Color.RED
    assert "device.bootable" in codes(result)
    # Never mounted nor read: no file listed.
    assert result.files_total == 0
    assert "refused by the inspectors" in caplog.text


def test_multi_partition_key_is_scanned_and_orange(raw, status, folder, tmp_path):
    image = img.mbr([(0x0C, 2048, 4096, False), (0x07, 6144, 4096, False)],
                    filesystems=["fat", "ntfs"])
    result = scan(raw, status, folder, device=image_device(tmp_path, image))
    assert result.verdict is Color.ORANGE
    assert codes(result) == ["device.multi_partition"]
    assert result.files_total == 2


def test_clean_device_and_folder_is_green(raw, status, folder, tmp_path):
    result = scan(raw, status, folder, device=image_device(tmp_path, img.superfloppy()))
    assert result.verdict is Color.GREEN


def test_failing_inspector_is_red(raw, status, folder, tmp_path):
    # A protective MBR without any valid GPT: the layout cannot be read.
    image = img.mbr([(0xEE, 1, 0xFFFF, False)], filesystems=["empty"])
    result = scan(raw, status, folder, device=image_device(tmp_path, image))
    assert result.verdict is Color.RED
    assert "internal.error" in codes(result)
    assert result.files_total == 0


@pytest.mark.parametrize(
    ("content", "exit_code"), [(img.superfloppy(), 0), (img.bootable_iso(), 2)]
)
def test_cli_inspect(tmp_path, capsys, content, exit_code):
    path = tmp_path / "key.img"
    path.write_bytes(bytes(content))
    assert main(["inspect", "-c", str(DEV), str(path)]) == exit_code
    assert "Inspection:" in capsys.readouterr().out


def test_cli_inspect_missing_image(tmp_path, capsys):
    assert main(["inspect", "-c", str(DEV), str(tmp_path / "missing.img")]) == 2
    assert "Cannot open the image" in capsys.readouterr().err


def test_demo_images(tmp_path, capsys):
    """tools/demo-images.py: each image gives the color the demo expects."""
    tool = Path(__file__).resolve().parents[2] / "tools" / "demo-images.py"
    spec = importlib.util.spec_from_file_location("demo_images", tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = {
        "clean-key.img": 0,
        "two-partitions.img": 1,
        "bootable-iso.img": 2,
        "efi-key.img": 2,
        "linux-key.img": 2,
    }
    assert set(module.IMAGES) == set(expected)
    for name, build in module.IMAGES.items():
        path = tmp_path / name
        path.write_bytes(bytes(build()))
        assert main(["inspect", "-c", str(DEV), str(path)]) == expected[name], name


# --- Review fixes: evidence kept ---------------------------------------------


def after_the_scan(monkeypatch, status, action):
    """Run ``action`` when every file has been analyzed (end of the scan)."""
    original = status.update

    def update(**changes):
        original(**changes)
        if changes.get("eta_seconds") == 0 and "state" not in changes:
            action()

    monkeypatch.setattr(status, "update", update)


def test_findings_survive_a_later_error(raw, status, folder, monkeypatch):
    # A virus found before an unexpected error must stay recorded.
    (folder / "bad.txt").write_bytes(MARKER)

    def fail():
        raise RuntimeError("unexpected failure after the scan")

    after_the_scan(monkeypatch, status, fail)
    result = scan(raw, status, folder)
    assert result.verdict is Color.RED
    assert codes(result) == ["fake.detected", "internal.error"]


# --- T12: several partitions, key removed ------------------------------------


def test_every_partition_is_analyzed(raw, status, tmp_path):
    first, second = tmp_path / "sdb1", tmp_path / "sdb2"
    first.mkdir()
    second.mkdir()
    (first / "a.txt").write_bytes(b"hello")
    (second / "b.txt").write_bytes(MARKER)  # a virus on the second partition
    result = scan(raw, status, [str(first), str(second)])
    assert result.verdict is Color.RED
    [finding] = [f for f in result.findings if f.code == "fake.detected"]
    assert finding.path == "sdb2/b.txt"
    assert result.files_total == 2


def test_key_removed_before_the_analysis(raw, status, folder):
    cancel = threading.Event()
    cancel.set()
    result = scan(raw, status, folder, cancel=cancel)
    assert result.verdict is Color.RED
    assert "device.removed" in codes(result)
    assert status.snapshot().state == "aborted"
    assert log_entries(raw)[0]["removed"] is True


def test_key_removed_during_a_long_file(raw, status, folder):
    # The slow file would hang for the whole file timeout (120 s): the
    # removal must stop the analysis within a moment.
    (folder / "slow.txt").write_bytes(b"FEBRUUS-FAKE-SLOW")
    cancel = threading.Event()
    threading.Timer(1.0, cancel.set).start()
    started = time.monotonic()
    result = scan(raw, status, folder, cancel=cancel)
    assert time.monotonic() - started < 10
    assert result.verdict is Color.RED
    assert codes(result) == ["device.removed"]


def test_key_removed_at_the_end_of_the_scan(raw, status, folder, monkeypatch):
    # Every file is analyzed, then the key is pulled out before the verdict:
    # the person did not see a complete analysis, so it is "key removed".
    cancel = threading.Event()
    after_the_scan(monkeypatch, status, cancel.set)
    result = scan(raw, status, folder, cancel=cancel)
    assert result.verdict is Color.RED
    assert "device.removed" in codes(result)
    assert status.snapshot().state == "aborted"


# --- Inventory limits (crafted keys with millions of entries) ----------------


def test_too_many_entries_is_red(raw, status, folder):
    raw["scan"]["max_entries"] = 2  # the folder holds 3 entries (a.txt, docs, b.txt)
    result = scan(raw, status, folder)
    assert result.verdict is Color.RED
    assert codes(result) == ["scan.limit_exceeded"]
    assert result.files_total == 0


def test_file_bigger_than_the_antivirus_limit_is_red_at_once(raw, status, folder):
    raw["scan"]["max_file_mb"] = 1
    with open(folder / "video.mp4", "wb") as file:
        file.truncate(2 * 1024 * 1024)  # sparse: 2 MB, nothing written
    result = scan(raw, status, folder)
    assert result.verdict is Color.RED
    assert codes(result) == ["file.too_big"]
    # Stopped before the analysis: nothing was read.
    assert result.files_total == 0


def test_names_of_big_files_go_to_the_screen_without_invisible_characters(raw, status, folder):
    raw["scan"]["max_file_mb"] = 1
    # U+202E (right-to-left mark) would show "evil\u202emp4.exe" as "evilexe.4pm".
    with open(folder / "evil\u202emp4.exe", "wb") as file:
        file.truncate(2 * 1024 * 1024)
    scan(raw, status, folder)
    [name] = status.snapshot().big_files
    assert name.endswith("evil?mp4.exe")


def test_file_at_the_limit_is_analyzed(raw, status, folder):
    raw["scan"]["max_file_mb"] = 1
    (folder / "exact.bin").write_bytes(b"x" * 1024 * 1024)
    assert "file.too_big" not in codes(scan(raw, status, folder))


def test_entries_are_counted_across_partitions(raw, status, tmp_path):
    first, second = tmp_path / "sdb1", tmp_path / "sdb2"
    for part in (first, second):
        part.mkdir()
        (part / "a.txt").write_bytes(b"x")
        (part / "b.txt").write_bytes(b"y")
    raw["scan"]["max_entries"] = 3
    assert codes(scan(raw, status, [str(first), str(second)])) == ["scan.limit_exceeded"]


def test_key_removed_during_the_inventory(raw, status, tmp_path, monkeypatch):
    root = tmp_path / "deep"
    path = root
    for level in range(50):
        path = path / f"d{level}"
    path.mkdir(parents=True)
    cancel = threading.Event()
    real_scandir = os.scandir
    folders_read = []

    def scandir(folder):
        folders_read.append(folder)
        if len(folders_read) == 3:
            cancel.set()  # the key is pulled out in the middle of the inventory
        return real_scandir(folder)

    monkeypatch.setattr("februus.core.session.os.scandir", scandir)
    result = scan(raw, status, root, cancel=cancel)
    assert 3 <= len(folders_read) < 50  # stopped early, not at the end
    assert result.verdict is Color.RED
    assert codes(result) == ["device.removed"]


def test_read_error_just_before_the_removal_event(raw, status, folder, monkeypatch):
    # Seen on the mini-PC: the key is pulled out, a read fails, and the
    # removal event comes a few milliseconds later.
    cancel = threading.Event()

    def scandir(path):
        threading.Timer(0.05, cancel.set).start()
        raise FileNotFoundError(path)

    monkeypatch.setattr("februus.core.session.os.scandir", scandir)
    result = scan(raw, status, folder, cancel=cancel)
    assert result.verdict is Color.RED
    assert sorted(codes(result)) == ["device.removed", "internal.error"]
    assert status.snapshot().state == "aborted"


def test_read_error_without_removal_is_an_internal_error(raw, status, folder, monkeypatch):
    def scandir(path):
        raise FileNotFoundError(path)

    monkeypatch.setattr("februus.core.session.os.scandir", scandir)
    result = scan(raw, status, folder, cancel=threading.Event())
    assert result.verdict is Color.RED
    assert codes(result) == ["internal.error"]
