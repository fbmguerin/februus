# STATUS — Februus

Read this first. Keep it SHORT (about 90 lines). Decisions go to
`docs/decisions.md`, the design to `PLAN.md`.

## Goal

A 100 % working demonstrator on 5 stations of the préfecture, used by the
agents. No certification, no signing: later. Plain explanation:
`docs/HOW-IT-WORKS.md`.

## Where we are (session of 2026-10-06 and 07, branch `fix/f1-first-install`)

- **Code**: simplified (one service `februus`, status in memory, key log,
  plain inspector list, no witness file, no SQLite). Screens in simple FRENCH
  (D16 changed, see `decisions.md`). Notices on screen for two keys and for a
  device blocked by USBGuard. 321 unit tests, CI green.
- **Repositories** (GitHub account `fbmguerin`): `februus` (PUBLIC, MIT, one
  initial commit, this repository), `februus-theme-moselle` (PUBLIC, MIT for its
  own files; the State design system is downloaded by `fetch-dsfr.sh`, never
  stored), `februus-dev` (PRIVATE, full history, old PRs lost),
  `februus-theme-moselle-ancien` (PRIVATE, to delete). Local folders:
  `~/februus`, `~/februus-dev`, `~/februus-theme-moselle-public`; backup of the
  old history: `~/sauvegardes/*.bundle`.
- **Test PC A** (Debian 13 with a desktop): installed, service active, theme of
  the préfecture installed. Checked with real keys: green / orange / red,
  EICAR (also in a zip), encrypted archives, nested zip, timeout, key pulled
  out, `kill -9`, reboot, hub and blocked device, ISO written with `dd`, hashes
  of the keys unchanged (`docs/hardware-validation.md`).
- **Docs**: install guide for a beginner (`docs/INSTALL.md`, `.fr.md`), test plan
  of the second mini PC (`docs/TEST-PC-B.md`, `.fr.md`), README EN/FR. English
  is the reference, `*.fr.md` follow.
- **Tools**: `tools/load-test-key.sh` (two test keys are enough),
  `tools/make-test-files.py`, `tools/station-report.sh`.
- **f1** (development station, ThinkCentre M710q, Debian 13 minimal, no sudo,
  ultra-wide DisplayPort screen, `docs/DEV-STATION.md`): installed with the
  kiosk and the theme. Kiosk at boot OK (9 boots). Fixed on the way (see
  `decisions.md`, 2026-10-06/07): cage `-s` and one rescue console (F2);
  wait for the real GPU driver; no sleep, `consoleblank=0`; sounds (muted
  mixer); frozen screen when the network comes up (watchdog
  `web.watchdog_seconds`, new REQUIRED setting, and Firefox network prefs);
  `systemctl stop` hanging 90 s; stale CSS after an update (`no-cache`);
  cage hung when restarted on another console (`chvt 1`); the kiosk Firefox
  talked to Mozilla (network limit on the kiosk user slice). Results:
  `docs/hardware-validation.md` sections 7, 8 and "f1". Theme fix for wide
  screens: PR #1 of `februus-theme-moselle` (draft).

## Next step: test on the second mini PC (user)

Follow `docs/TEST-PC-B.fr.md` with `docs/INSTALL.fr.md`: Debian 13 without
desktop, Februus, the keys, USBGuard, robustness (power cut), kiosk at boot,
theme, acceptance with an agent who does not know the project. Note every
unclear step of the guide in the friction table, write the results in
`docs/hardware-validation.md` (`PC B 2026-10-xx: ...`), never a result that was
not seen. Then T15.

## Waiting for the user (go on with the rest meanwhile)

- Texts of the screens, the 5 tips and the messages about viruses: to be read by
  someone of the préfecture (simple French).
- Bloc-marque "Préfet de la Moselle" and DSFR theme: the user states that the
  préfecture agreed (2026-10-05); the communication service should confirm the
  use outside `.gouv.fr` and that only text size and kiosk layout are changed.
- A key that once held an ISO and was only reformatted stays RED
  (`device.bootable`: the El Torito record stays before the first partition).
  Fail-closed, kept. Accept (old installer keys must be wiped) or ignore the
  record when a partition table covers the key? (security rule: ask)
- Licence holder in `LICENSE` ("The Februus authors"), and the mentions of the
  préfecture / SIDSIC in `AGENTS.md`, `PLAN.md` and this file: keep or
  generalise. The author of the public commits is "François Guerin"
  (GitHub noreply address).
- Files bigger than the clamd limits (videos > 1 GB): red today; orange with a
  "file not analyzed" message?
- `device.boot_flag`: red or orange (how many real keys have the MBR flag?
  check 5.3 with 10 ordinary keys of the préfecture).
- External hard disks on a USB adapter: allowed like keys. Accept or refuse?
- USBGuard keyboard/mouse rules are tied to their USB port. Wanted? Which
  rescue access?
- Poster: say "one key at a time" (wanted, with a USB extension cable and no
  hub)? IT support contact is a blank line.
- RGPD: the key log keeps only the names of files with a warning, no rotation
  yet; retention time and poster mention to discuss with the DPO before agents
  use a station.
- Questions for the tutor / SIDSIC (later): Linux management tool, mirrors, SMTP
  relay, Zabbix.
- Claude web setup: keep it equal to `tools/claude-web-setup.sh`.

## Tasks (P1)

T0–T9, T11, T12 done (skeleton, config, verdict, ClamAV, session engine, web UI,
real key removal). The simplification project (D16, steps 1 to 4) is finished
and merged.
- [x] T10 USBGuard + udev: checked with real keys (PC A)
- [~] T14 install and one-service `februus.service` checked on PC A (reboot
  OK); kiosk at boot checked on f1 (2026-10-06); still to see on PC B with
  the install guide, and the keyboard shortcuts (8.6), polkit (8.7)
- [ ] T15 full acceptance test (`docs/TEST-PC-B.md`, PLAN.md section 6)
- [~] T16 README, poster, demo (`docs/demo.md`), install guide: to check on PC B

## Known issues

- Speed (f1): plug to red verdict 3.6 s (2 s are `scanner.settle_seconds`).
  ClamAV is the cost of a real analysis (about 9 ms per small file, 18 MB/s;
  Februus adds 5 %): one file at a time, one CPU thread of four. Leads:
  several files at once to clamd (MaxThreads 12), a shorter settle. Mounting
  not measured yet (no green key plugged on f1).
- Lead (not decided): Cog (WebKit kiosk browser, Debian package) instead of
  Firefox: smaller, no UI, but no policy file and all kiosk checks to redo.
- An update needs `watchdog_seconds = 10` in `[web]` of an existing
  `/etc/februus/februus.toml` (install.sh stops and says so).
- Kingston DataTraveler 3.0 on f1: USB 3 errors, disk seen after 1 minute
  or never (hardware); red, never green.
- `test_theme_keeps_the_live_screens_and_the_notice` fails now and then: the
  tip of the idle screen can change during its 1-second stream (old).

- ETA uses bytes: with thousands of small files it shows 0 while minutes are
  left (about 17 ms per file on FAT32). No time estimate for the first second.
- A device blocked by USBGuard before the service starts is not reported on
  screen (only the ones plugged in later).
- No self-test at scanner start and no "station degraded" screen for old
  signatures or clamd down.
- clamd size limits (MaxFileSize 1000M, MaxScanSize 2000M): bigger = red.
- A new required config key makes an old `/etc/februus/februus.toml` invalid
  after an update (wanted: no hidden default).
- polkit lets an active desktop user mount keys: a station must have no desktop
  session (check 8.7 on PC B).
- `kill -9` while a key is mounted: the next session is red ("already mounted"),
  the key must be unplugged (fail-closed).

## Rules for the coding sessions

- `git pull` before working. One working branch at a time, merged quickly.
- Security-sensitive code (`readers/kernel_mount.py`, `inspectors/_layout.py`,
  `core/session.py`, `core/worker.py`, `deploy/`): keep the `# FR:` comments,
  add tests, say in the commit that a review is wanted.
- Never delete a GitHub repository or force-push without the user's explicit
  go; the public repository must never contain the State design system,
  Marianne, a logo, or malware (EICAR is generated at runtime).
