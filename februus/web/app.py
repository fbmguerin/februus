"""Web UI of the kiosk (FastAPI + Jinja2).

The UI runs in the same process as the scanner, but it only READS the
status of the station (a snapshot, ``core/status.py``). Any error while
reading, or a scanner that stopped, shows the "degraded" screen (station
out of service).
FR : l'interface ne fait que LIRE l'état de la station. Toute erreur, ou
un scanner arrêté, affiche « station hors service », jamais un ancien
résultat.

Live updates: ``/events`` is a Server-Sent Events stream. It sends the
``<main>`` part of the screen each time it changes, with a key; the page
replaces its ``<main>`` (``/static/live.js``, rendered from
templates/live.js), or reloads itself when the key changes (other screen:
new colors and sounds). In between it sends a sign of life, so that the
page can tell a frozen stream from a screen that does not change: without
news for ``web.watchdog_seconds`` it shows "station out of service".

The texts are in simple French, written in the templates and in messages.py.

Theme (optional): a folder ``/etc/februus/theme`` (put there by
``deploy/install.sh --theme``) with ``templates/`` (they replace the
templates of the same name, for example ``base.html``) and ``static/``
(served as ``/theme/...``). Without it the plain screens are shown. It is
how a place gives its own look (logo, colors, fonts) without changing the
code. FR : un dossier de thème facultatif, lu seulement ; il appartient à
root, comme la configuration.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import jinja2
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from februus.core.config import Config
from februus.core.status import Status
from februus.web.messages import TIPS
from februus.web.screens import Screen, current_screen, preview_screens
from februus.web.sounds import generate_sounds

WEB_DIR = Path(__file__).resolve().parent
THEME_DIR = Path("/etc/februus/theme")
# Screens that play a sound when they appear, and whether it loops.
SCREEN_SOUNDS = {
    ("result", "green"): ("green", False),
    ("result", "orange"): ("orange", False),
    ("result", "red"): ("red", True),
    ("removed", "red"): ("red", True),
}


def create_app(
    config: Config,
    status: Status,
    scanner_alive: Callable[[], bool] = lambda: True,
    now: Callable[[], datetime] = datetime.now,
    theme_dir: Path = THEME_DIR,
) -> FastAPI:
    """Build the web application for this configuration.

    ``status`` is what the scanner shows, ``scanner_alive`` tells whether
    the scanner still runs, ``now`` gives the local time and ``theme_dir``
    the optional theme (both replaced in tests).
    """
    web = config.web
    environment = _environment(theme_dir)
    sounds = generate_sounds()
    long_scan_minutes = config.scan.long_scan_warning_minutes

    # No API documentation pages: the kiosk only shows the screens.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    # Before the /static folder: the script is rendered with the settings
    # (the theme's base.html keeps the same path).
    @app.get("/static/live.js")
    def live_script() -> Response:
        script = environment.get_template("live.js").render(
            watchdog_ms=web.watchdog_seconds * 1000,
            lost_html=main_part(Screen("degraded")),
        )
        return Response(script, media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
    if (theme_dir / "static").is_dir():
        app.mount("/theme", StaticFiles(directory=theme_dir / "static"), name="theme")

    def read_screen() -> Screen:
        try:
            if not scanner_alive():
                # FAIL-CLOSED: never show the result of an old session
                # while nothing watches the keys.
                # FR : scanner arrêté : jamais d'ancien résultat à l'écran.
                return Screen("degraded")
            return current_screen(status, long_scan_minutes)
        except Exception:
            # FAIL-CLOSED / FR : erreur de lecture = station hors service.
            return Screen("degraded")

    def context(screen: Screen) -> dict[str, Any]:
        """Values used by the templates."""
        local_now = now()
        come_back_at = None
        if screen.long_scan and screen.eta_seconds is not None:
            # Local time, 24 hours ("14:35").
            come_back_at = (local_now + timedelta(seconds=screen.eta_seconds)).strftime("%H:%M")
        tip_index = int(local_now.timestamp()) // web.tip_change_seconds % len(TIPS)
        sound = SCREEN_SOUNDS.get((screen.name, screen.color)) if web.sounds else None
        return {
            "screen": screen,
            "station": config.station.name,
            "come_back_at": come_back_at,
            "tip": TIPS[tip_index],
            "sound": sound,
            "key": _screen_key(screen),
            "live": True,
        }

    def page(screen: Screen, live: bool = True) -> HTMLResponse:
        template = environment.get_template(f"{screen.name}.html")
        values = context(screen)
        values["live"] = live
        return HTMLResponse(template.render(values))

    def main_part(screen: Screen) -> str:
        """Only the content of <main> (the "content" block)."""
        template = environment.get_template(f"{screen.name}.html")
        values = context(screen)
        block = template.blocks["content"]
        notice = environment.get_template("_notice.html").render(values)
        return notice + "".join(block(template.new_context(values)))

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return page(read_screen())

    @app.get("/events")
    async def events(request: Request) -> StreamingResponse:
        async def stream() -> AsyncIterator[str]:
            # Ask the browser to reconnect quickly when this stream ends.
            yield f"retry: {web.poll_interval_ms}\n\n"
            deadline = time.monotonic() + web.stream_seconds
            # A sign of life three times per watchdog delay of the page.
            alive_every = web.watchdog_seconds / 3
            last = None
            last_sent = time.monotonic()
            while time.monotonic() < deadline and not await request.is_disconnected():
                screen = await run_in_threadpool(read_screen)
                payload = json.dumps({"key": _screen_key(screen), "main": main_part(screen)})
                if payload != last:
                    yield f"event: screen\ndata: {payload}\n\n"
                    last = payload
                    last_sent = time.monotonic()
                elif time.monotonic() - last_sent >= alive_every:
                    yield "event: alive\ndata: \n\n"
                    last_sent = time.monotonic()
                await asyncio.sleep(web.poll_interval_ms / 1000)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/sounds/{name}.wav")
    def sound(name: str) -> Response:
        if name not in sounds:
            raise HTTPException(status_code=404)
        return Response(sounds[name], media_type="audio/wav")

    if web.preview_screens:

        @app.get("/preview/{name}", response_class=HTMLResponse)
        def preview(name: str) -> HTMLResponse:
            screens = preview_screens(long_scan_minutes)
            if name not in screens:
                raise HTTPException(status_code=404)
            # No live updates: the preview must stay on this screen.
            return page(screens[name], live=False)

    return app


def _screen_key(screen: Screen) -> str:
    """Changes when the whole page must be reloaded (not only <main>)."""
    return f"{screen.name}:{screen.color}:{screen.session_id}"


def _environment(theme_dir: Path) -> jinja2.Environment:
    return jinja2.Environment(
        # The theme first, then the plain templates (a missing folder just
        # finds nothing).
        loader=jinja2.ChoiceLoader([
            jinja2.FileSystemLoader(theme_dir / "templates"),
            jinja2.FileSystemLoader(WEB_DIR / "templates"),
        ]),
        # Autoescape: text from the key (unknown codes...) is never HTML.
        # FR : le texte venant de la base (noms de fichiers...) n'est jamais
        # interprété comme du HTML.
        autoescape=True,
        undefined=jinja2.StrictUndefined,
    )
