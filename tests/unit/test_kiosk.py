"""Tests for the kiosk files of ``deploy/kiosk`` (unit and GPU wait)."""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WAIT = REPO_ROOT / "deploy" / "kiosk" / "wait-for-gpu.sh"
UNIT = REPO_ROOT / "deploy" / "kiosk" / "februus-kiosk.service"


def _card(drm: Path, name: str, driver: str | None) -> None:
    """Make a fake /sys/class/drm/<name> whose device uses ``driver``."""
    device = drm / f"{name}-device"
    device.mkdir(parents=True)
    if driver is not None:
        (drm / "drivers" / driver).mkdir(parents=True, exist_ok=True)
        (device / "driver").symlink_to(drm / "drivers" / driver)
    (drm / name).mkdir()
    (drm / name / "device").symlink_to(device)


def _wait(drm: Path, seconds: int = 1) -> subprocess.CompletedProcess:
    env = dict(os.environ, FEBRUUS_DRM_DIR=str(drm))
    return subprocess.run(
        [str(WAIT), str(seconds)],
        env=env, capture_output=True, text=True, timeout=30,
    )


def test_real_driver_is_ready_at_once(tmp_path):
    _card(tmp_path, "card0", "i915")
    (tmp_path / "card0-HDMI-A-1").mkdir()
    result = _wait(tmp_path, seconds=5)
    assert result.returncode == 0
    assert "ready after 0 s" in result.stdout


def test_real_driver_next_to_simpledrm_is_ready(tmp_path):
    _card(tmp_path, "card0", "simple-framebuffer")
    _card(tmp_path, "card1", "amdgpu")
    assert "ready" in _wait(tmp_path).stdout


def test_only_simpledrm_waits_then_goes_on(tmp_path):
    _card(tmp_path, "card0", "simple-framebuffer")
    result = _wait(tmp_path, seconds=1)
    assert result.returncode == 0
    assert "generic one" in result.stdout


def test_no_screen_device_fails(tmp_path):
    result = _wait(tmp_path, seconds=1)
    assert result.returncode == 1
    assert "no screen device" in result.stderr


def test_kiosk_unit_allows_console_switch_and_never_gives_up():
    text = UNIT.read_text()
    assert "/usr/bin/cage -s -- " in text
    assert "ExecStartPre=/usr/local/lib/februus/wait-for-gpu.sh" in text
    assert "StartLimitIntervalSec=0" in text
    assert "StandardError=journal" in text
