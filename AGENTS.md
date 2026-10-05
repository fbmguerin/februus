# AGENTS.md — Februus

Februus: free "station blanche" (USB sheep-dip). An agent plugs in a USB
key, the station checks it read-only and shows green / orange / red.
Target: 5 stations of a French préfecture (SIDSIC 57), non-technical users.
Goal now: a 100 % working demonstrator. No certification, no signing yet.

Read first: `docs/STATUS.md` (short). Then only what the task needs:
`PLAN.md` (design), `docs/HOW-IT-WORKS.md` (plain explanation),
`docs/decisions.md` (decisions log), `docs/tasks/` (task designs, if any).

## How to work (be autonomous)

- Take the next task from STATUS and finish it: code, tests, `pytest`
  green, docs updated, commit, push, draft PR. Do not wait for approval
  between steps.
- Decide yourself on design choices, small or medium. Write the decision
  (one entry, with the reason) in `docs/decisions.md`. Prefer the simplest
  solution; remove code rather than add it.
- Ask the user ONLY for: a change of a security rule; a dependency that is
  not a Debian 13 package; a feature removed from the user's point of
  view; a step that needs the test PC or a real key (never pretend it was
  done); merging to `main` or deleting branches (unless told to).
  Put other open questions in STATUS and go on.
- The user is a beginner and wants to understand. Talk in French, short,
  plain words, no unexplained jargon (explain a term in half a sentence).
  Summary at the end: what changed, what to check, what is next.
- Stay in scope. No refactoring unrelated to the task. No P2/P3 features.
- If PLAN.md is wrong or blocking, fix it in the same commit and say so.

## Security rules (never break)

1. NEVER execute, open, render or import a file from a scanned device.
   Analyzers only read bytes.
2. NEVER send file contents off the station (no cloud, no VirusTotal).
3. FAIL-CLOSED: exception, timeout, unknown finding code or unexpected
   state = RED. Never green by default.
4. Media are mounted `ro,noexec,nosuid,nodev` by udisks2 (D7); real
   options checked in mountinfo. No Februus code runs as root.
5. Least privilege: scanner and analyzers unprivileged, no network
   (only `freshclam` uses the network); the web UI reads the data only.
6. Nothing is ever written on a scanned key.
7. Everything read from a key is untrusted input: validate it.
8. Test malware = EICAR only, generated at runtime. Never commit malware.

## Design rules

- Keep it simple: few moving parts, each one explainable in two lines.
- Checks (inspectors, analyzers) return findings with stable codes
  (`clamav.detected`, `device.bootable`...). The verdict engine maps codes
  to colors from the TOML; unknown code = red; worst color wins.
- Tunable values (colors, delays, limits, paths) live in
  `/etc/februus/februus.toml`, validated at startup. None in code.
- systemd units only start services and apply hardening.
- Human docs with a French version (`README`, `docs/INSTALL`, `docs/HOW-IT-WORKS`,
  files `*.fr.md`): English is the reference and the default; each `*.fr.md`
  says so at the top. Change the English first, then the French one.
- Web UI: simple French only (D16, changed on 2026-10-05), written in the
  templates and in `web/messages.py` (no translation system). The rest of
  the code and the logs: plain English.
- The simplification project (STATUS, D16) removed the witness file, the
  translations, `write_protect`, SQLite, the separate services and the
  plugin registry: do not bring them back. Inspectors are plain functions
  in a fixed list; analyzers are chosen in `[analyzers]`; the reader is
  chosen by the command (`serve`: `kernel_mount`; `scan`, `demo`: `directory`).

## Code conventions

- Python 3.13 (Debian 13), PEP 8, type hints, short docstrings.
- Simple English in identifiers and comments. Security-critical comments
  are doubled in French: `# FR: ...`.
- snake_case, PascalCase for classes, UPPER_SNAKE_CASE for constants.
- Prefer Debian packages (apt) over pip.

## Environments

- Claude Code web / Codespaces: everything except real USB. The
  `directory` reader runs the whole pipeline on a folder. The web setup
  script is `tools/claude-web-setup.sh` (keep it in sync with the
  environment settings). The web setup installs fastapi, jinja2 and
  httpx for `test_web.py`.
- Test PC / station (Debian 13): USBGuard, udev, udisks2, kiosk, real keys.
  Checklist: `docs/hardware-validation.md`.
- Tests needing clamd or hardware are marked (`clamav`, `hardware`) and
  skipped when unavailable. CI runs the unit tests only.

## Commands

- `pytest` — unit tests (`pytest -m clamav` for ClamAV tests)
- `februus config check [-c config/februus.dev.toml]` — validate the config
- `februus scan -c config/februus.dev.toml <folder>` — run the pipeline
  (exit code 0 green, 1 orange, 2 red)
- `februus web -c config/februus.dev.toml` — only the screens, on
  http://127.0.0.1:8080 (previews: `/preview/<screen>`)
- `tools/demo.sh [green|red|long]` — demo: the screens and a simulated key
  (`februus demo -c <config> <folder>`: Enter inserts / removes the key)
- `februus inspect -c config/februus.dev.toml <image>` and
  `python3 tools/demo-images.py <folder>` — inspectors on disk images
- `februus serve -c <config>` — the one service of a station (keys,
  analysis and screens)
- `sudo deploy/install.sh [--name f3] [--no-apt] [--usbguard] [--kiosk]` —
  install or update a station; logs: `journalctl -u februus`
- `februus stats [--days N]` — statistics from the key log
- `sudo tools/load-test-key.sh /dev/sdX <kit>` — erases a TEST key and loads
  a kit (eicar, two-partitions, iso...): two keys are enough for the whole
  acceptance test (`docs/TEST-PC-B.md`); `tools/make-test-files.py` makes the
  files; `sudo tools/station-report.sh` — read-only report of a station
