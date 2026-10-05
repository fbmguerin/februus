// Live screen: the server sends the <main> part of the screen when it
// changes (Server-Sent Events). Same screen: replace <main>. Other screen
// or language: reload the page (colors, sounds). The browser reconnects
// by itself when the connection ends.
"use strict";

const source = new EventSource("/events");

source.addEventListener("screen", (event) => {
  const data = JSON.parse(event.data);
  if (data.key !== document.body.dataset.key) {
    window.location.reload();
    return;
  }
  // HTML rendered and escaped by the server (Jinja2 autoescape).
  document.querySelector("main").innerHTML = data.main;
});
