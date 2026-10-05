# STATUS — Februus

Read this first. Keep it SHORT (about 90 lines). Decisions go to
`docs/decisions.md`, the design to `PLAN.md`.

## Goal

A 100 % working demonstrator on 5 stations of the préfecture, used by the
agents. No certification, no signing: later. Plain explanation:
`docs/HOW-IT-WORKS.md`.

## Simplification project (decided 2026-10-04)

Decisions (see `docs/decisions.md`, D16): web UI in very simple English
only (CHANGED on 2026-10-05: simple French, see the end of `decisions.md`); no witness file, nothing is written on a key; `write_protect`
inspector removed; inspectors `bootable`, `filesystem`, `partitions` kept
(colors in the TOML: several Windows partitions = orange; bootable or not
FAT32/exFAT/NTFS = red); ClamAV signatures by `freshclam` (stations have
network, only freshclam uses it).

Steps, in this order (do them without asking, one PR per step, tests green):

1. [x] Plain docs (`HOW-IT-WORKS.md`), shorter guides, T14b merged.
2. [x] Removed the witness file, the translations (texts are in the
   templates, simple English) and the `write_protect` inspector (see
   `docs/decisions.md`, 2026-10-04, step 2).
3. [x] One service (`februus serve`), status in memory, key log (one line
   per key) instead of SQLite, analyzer service removed (see
   `docs/decisions.md`, 2026-10-04, step 3, D17).
4. [x] (merged into main 2026-10-05, PR 12) Plugin registry removed: inspectors are plain functions in a fixed
   list, analyzers are chosen in `[analyzers]`, the reader is chosen by the
   command; fewer TOML settings (see `docs/decisions.md`, 2026-10-04,
   step 4, D18).
5. [ ] Finish T14 (kiosk, reboot, firewall), then T15 on real keys.

## Waiting for the user (go on with the rest meanwhile)

- Test PC (2026-10-05): installed, `februus.service` active; checks 2.4,
  2.5 (synthetic ISO with `dd`), 2.10 (green, orange, red) and 7.1 to 7.11
  done with two real keys and EICAR (`docs/hardware-validation.md`). Old
  database and account `februus-web` deleted (the service runs without
  them). 7.12 (reboot) done. Hubs stay blocked (user decision 2026-10-05, check 5.4). Kiosk tested in a window only (hardware-validation section 8: screen and Firefox policies OK); left: the kiosk at boot on a PC without desktop session (test B), a real Debian ISO.
  One key at a time is wanted (decisions.md, 2026-10-05): USB extension
  cable, mini PC under a piece of furniture, no hub. A screen notice tells
  the agent to remove the second key (done, checked on the test PC).
- Claude web setup: keep it equal to `tools/claude-web-setup.sh` (no
  `babel`; the venv of this session had no fastapi/jinja2/httpx).
- Screens and posters now quote the same French titles: the texts (screens,
  tips, messages) are to be read by someone of the préfecture.
- Hardware checks at the test PC (never pretend they were done; results go
  in `docs/hardware-validation.md`): section 7 (main risk: clamd under
  AppArmor and descriptors given by the analyzer child; if it fails, ask:
  INSTREAM), real key
  removal during the analysis, ISO written with `dd`, key behind a hub,
  more keys, `--name`.
- Files bigger than the clamd limits (videos > 1 GB): red today; orange with
  a "file not analyzed" message?
- `device.boot_flag`: red or orange (how many real keys have the MBR flag?).
- External hard disks on a USB adapter: allowed like keys. Accept or refuse?
- USBGuard keyboard/mouse rules are tied to their USB port. Wanted? Which
  rescue access?
- RGPD: the key log keeps only the names of files with a warning, no
  rotation yet; retention time and poster mention to discuss with the DPO
  before agents use a station.
- Questions for the tutor / SIDSIC (later): Linux management tool, mirrors,
  SMTP relay, Zabbix. Poster: IT support contact (blank line).

Public release prepared (2026-10-05): MIT licence (`LICENSE`), components
checked (`docs/CREDITS.md`). Before making the repository public, decide:
the name and e-mail of the
commit author in the history, the mentions of the préfecture / SIDSIC in
AGENTS, PLAN and STATUS. Test B (second mini PC): `docs/hardware-validation.md`
section 9.

Theme (2026-10-05): the screens take an optional theme
(`install.sh --theme`, `deploy/theme-example/`); the DSFR / Préfet de la
Moselle theme is in the PRIVATE folder `~/februus-theme-moselle` (local git
repo, to push to a private repository). To validate with the communication
service of the préfecture; UI texts in French (D16 changed).

Install guide for a beginner (copy and paste): `docs/INSTALL.md`, French
version `docs/INSTALL.fr.md`; README and HOW-IT-WORKS also in French
(`*.fr.md`, English is the reference; keep them in sync) (written
2026-10-05; to try on the second mini PC and correct where it fails).

## Tasks (P1)

T0–T9 done (skeleton, config, verdict, ClamAV, session engine, web UI).
T11, T12 done and checked with one real key (T13, the witness file, and
T14b, the analyzer account, were removed in steps 2 and 3).
- [~] T10 USBGuard + udev: checked on the test PC with a real key
- [~] T14 install.sh and the one-service `februus.service` checked on the
  test PC (2026-10-05, reboot OK; kiosk not tested); kiosk written, NOT tested (needs a
  PC without desktop session)
- [ ] T15 full acceptance test (PLAN.md section 6)
- [~] T16 README, poster, demo (`docs/demo.md`): install section waits for T14

## Known issues

- ETA uses bytes: with thousands of small files it shows 0 while minutes
  are left (about 17 ms per file on FAT32).
- A device blocked by USBGuard before the service starts is not reported on screen (only the ones plugged in later).
- No self-test at scanner start and no "station degraded" screen (old
  signatures, clamd down).
- clamd size limits (MaxFileSize 1000M, MaxScanSize 2000M): bigger = red.
- A new required config key makes an old `/etc/februus/februus.toml`
  invalid after an update (wanted: no hidden default).
- polkit lets an active desktop user mount keys: a station must have no
  desktop session (check at T14).
- No time estimate before the first measure (about 1 s): the history of
  earlier keys was removed with SQLite.

## Rules for the coding sessions

- `git pull` before working. One working branch at a time, merged quickly.
- Security-sensitive code (`readers/kernel_mount.py`,
  `inspectors/_layout.py`, `core/session.py`, `core/worker.py`, `deploy/`):
  keep the `# FR:` comments, add tests, say in the commit that a review is
  wanted.
