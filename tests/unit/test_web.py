"""Tests for the web UI: screens, read-only access, live updates."""

import copy
import json
import re
import tomllib
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from februus.core.config import parse_config
from februus.core.status import SessionStatus, Status
from februus.web import app as web_app
from februus.web.app import create_app

# The tests never read the theme installed on the machine.
NO_THEME = Path("/nonexistent/februus-theme")
from februus.web.messages import FINDING_MESSAGES
from februus.web.screens import preview_screens, screen_for

DEV = Path(__file__).resolve().parents[2] / "config" / "februus.dev.toml"
EXAMPLE = DEV.with_name("februus.example.toml")
FIXED_NOW = datetime(2026, 10, 2, 10, 0, 0)


@pytest.fixture
def raw(tmp_path):
    with DEV.open("rb") as file:
        data = copy.deepcopy(tomllib.load(file))
    data["station"]["name"] = "f1"
    # Short live streams for the tests.
    data["web"]["stream_seconds"] = 1
    data["web"]["poll_interval_ms"] = 100
    return data


@pytest.fixture
def status():
    return Status()


@pytest.fixture
def client(raw, status):
    # Fixed time: the idle tip must not change during a test.
    return TestClient(create_app(parse_config(raw), status, now=lambda: FIXED_NOW, theme_dir=NO_THEME))


def add_session(status, state, verdict=None, closed=False, codes=(), **progress):
    """A session in the given state (``closed``: the key was removed)."""
    session_id = status.start()
    problems = tuple(code for code, color in codes if color != "green")
    status.update(state=state, verdict=verdict, problems=problems, **progress)
    if closed:
        status.close()
    return session_id


def main_text(html: str) -> str:
    """Visible text of the <main> part, on one line."""
    main = html.split("<main>", 1)[1].split("</main>", 1)[0]
    return " ".join(re.sub(r"<[^>]+>", " ", main).split())


# --- Screens ------------------------------------------------------------


def test_no_session_shows_idle(client):
    assert "Insérez votre clé USB" in client.get("/").text


def test_scanning_screen_shows_progress(client, status):
    add_session(status, "scanning", files_total=10, files_done=4, bytes_total=1000,
                bytes_done=250, eta_seconds=150)
    page = client.get("/").text
    assert "Analyse en cours" in main_text(page)
    assert "4 sur 10 fichiers vérifiés" in main_text(page)
    assert "Environ 3 minutes restantes." in main_text(page)
    assert 'aria-valuenow="25"' in page
    assert "Ne retirez pas la clé." in page


@pytest.mark.parametrize(
    ("verdict", "codes", "expected"),
    [
        ("green", [], "Aucune menace détectée"),
        ("orange", [("device.multi_partition", "orange")], "Cette clé contient plusieurs partitions."),
        ("red", [("clamav.detected", "red")], "Un virus ou un fichier malveillant a été trouvé."),
        ("red", [("vendor.new_code", "red")], "Problème inconnu (code vendor.new_code)."),
    ],
)
def test_result_screens(client, status, verdict, codes, expected):
    add_session(status, "result", verdict, codes=codes)
    page = client.get("/").text
    assert f"color-{verdict}" in page
    assert expected in main_text(page)


def test_green_findings_are_not_listed(client, status):
    add_session(status, "result", "green", codes=[("fake.clean", "green")])
    assert "<li>" not in client.get("/").text


def test_aborted_session_shows_removed(client, status):
    add_session(status, "aborted", "red")
    page = client.get("/").text
    assert "elle n'a PAS été vérifiée" in page
    assert "color-red" in page


def test_closed_session_goes_back_to_idle(client, status):
    add_session(status, "result", "green", closed=True)
    assert "Insérez votre clé USB" in client.get("/").text


def test_unknown_state_is_degraded():
    # FAIL-CLOSED: a state the UI does not know never shows a result.
    session = SessionStatus(id=1, state="paused", verdict="green")
    assert screen_for(session, 5).name == "degraded"


def test_status_error_is_degraded(client, status, monkeypatch):
    add_session(status, "result", "green")

    def broken(status, long_scan_minutes):
        raise RuntimeError("unexpected error")

    monkeypatch.setattr(web_app, "current_screen", broken)
    page = client.get("/").text
    assert "Station hors service" in page
    assert "Aucune menace détectée" not in page


def test_web_ui_never_changes_the_status(client, status):
    add_session(status, "result", "green")
    before = status.snapshot()
    client.get("/")
    assert status.snapshot() == before


def test_file_names_are_escaped(client, status):
    # Text from the key is never HTML: unknown codes are shown escaped.
    add_session(status, "result", "red", codes=[("x.<script>", "red")])
    page = client.get("/").text
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


# --- One language ---------------------------------------------------------


def test_the_ui_is_in_french(client):
    page = client.get("/").text
    assert '<html lang="fr">' in page
    assert 'class="languages"' not in page
    assert client.get("/lang/fr", follow_redirects=False).status_code == 404


def test_one_file_is_not_plural(client, status):
    add_session(status, "result", "green", files_done=1)
    assert "1 fichier vérifié." in main_text(client.get("/").text)


def test_files_are_plural_from_two(client, status):
    # French: 0 and 1 are singular, 2 and more are plural.
    add_session(status, "result", "green", files_done=0)
    assert "0 fichier vérifié." in main_text(client.get("/").text)
    add_session(status, "result", "green", files_done=2)
    assert "2 fichiers vérifiés." in main_text(client.get("/").text)


# --- Preview --------------------------------------------------------------


@pytest.mark.parametrize("name", list(preview_screens(5)))
def test_every_screen_renders(client, name):
    response = client.get(f"/preview/{name}")
    assert response.status_code == 200
    assert "Februus" in response.text


def test_preview_disabled_in_production(raw, status):
    raw["web"]["preview_screens"] = False
    client = TestClient(create_app(parse_config(raw), status, theme_dir=NO_THEME))
    assert client.get("/preview/idle").status_code == 404


def test_stopped_scanner_never_shows_an_old_result(raw, status):
    # Seen on the test PC: with the scanner stopped, the green result of
    # the last key stayed on the screen.
    alive = [True]
    add_session(status, "result", "green")
    client = TestClient(create_app(parse_config(raw), status, scanner_alive=lambda: alive[0], theme_dir=NO_THEME))
    assert "Aucune menace détectée" in client.get("/").text
    alive[0] = False
    page = client.get("/").text
    assert "Station hors service" in page
    assert "Aucune menace détectée" not in page
    assert "Station hors service" in screen_events(client)[0]["main"]


def test_brand_font_is_served_by_the_station(client):
    # No Internet on a station: nothing may be loaded from another site.
    page = client.get("/").text
    assert '<span class="brand">Februus</span>' in page
    assert "http://" not in page and "https://" not in page
    style = client.get("/static/style.css").text
    assert "http://" not in style and "https://" not in style
    files = re.findall(r'url\("(/static/[^"]+)"\)', style)
    assert len(files) == 1  # the font of the name
    for path in files:
        assert client.get(path).status_code == 200


def test_no_api_documentation_pages(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


# --- Messages -------------------------------------------------------------


def test_every_finding_code_of_the_rules_has_a_message():
    with EXAMPLE.open("rb") as file:
        rules = tomllib.load(file)["verdict"]["rules"]
    missing = set(rules) - set(FINDING_MESSAGES)
    assert missing == set()


# --- T9: live updates, long scan, idle screen, sounds ----------------------


def make_client(raw, status, **kwargs):
    return TestClient(create_app(parse_config(raw), status, theme_dir=NO_THEME, **kwargs))


def stream_events(client) -> list[tuple[str, str]]:
    """(event name, data) of one live stream (it lasts stream_seconds)."""
    events = []
    name = ""
    with client.stream("GET", "/events") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((name, line.removeprefix("data: ")))
    return events


def screen_events(client) -> list[dict]:
    """All "screen" events of one live stream."""
    return [json.loads(data) for name, data in stream_events(client) if name == "screen"]


def test_live_stream_sends_the_screen_once(client):
    events = screen_events(client)
    # Same screen during the whole stream: sent only once.
    assert len(events) == 1
    assert events[0]["key"] == "idle:None:0"
    assert "Insérez votre clé USB" in events[0]["main"]


def test_live_stream_follows_the_status(client, status):
    session_id = add_session(status, "scanning", files_total=10, files_done=4)
    [event] = screen_events(client)
    assert event["key"] == f"scanning:None:{session_id}"
    assert "4 sur 10 fichiers vérifiés" in event["main"]
    status.update(state="result", verdict="red")
    [event] = screen_events(client)
    assert event["key"] == f"result:red:{session_id}"


def test_live_page_loads_the_script_and_preview_does_not(client):
    assert "/static/live.js" in client.get("/").text
    assert "/static/live.js" not in client.get("/preview/scanning").text
    assert client.get("/static/live.js").status_code == 200


def test_live_stream_sends_signs_of_life_between_changes(raw, status):
    # watchdog 3 s: a sign of life every second; the stream lasts 2 s.
    raw["web"]["watchdog_seconds"] = 3
    raw["web"]["stream_seconds"] = 2
    names = [name for name, _ in stream_events(make_client(raw, status))]
    assert names[0] == "screen"
    assert names.count("screen") == 1
    assert names.count("alive") >= 1


def test_live_script_has_the_watchdog_and_the_out_of_service_text(raw, status):
    raw["web"]["watchdog_seconds"] = 7
    response = make_client(raw, status).get("/static/live.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    script = response.text
    assert "const WATCHDOG_MS = 7000;" in script
    assert "Station hors service" in script
    # The HTML is a JSON string: no raw "<" that could close a <script>.
    assert "<h1>" not in script


def test_long_scan_shows_come_back_time(raw, status):
    # long_scan_warning_minutes = 5 in the dev config; 25 minutes left.
    add_session(status, "scanning", files_total=10, files_done=1, eta_seconds=25 * 60)
    client = make_client(raw, status, now=lambda: FIXED_NOW)
    text = main_text(client.get("/").text)
    assert "Revenez à 10:25." in text


def test_short_scan_has_no_come_back_time(raw, status):
    add_session(status, "scanning", files_total=10, files_done=1, eta_seconds=4 * 60)
    text = main_text(make_client(raw, status, now=lambda: FIXED_NOW).get("/").text)
    assert "Revenez à" not in text
    assert "Ne retirez pas la clé." in text


def test_idle_tip_changes_with_time(raw, status):
    # tip_change_seconds = 20 in the dev config.
    first = make_client(raw, status, now=lambda: datetime.fromtimestamp(1_000_000_000))
    later = make_client(raw, status, now=lambda: datetime.fromtimestamp(1_000_000_020))
    tip_of = lambda c: re.search(r'<p class="tip">(.*?)</p>', c.get("/").text).group(1)
    assert tip_of(first) != tip_of(later)


def test_idle_shows_last_signatures(client, status):
    add_session(status, "result", "green", signatures="ClamAV 1.4.3/28140", closed=True)
    assert "Signatures antivirus : ClamAV 1.4.3/28140" in client.get("/").text


@pytest.mark.parametrize(
    ("state", "verdict", "sound", "loop"),
    [
        ("result", "green", "green", False),
        ("result", "orange", "orange", False),
        ("result", "red", "red", True),
        ("aborted", "red", "red", True),
    ],
)
def test_result_sounds(client, status, state, verdict, sound, loop):
    add_session(status, state, verdict)
    audio = re.search(r"<audio [^>]*>", client.get("/").text).group(0)
    assert f'src="/sounds/{sound}.wav"' in audio
    assert ("loop" in audio) is loop


def test_no_sound_while_scanning(client, status):
    add_session(status, "scanning", files_total=1)
    assert "<audio" not in client.get("/").text


def test_sounds_can_be_disabled(raw, status):
    raw["web"]["sounds"] = False
    add_session(status, "result", "red")
    assert "<audio" not in make_client(raw, status).get("/").text


def test_sound_files_are_wav(client):
    for name in ("green", "orange", "red"):
        response = client.get(f"/sounds/{name}.wav")
        assert response.headers["content-type"] == "audio/wav"
        assert response.content[:4] == b"RIFF"
    assert client.get("/sounds/other.wav").status_code == 404


def test_second_key_notice(client, status):
    status.start()
    status.update(state="scanning")
    assert "plugged in" not in client.get("/").text
    status.set_extra_keys(1)
    page = client.get("/").text
    assert "Deux clés USB sont branchées" in page and "Retirez l'autre clé" in page
    # The live stream sends the notice too (only <main> is replaced).
    status.update(state="result", verdict="green")
    assert "Retirez l'autre clé" in client.get("/").text


def test_key_left_after_the_first_one_was_removed(client, status):
    status.set_extra_keys(1)
    page = client.get("/").text
    assert "Insérez votre clé USB" in page
    assert "encore branchée, mais elle n'a pas été vérifiée" in page
    assert "Retirez l'autre clé" not in page


def test_live_stream_carries_the_second_key_notice(client, status):
    add_session(status, "scanning", files_total=10, files_done=4)
    [event] = screen_events(client)
    assert "Retirez l'autre clé" not in event["main"]
    status.set_extra_keys(1)
    [event] = screen_events(client)
    assert "Retirez l'autre clé" in event["main"]
    assert "4 sur 10 fichiers vérifiés" in event["main"]


def test_blocked_device_notice(client, status):
    assert "a été bloqué" not in client.get("/").text
    status.set_blocked_devices(1)
    page = client.get("/").text
    assert "Un appareil USB a été bloqué" in page
    assert "Débranchez-le maintenant et prévenez votre support informatique" in page
    assert "Insérez votre clé USB" in page  # the usual screen stays
    status.set_blocked_devices(0)
    assert "a été bloqué" not in client.get("/").text


EXAMPLE_THEME = Path(__file__).resolve().parents[2] / "deploy" / "theme-example"


def test_no_theme_shows_the_plain_screens(raw, status, tmp_path):
    client = TestClient(create_app(parse_config(raw), status, theme_dir=tmp_path / "none"))
    page = client.get("/").text
    assert "Insérez votre clé USB" in page and "Thème d'exemple" not in page
    assert client.get("/theme/example.css").status_code == 404


def test_theme_replaces_templates_and_serves_its_files(raw, status):
    client = TestClient(create_app(parse_config(raw), status, theme_dir=EXAMPLE_THEME))
    page = client.get("/").text
    assert "Thème d'exemple" in page  # the theme's base.html
    assert "Insérez votre clé USB" in page  # the content still comes from the page
    assert 'href="/theme/example.css"' in page
    assert client.get("/theme/example.css").status_code == 200
    assert "/static/live.js" in page  # the live script is kept


def test_theme_keeps_the_live_screens_and_the_notice(raw, status):
    status.set_extra_keys(1)
    client = TestClient(create_app(parse_config(raw), status, theme_dir=EXAMPLE_THEME))
    [event] = screen_events(client)
    assert "Retirez-la, puis rebranchez-la" in event["main"]
    assert "Thème d'exemple" not in event["main"]  # <main> only
