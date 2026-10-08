"""Which screen to show, from the status of the station (in memory).

FAIL-CLOSED: an unknown state or verdict shows the "degraded" screen
(station out of service), never a result.
FR : un état ou un verdict inattendu affiche « station hors service »,
jamais un résultat.
"""

import math
from dataclasses import dataclass, replace

from februus.core.status import SessionStatus, Status
from februus.web.messages import FINDING_MESSAGES

RESULT_COLORS = {"green", "orange", "red"}
SCREENS = ("idle", "inspecting", "scanning", "result", "removed", "degraded")


@dataclass(frozen=True, slots=True)
class Problem:
    """One kind of problem to show: a known message, or an unknown code."""

    message: str | None
    code: str


@dataclass(frozen=True, slots=True)
class Screen:
    name: str
    color: str | None = None
    files_total: int = 0
    files_done: int = 0
    percent: int = 0
    eta_seconds: int | None = None
    eta_minutes: int | None = None
    # ETA above [scan] long_scan_warning_minutes: "come back at HH:MM".
    long_scan: bool = False
    problems: tuple[Problem, ...] = ()
    # Files too big to be checked (names from the key, escaped by Jinja2).
    big_files: tuple[str, ...] = ()
    # Signatures of the last session that knew them (idle status line).
    signatures: str | None = None
    # Last session: the page reloads when it changes (None: no session yet).
    session_id: int | None = None
    # Another key is plugged in and ignored (notice on every screen).
    extra_keys: bool = False
    # A USB device refused by USBGuard is plugged in (notice on every screen).
    blocked_device: bool = False


def current_screen(status: Status, long_scan_minutes: int) -> Screen:
    """Screen for the current state of the station."""
    return screen_for(status.snapshot(), long_scan_minutes)


def screen_for(session: SessionStatus, long_scan_minutes: int) -> Screen:
    """Screen for one status of the station."""
    common = {"session_id": session.id, "extra_keys": session.extra_keys > 0,
              "blocked_device": session.blocked_devices > 0}
    state = session.state
    if state == "idle":
        return Screen("idle", signatures=session.signatures, **common)
    if state == "inspecting":
        return Screen("inspecting", **common)
    if state == "scanning":
        eta_minutes = _minutes(session.eta_seconds)
        return Screen(
            "scanning",
            files_total=session.files_total,
            files_done=session.files_done,
            percent=_percent(session),
            eta_seconds=session.eta_seconds,
            eta_minutes=eta_minutes,
            long_scan=eta_minutes is not None and eta_minutes > long_scan_minutes,
            **common,
        )
    if state == "aborted":
        return Screen("removed", color="red", **common)
    if state == "result" and session.verdict in RESULT_COLORS:
        return Screen(
            "result",
            color=session.verdict,
            files_total=session.files_total,
            files_done=session.files_done,
            problems=tuple(Problem(FINDING_MESSAGES.get(code), code) for code in session.problems),
            big_files=session.big_files,
            **common,
        )
    # FAIL-CLOSED / FR : état inattendu = station hors service.
    return Screen("degraded", **common)


def preview_screens(long_scan_minutes: int) -> dict[str, Screen]:
    """Every screen with a simulated session (development preview)."""
    base = SessionStatus(
        id=1, state="scanning", files_total=1200, files_done=450,
        bytes_total=4_000_000_000, bytes_done=1_500_000_000, eta_seconds=610,
    )
    result = replace(base, state="result", files_done=1200, eta_seconds=0)
    long_eta = (long_scan_minutes + 25) * 60
    minutes = long_scan_minutes

    def show(session: SessionStatus) -> Screen:
        return screen_for(session, minutes)

    return {
        "idle": Screen("idle", signatures="ClamAV 1.4.3/28140/Thu Oct  1 06:24:38 2026"),
        "two_keys": show(replace(base, extra_keys=1)),
        "key_left": Screen("idle", extra_keys=True),
        "blocked": Screen("idle", blocked_device=True),
        "inspecting": show(replace(base, state="inspecting")),
        "scanning": show(replace(base, eta_seconds=150)),
        "long_scan": show(replace(base, eta_seconds=long_eta)),
        "green": show(replace(result, verdict="green")),
        "orange": show(replace(result, verdict="orange", problems=("device.multi_partition",))),
        "red": show(replace(
            result, verdict="red",
            problems=("archive.encrypted", "clamav.detected", "vendor.new_code"),
        )),
        "removed": show(replace(base, state="aborted", verdict="red")),
        "degraded": Screen("degraded"),
    }


def _percent(session: SessionStatus) -> int:
    if session.bytes_total:
        ratio = session.bytes_done / session.bytes_total
    elif session.files_total:
        ratio = session.files_done / session.files_total
    else:
        ratio = 0.0
    return max(0, min(100, int(ratio * 100)))


def _minutes(eta_seconds: int | None) -> int | None:
    if eta_seconds is None:
        return None
    return math.ceil(eta_seconds / 60)
