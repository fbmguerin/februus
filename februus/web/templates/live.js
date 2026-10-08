// Live screen (served by the web UI at /static/live.js, rendered with the
// settings). The server sends the <main> part of the screen when it changes
// (Server-Sent Events), and a sign of life ("alive") in between. Same
// screen: replace <main>. Other screen: reload the page (colors, sounds).
//
// Watchdog: if nothing arrives for web.watchdog_seconds (stream frozen or
// lost, seen with Firefox when the network changes at boot), the screen is
// hidden behind "Station hors service" and the page reloads only once the
// service answers again (a failed reload would leave a browser error page).
// FR : chien de garde : sans nouvelles du service, jamais d'ancien verdict à
// l'écran ; on affiche « hors service » et on recharge quand il répond.
"use strict";

const WATCHDOG_MS = {{ watchdog_ms|tojson }};
// Content of <main> for "Station hors service" (rendered by the server).
const LOST_HTML = {{ lost_html|tojson }};

const source = new EventSource("/events");
// performance.now(): not changed when the clock of the PC is set.
let lastMessage = performance.now();
let lost = false;

source.addEventListener("screen", (event) => {
  lastMessage = performance.now();
  const data = JSON.parse(event.data);
  if (lost || data.key !== document.body.dataset.key) {
    window.location.reload();
    return;
  }
  // HTML rendered and escaped by the server (Jinja2 autoescape).
  document.querySelector("main").innerHTML = data.main;
});

source.addEventListener("alive", () => {
  lastMessage = performance.now();
});

setInterval(() => {
  if (performance.now() - lastMessage < WATCHDOG_MS) {
    return;
  }
  if (!lost) {
    lost = true;
    source.close();
    document.querySelectorAll("audio").forEach((audio) => audio.pause());
    document.body.className = "screen-degraded";
    document.body.dataset.key = "";
    document.querySelector("main").innerHTML = LOST_HTML;
  }
  // "?watchdog": these reloads can be counted in the journal of the service.
  fetch("/", { cache: "no-store" })
    .then((response) => {
      if (response.ok) {
        window.location.replace("/?watchdog");
      }
    })
    .catch(() => {});
}, 2000);
