# Decisions log — Februus

One entry per decision taken during development: date — decision —
reason. Newest at the end. Important ones are also copied to PLAN.md
section 10 (D1, D2...). Moved here from docs/STATUS.md on 2026-10-02
to keep STATUS short.

- 2026-10-01 — STATUS.md moved to `docs/STATUS.md` — match AGENTS.md and
  PLAN.md section 6.
- 2026-10-01 — D7: mount with udisks2 + polkit, no home-made root service —
  user prefers a popular, maintained tool for sensitive parts. To check on
  the mini-PC at T12 (forced `ro,noexec,nosuid,nodev`, write refused).
  PLAN.md and AGENTS.md updated (no februus-mountd any more).
- 2026-10-01 — Claude Code web sessions are prepared by the environment
  setup script; reference copy in `tools/claude-web-setup.sh` (Ubuntu 24.04
  container: Python 3.13 venv in `/opt/februus-venv` + pytest, ClamAV from
  apt, signatures, clamd). Codespaces uses `.devcontainer/` (Debian 13).
- 2026-10-01 — T0 checked in Codespaces by the user: ClamAV 1.4.3 with
  signatures (clamd answers), Python 3.13.5, pytest 8.3.5.
- 2026-10-04 — History note: the entries below about the witness file
  (T13, T10/T12, reviews), `write_protect` (T11) and translations (T8, T9,
  i18n) describe code removed in step 2 (see 2026-10-04, step 2, at the
  end). They are kept as history.
- 2026-10-01 — i18n applies to the web UI only. CLI, logs and services use
  plain English; important comments doubled in French.
- 2026-10-01 — T1: CLI with `argparse` (stdlib); packaging with setuptools
  (`pyproject.toml`, version in `februus/__init__.py`); tests import the
  code without install (`pythonpath = ["."]`). CI runs in a `debian:trixie`
  container with Debian packages and a `--system-site-packages` venv, same
  as the devcontainer. No licence declared yet (P4).
- 2026-10-01 — T2: config validated by a small hand-written validator
  (`februus/core/config.py`, no dependency). No default values in code:
  every key is required (station name optional, falls back to hostname).
  Unknown keys are errors. All errors are reported at once. `conf.d/*.toml`
  merged in alphabetical order (tables merged, values replaced).
  FAIL-CLOSED: at least one reader and one analyzer required. Example
  values chosen by Claude, to review: file timeout 120 s, session timeout
  240 min, witness keeps 10 passes. Module names are checked against the
  registry at T4. `[paths]` became `[database]` (path, busy_timeout_ms).
- 2026-10-01 — T3: schema in `februus/core/db.py` (devices, sessions,
  files, findings, events), version in `PRAGMA user_version`, unknown or
  newer version refused. CHECK constraints enforce fail-closed rules in
  the database itself: a finished session has a verdict, an aborted one is
  red. Web UI: `connect_readonly` (URI `mode=ro` + `query_only`). Data
  access functions come with the tasks that need them (T7).
- 2026-10-01 — T4: modules found by convention, `februus/<type>/<name>.py`
  exposing `MODULE` (no entry points, no install needed; name checked by
  regex before import). Options in `[module.<name>]`, validated by the
  module with the same `TableReader` as the config; constructors have no
  side effect. A module name is used only once across types.
  `config check` also loads the modules. Dev config
  `config/februus.dev.toml` (directory reader + fake analyzer). The fake
  analyzer emits `fake.clean` / `fake.detected`, absent from production
  rules, so it can only give RED on a real station.
- 2026-10-01 — T5: `februus/core/verdict.py`. Unknown code, bad rule value
  or unexpected color = RED; worst color wins; no finding = GREEN (the
  session engine, T7, must add `internal.error` if a file was not
  analyzed).
- 2026-10-01 — T6: `februus/analyzers/clamav.py` talks to clamd directly
  (no dependency): the file is opened with O_NOFOLLOW and its descriptor
  passed with FILDES (clamd needs no access to the key, no stream limit).
  Heuristics.Encrypted.PDF -> pdf.encrypted, Heuristics.Encrypted.* ->
  archive.encrypted, Heuristics.Limits.Exceeded.* -> scan.limit_exceeded,
  other FOUND -> clamav.detected, OK -> no finding, anything else raises
  (-> internal.error at T7). Required clamd settings (AlertEncrypted,
  AlertExceedsMax, sizes) in `deploy/clamav/clamd-februus.conf`, applied
  by the devcontainer and the Claude Code web setup script. Test samples
  (EICAR, encrypted zip/PDF, nested zip) generated at runtime in
  `tests/samples.py`.
- 2026-10-01 — T7: `februus/core/session.py` + `store.py` (DB access) +
  `worker.py`. Analyzers run in one "spawn" worker process, one file at a
  time; on file timeout the worker is killed (`scan.timeout`) and
  restarted; analyzer exception or worker crash -> `internal.error`.
  Session timeout -> `scan.timeout`, remaining files unanalyzed. Any
  unexpected exception -> `internal.error`. A file left unanalyzed without
  reason -> `internal.error`. Inventory never follows symlinks; non-regular
  entries -> `file.not_regular` (not in the rules: red, tunable). ETA:
  first estimate from the average speed of the last N sessions, then
  measured speed. New `[scan]` keys: `progress_update_seconds`,
  `eta_history_sessions`. `februus scan` exit code: 0 green, 1 orange,
  2 red. The first configured reader is used.
- 2026-10-01 — T8: dependencies approved by the user: python3-fastapi,
  python3-uvicorn, python3-jinja2, python3-babel, plus python3-httpx (tests
  only, needed by the FastAPI test client). `februus/web/`: `app.py`
  (read-only DB; any error -> "degraded" screen, never an old result),
  `screens.py` (screen from the last session; unknown state -> degraded),
  `i18n.py` (.po compiled in memory at startup, no .mo file; a missing
  catalog is a config error), `messages.py` (text per finding code;
  unknown code -> generic message with the code). Language: cookie
  "lang:session id", reset when a later session is closed. `/preview/<name>`
  only if `web.preview_screens` (dev). New config keys: `web.host`,
  `web.port`, `web.preview_screens`. New column `sessions.closed_at` (key
  removed after the result -> idle screen); schema kept at version 1 as it
  was never deployed (delete old dev databases). A test renders every
  screen in a pseudo-language to prove no text is hardcoded.
- 2026-10-01 — T9: `/events` (Server-Sent Events) sends the rendered
  `<main>` and a screen key when they change; `static/live.js` replaces
  `<main>`, or reloads the page when the key changes (screen, verdict,
  session, language). Each stream lasts `web.stream_seconds`, then the
  browser reconnects. Long scan: "come back at HH:MM" (local time, Babel
  format) when the ETA exceeds `scan.long_scan_warning_minutes`. Idle:
  rotating tips (`messages.TIPS`, every `web.tip_change_seconds`) and the
  last signatures version (stored per session from `Module.version()`;
  clamd 1.4.3 always answers VERSION: no setting needed, see 2026-10-02).
  Sounds generated in memory with `wave` (no binary in the repo): green,
  orange, red alarm in a loop (also for key removed too early);
  `web.sounds` to disable. New commands: `februus db init`,
  `februus session close` (dev: simulates key removal after the result).
  Demo: `tools/demo.sh [green|red|long]` (fake analyzer `delay_ms`).
- 2026-10-01 — T13 (done before T10-T12, on the user's request):
  `februus/witness/file.py` (format schema 1, `signature` always null),
  `hidden.py` (FAT/exFAT ioctl, NTFS xattr; used by `kernel_mount` at
  T12, `pytest -m hardware` with FEBRUUS_FAT_DIR). Existing witness read
  with a size limit (`witness.max_read_bytes`), O_NOFOLLOW, every field
  validated; invalid passes dropped, invalid file ignored (event
  `witness.invalid`); it never changes the verdict. Written through the
  reader (`Reader.write_file`, default: cannot write) only after green or
  orange, checked again in `write_witness` (a red key is never written).
  Write failure or write-protected key -> `witness.not_written` (orange
  in the example rules, to validate). New `[witness]` keys: `enabled`,
  `filename`, `max_read_bytes`. `februus stats [--days N]`: sessions by
  verdict, files and bytes analyzed (read-only connection).
- 2026-10-01 — T11 (prepared without hardware): inspectors receive a
  `BlockDevice` (path, size, read_only, `read_at`) instead of a path:
  `ImageDevice` for tests/dev, the udisks2 device (OpenForRead, no root
  for the scanner) comes with T12. `februus/inspectors/_layout.py` reads
  MBR/GPT/"no table" and file system magic bytes; any inconsistency
  raises (-> internal.error, red). Inspectors: `partitions`
  (device.multi_partition), `bootable` (device.bootable: El Torito ISO,
  EFI system or BIOS boot partition; device.boot_flag: MBR active flag
  only, red for now, to check with real keys), `write_protect`
  (device.write_protected), `filesystem` (filesystem.unsupported, option
  `supported`). The session runs the inspectors first when a device is
  given; if they already give red, the source is never opened (event
  `device.refused`). `februus inspect <image> [--read-only]`.
- 2026-10-01 — Code review of the whole code base (on the user's
  request), fixes:
  - Partition table read like the kernel: a first sector with valid
    "boot" bytes is a partition table even if it holds file system magic
    bytes (a crafted key could hide an EFI partition). GPT checksums
    checked, backup GPT used if the primary is invalid, hybrid MBR
    entries inspected, logical partitions (EBR chain) listed.
  - Witness: any ValueError (huge integer...) only makes it invalid.
    Everything is committed before writing it, nothing fallible after.
  - Findings committed after each file (a detected virus survives a later
    error). Sessions left unfinished (crash) become red before the next
    one (`store.fail_interrupted_sessions`, also for the scanner at T10).
  - Language cookie: reset after the session of the person who chose it.
  - `station.name`: printable, at most 64 characters (witness limit).
  - Not changed: the layout is parsed by each inspector (a few KB read,
    simpler independent modules).
- 2026-10-01 — T10/T12 prepared without hardware (user approved
  python3-pyudev and the udisksctl approach):
  - `februus scanner`: `scanner/udev.py` (pyudev, USB disks only, keys
    already plugged in at startup, extended partitions skipped) feeds
    `scanner/service.py` (one key at a time, session in a thread with its
    own SQLite connection; removal during the session -> cancel -> state
    aborted, red, `device.removed`, back to idle after
    `scanner.removed_screen_seconds`; removal after the result -> closed).
    A device that cannot be opened becomes an "unavailable" device: the
    inspectors fail -> red, never mounted.
  - Sessions take several sources: every partition is analyzed (paths
    prefixed with the partition name), witness on the first one.
    Cancellation checked every `scan.cancel_check_ms`, also inside a long
    file (worker killed).
  - `readers/kernel_mount.py`: `udisksctl mount -o ro,noexec,nosuid,nodev`,
    then the real options and file system are checked in
    /proc/self/mountinfo (else unmount, red). Witness: unmount, mount
    `rw,noexec,nosuid,nodev` (checked), atomic write + fsync, hidden
    attribute, unmount. Unmount errors after the analysis are logged, they
    do not change the verdict (closes the T12 open point of the review).
  - `core/devices.py` KernelDevice: raw read of /dev/sdX (udev rule gives
    the februus group read access), read-only flag from sysfs.
  - deploy/: udev rule, udisks2 mount_options.conf, polkit rule, USBGuard
    rules (mass storage only, single interface).
  - Example config now passes `config check` (local_log notifier removed
    from it until it is written).
- 2026-10-01 — After the user's review of PR #4: key removed while the
  witness is written -> red "removed" (cancel checked again at the end);
  a leftover `.februus.json.tmp` (interrupted write) is removed instead of
  blocking every later witness; a partition already mounted, or mounted
  twice, is refused; mountinfo format tests; fuzzing of the layout parser
  (only LayoutError, random images never green). Hardware checklist:
  `docs/hardware-validation.md` (must pass before using the station).
- 2026-10-01 — Second review (whole repository), checked one by one. Real
  issues fixed: the inventory is now bounded (new `scan.max_entries` ->
  scan.limit_exceeded, session timeout and key removal checked for each
  folder: a crafted key with millions of folders can no longer block the
  station); file system detection never reads beyond its partition.
  Already handled (no change): GPT entries limit (128), witness size limit,
  disk full when writing the witness (witness.not_written), HTML escaping
  of file names (Jinja2 autoescape + test), no default config values (by
  design, `config check`). kernel_mount, scanner and KernelDevice exist
  in PR #4 (waiting for the hardware).
- 2026-10-01 — T16 written while waiting for the hardware: README in
  English (status, verdicts, security principles, architecture, try it on
  a folder; install section left for T14). A4 poster for the agents in
  `docs/poster/` (FR and EN, HTML printed from a browser, texts taken from
  the screens, blank line for the IT support contact). Demonstration
  script in French, `docs/demo.md` (version A in Codespaces with real
  ClamAV and EICAR, version B on the mini-PC). `tools/demo-images.py`
  writes synthetic key images for `februus inspect` (reuses the test
  helpers). Fix: `februus inspect` on a missing file printed a traceback.
  Separate PR from PR #4 (T10/T12, waiting for the hardware), so the docs
  can be merged now; parts that only exist in PR #4 are marked as such.
- 2026-10-02 — Hardware validation on a test PC (Debian 13 + LXQt, one
  SanDisk key reformatted for each case; results and limits in
  `docs/hardware-validation.md`). Fixes:
  - clamd 1.4.3 (Debian 13) refuses `EnableVersionCommand` and did not
    start: line removed from `clamd-februus.conf`.
  - FAIL-OPEN found: clamd answers "OK" for a file it could read only in
    part (damaged sectors, key pulled out). The worker now reads every
    file itself before the analyzers (`worker._check_readable`); a read
    error gives `internal.error` (red). Cost: a file bigger than the free
    memory is read twice from the key.
  - A bootable ISO inside a partition (Debian live key) is now
    `device.bootable` (El Torito searched in each partition).
  - Key pulled out during the inventory: the read error came before the
    removal event and the session ended as `internal.error`. After an
    unexpected error, the session now waits one `scan.cancel_check_ms`
    for the removal event and ends as "key removed" (aborted, red).
  - Test PC setup: accounts `februus` and `februus-web` (system, no home,
    no shell), rules of `deploy/` installed, `/etc/februus/februus.toml` =
    example config, `/var/lib/februus` owned by `februus` (0750), ACL
    `februus:x` on `/home/<user>` to run the code from the clone.
    USBGuard stopped during sections 1 to 4, then enabled with the Februus
    rules (station keyboard and mouse + `deploy/usbguard/rules.conf`).
    openssh-server installed for section 5 (to remove if not wanted).
- 2026-10-02 — Fixes after the validation: `kernel_mount` stops waiting
  for udisksctl when the key is gone (new option `device_check_ms`; was
  ~20 s, now 0.1 s); findings stored before a crash become red (they were
  not shown on the screen); `februus stats` prints a clear error.
- 2026-10-02 — T14, first part (checked on the test PC, PLAN.md D13/D14):
  - `deploy/install.sh` (can be run again): packages, accounts, code
    copied to `/opt/februus` (root, read-only) with a small launcher
    `/usr/local/bin/februus` — no venv and no pip on a station, only
    Debian Python packages. Options `--no-apt`, `--usbguard` (generated
    rules of the devices plugged in + Februus rule; old rules restored if
    a keyboard or mouse ends up blocked), `--kiosk` (not tested).
  - Database: `/var/lib/februus` is `februus:februus-web` mode 2750
    (`deploy/systemd/februus.tmpfiles`), scanner `UMask=0027`: the web
    account can only read the files. SQLite reads a WAL database
    read-only only while its `-wal`/`-shm` files exist, so the scanner
    keeps one connection open.
  - Scanner lock `<database>.scanner` (`core/presence.py`, flock released
    by the kernel when the process dies). Web: scanner not running =
    "station out of service", never the last result (it stayed green on
    the screen). New key `web.require_scanner` (false in the dev config).
    Also refuses a second scanner.
  - `februus-web.service`: full hardening (ProtectSystem=strict, local
    network only, no devices; systemd-analyze exposure 1.1).
  - `februus-scanner.service` (exposure 2.6): no IP network
    (`IPAddressDeny=any`), no capability, `sd*` devices read-only. NOT
    `PrivateNetwork` (no udev events in a private network namespace) and
    NO mount namespace (ProtectSystem, ProtectHome, PrivateTmp,
    ProtectKernel*, ProtectProc): clamd under AppArmor then refuses the
    file descriptors ("disconnected path") and every key is red.
  - Checked with the services: EICAR red, clean key green + witness,
    removal, kill -9 (restarted by systemd, session red), scanner stopped
    (out of service screen). Not checked: a reboot, the apt step on a
    fresh system, the kiosk.
- 2026-10-02 — Simplification pass on the code of the day: one helper
  `core.files.open_regular` (no symlink, regular file only) for the worker
  and the ClamAV analyzer; `session._colors`; `kernel_mount._run(action,
  source, *options)`. It fixed a defect of the same day: for a mount, the
  "is the key still there" check looked at the options instead of the
  partition, so a mount longer than `device_check_ms` would have been
  stopped (test added).
- 2026-10-02 — Look of the web UI (user's choices): the name "Februus" in
  Cinzel Decorative at the top of every screen, everything else in Cinzel
  (capitals and small capitals). Cerberus on every screen, at the bottom
  right, shown in the color of the screen (CSS blend "luminosity" + a
  gradient: almost plain color under the texts on the left, lighter over
  the heads); the verdict color stays the dominant color. No station name
  on the screens any more. Fonts (OFL) and picture are files of
  `februus/web/static/`, nothing is loaded from the Internet (test).
  Sources and licences: `docs/CREDITS.md`.
- 2026-10-02 — Look of the web UI, second pass (user's choices): Cinzel
  Decorative only for the name "Februus"; every other text in DejaVu Sans
  (Debian font, readable from far away; Cinzel removed). Layout: a top bar
  (name, languages) and a bottom bar (station name, antivirus signatures)
  frame one column of text on the left; the three share the same margin;
  same space between blocks; text size follows the screen height
  (checked at 1920x1080 and 1280x1024). Station name back on every
  screen (the support must know which station a user calls about).
  Station names: f1, f2, ... f12 (no leading zeros), normally the
  hostname.
- 2026-10-02 — `install.sh --name f3`: sets the machine name (hostname
  and the 127.0.1.1 line of /etc/hosts), checked before anything else
  (lowercase letters, digits, "-"). The station name is the hostname
  unless `station.name` is set (the script says so). Remote settings for
  the 6 stations: Ansible from an admin PC over SSH is the proposal (P3,
  waiting for the tools the SIDSIC already uses).
- 2026-10-02 — Handoff to other coding models: the decisions log moved
  from STATUS.md to this file; STATUS.md keeps only the next tasks, what
  waits for the user, open questions and rules for the sessions.
  Prepared tasks get a design file in `docs/tasks/`.
- 2026-10-02 — T14b approved by the user: analyzers under their own
  account `februus-analyzer`, started by systemd socket activation (one
  process per connection), files passed as descriptors, analyzer API
  takes an open file. Design: `docs/tasks/T14b-analyzer-account.md`.
- 2026-10-02 — T14b written (no hardware; D15 in PLAN.md). Changes to
  the design sheet, approved by the user:
  - Socket `root:februus 0660` (not owned by `februus-analyzer`): the
    analyzer account gets the accepted connection from systemd and has
    no right to connect itself (it could have started more analyzers).
  - Supervisor process instead of a watchdog thread: `februus analyzer`
    forks before loading the analyzers; the parent only polls the
    connection (hang-up events, never reads) and the child (pidfd), and
    does `kill -9` on the child when the scanner closes. A thread could
    not run while C code holds the Python lock (future macro/YARA
    parsers); the kill is done by the kernel.
  - Exit code 0 when the scanner closes the connection (end of session,
    timeout, key removed: the verdict is the scanner's job). Non-zero
    only for a real failure (child crashed). `CollectMode=
    inactive-or-failed`: no instance is kept; check with
    `systemctl list-units --all`.
  - `core/session.py` changes by two lines (the `[analyzer_service]`
    table and the relative file name go to the worker); no behaviour
    change, its tests pass unchanged except the three that used private
    parts of the worker.
  - Local mode (`enabled = false`): a child process of the scanner
    speaking the same protocol over a socketpair, running the same
    `serve()`; the scanner still kills it itself (no supervisor there).
    One code path, the protocol is tested by the CI without systemd.
  - Scanner unit: `Wants=`/`After=februus-analyzer.socket` (not
    Requires: without the socket the keys are red, the scanner keeps
    running). No `RuntimeDirectory=februus` in it (it would remove the
    socket when the scanner stops).
  Also: both sides validate the messages (the scanner only accepts
  findings of the configured analyzers); the analyzer refuses a
  descriptor that is not a regular file opened read-only; the service
  rewinds the descriptor before each analyzer. Symlink and "not a
  regular file" checks now live only in the scanner (`open_regular`).
  Checked here without root: `systemd-socket-activate --accept --inetd`
  + real clamd + EICAR from a folder: red, analyzer ended with code 0.
  A new required table `[analyzer_service]`: an existing
  `/etc/februus/februus.toml` must get it (install.sh stops at
  `config check` otherwise).
- 2026-10-02 — T14b, fixes after a code review of the commit:
  - The worker checks the timeout and the removal of the key before
    EVERY read of the answer (an analyzer answering byte by byte went
    past both), and the connection and the request have the file timeout
    (a service that does not accept blocked the scanner).
  - The analyzer process builds the analyzers only
    (`service.load_analyzers`): no reader, inspector or notifier, nor
    their options, in the process that reads hostile content.
  - A local analyzer process that cannot start gives `WorkerDied`.
  - `install.sh` checks an existing configuration with the NEW code
    before replacing `/opt/februus`: a missing new key stops the update
    with nothing changed (it stopped after the code was replaced).
  Not changed, to decide: in service mode the analyzer is killed just
  after the scanner closes the connection, not before `stop()` returns
  (see STATUS).
- 2026-10-04 — D16: simplification project. Februus is a demonstrator on 5
  stations, used by the agents; certification and signing come later.
  Decided with the user: web UI in very simple English only (no gettext);
  no witness file (nothing is written on a key) and no `write_protect`
  inspector; inspectors `bootable`, `filesystem`, `partitions` kept, with
  colors in the TOML (several Windows partitions = orange, bootable or
  not FAT32/exFAT/NTFS = red, worst color wins); ClamAV signatures by
  `freshclam` (stations have network, scanner stays offline). Next: one
  service, log file instead of SQLite, plain function list instead of the
  plugin registry (see STATUS). Guides shortened (AGENTS, PLAN, STATUS)
  and Claude works more autonomously (AGENTS.md "How to work").
- 2026-10-02 — (moved from the closed PR 6) Development mini-PC: Debian 13 +
  LXQt, automount of removable media disabled in PCManFM-Qt (it would
  mount test keys read-write before Februus). Production stations: clean
  minimal install, no desktop, SSH server + standard utilities only.
  Partitions: separate `/`, `/var`, `/tmp`, `/home`, swap; no LVM, no
  encryption (the station must boot unattended). Separate `/var`: ClamAV
  signatures, data and logs cannot fill `/`. Disk-backed `/tmp` (not
  tmpfs): clamd unpacks archives there; mount options `noexec,nosuid,
  nodev` to set at T14. `install.sh` and the acceptance test (T15) assume
  this layout.
- 2026-10-04 — CI and devcontainer install `procps`: the T14b analyzer
  tests use `pgrep`, missing in the minimal Debian image (CI was red on
  `main` after the T14b merge).
- 2026-10-04 — Simplification, step 2 (D16): witness file, translations and
  `write_protect` removed. Nothing is written on a key any more.
  - Witness: `februus/witness/`, `Reader.write_file`, `files.write_atomic`,
    the `[witness]` table, the session state `writing_witness`, the codes
    `witness.not_written` / `device.write_protected` and the events
    `witness.*` are gone. `kernel_mount` has one single path: one read-only
    mount (`ro,noexec,nosuid,nodev`, checked in mountinfo) and one unmount
    that never raises. Security rule 6 now has tests (session, scanner,
    kernel_mount) and a new hardware check (2.10).
  - Check removed in `core/session.py`: the one after the unmount of the
    sources (its only reason was the witness write). A key pulled out during
    that last unmount no longer turns a finished analysis red. The check
    just after the scan stays (new test). Review wanted: `core/session.py`,
    `readers/kernel_mount.py`.
  - Translations: Babel, `.po` files and `web/i18n.py` removed; texts are
    written in the templates and `web/messages.py` (very simple English);
    no language bar, no `/lang/<code>` (404), no cookie; `Screen.closed`
    removed (only the language reset used it). Plurals: a one-word test in
    the template. "Come back at" is now the local time in 24 h ("17:19"),
    from `strftime`, instead of the Babel format ("5:19 PM"). Babel is no
    longer a dependency (`pyproject.toml`, `install.sh`, CI, devcontainer,
    web setup script).
  - `write_protect`: inspector, `BlockDevice.read_only`, `ImageDevice(...,
    read_only)` and `februus inspect --read-only` removed (nothing else used
    them).
  - Config: removed `[witness]`, `web.languages`, `web.default_language`,
    `web.reset_language_after_session`, the `write_protect` inspector and
    the two rules. An old `/etc/februus/februus.toml` is now invalid
    ("unknown key"): `install.sh` stops with the list and changes nothing.
  - Database: schema version stays 1; only `writing_witness` left the
    allowed states. An old database accepts it still, no migration (step 3
    replaces SQLite).
  - Docs: README, AGENTS, PLAN, demo, posters and the hardware checklist
    updated (old hardware results kept; rows about the witness marked
    removed). Not touched: `docs/CREDITS.md`.
- 2026-10-04 — Simplification, step 3 (D16, D17): one service, status in
  memory, key log, no analyzer service.
  - One service `februus` (`februus serve`, `deploy/systemd/februus.service`
    replaces scanner, web and analyzer units). The key watcher runs in a
    thread, the screens (uvicorn) in the main thread. If the watcher stops,
    the screens show "out of service" and the service stops itself
    (SIGTERM), systemd starts it again. This replaces the scanner lock file
    (`core/presence.py`). The port of the screens is taken before the keys
    are watched, so a second service stops there and never analyzes a key. The unit keeps the scanner's hardening (no mount
    namespace: clamd under AppArmor) and allows the loopback network for
    the screens. Trade-off: the web code now runs in the process that
    mounts keys; it only reads a snapshot (`core/status.py`) and listens
    on 127.0.0.1 only. Security rule 5 still holds (no account has more
    rights than before; the web UI reads only).
  - Status in memory: `core/status.py` (`SessionStatus` snapshot, `Status`
    with a lock). The session thread writes, the screens read. SQLite
    (`core/db.py`, `core/store.py`, the tables of files, findings and
    events, interrupted-session recovery, ETA history) is gone. After a
    crash the screen is idle and a key still plugged in is analyzed again.
    Findings stay in memory while the session runs; events became journal
    lines (`journalctl -u februus`).
  - Key log: `core/keylog.py`, one JSON line per key, written when the
    session ends (`[log] path`, `/var/log/februus/keys.jsonl`, 0640,
    `O_APPEND`, `fsync`, no symbolic link followed). Fields: start time,
    seconds, station, verdict, key removed, files, bytes, signatures, and
    the files with an orange or red finding (at most 20, made safe). No
    other file name is kept (less personal data than the old database). A
    log that cannot be written is reported in the journal and never changes
    the verdict. No rotation yet. `februus stats` reads it (a missing file
    = no key yet).
  - Analyzer service removed (T14b: its design file, the socket and
    instance units, `februus analyzer`, the supervisor, `[analyzer_service]`,
    the `februus-analyzer` account). Reason: the only analyzer today passes
    an open file to clamd, which already runs under its own account; the
    child process, its timeout and its kill (`core/worker.py`,
    `analyzer/service.py`, same protocol) stay. Removed risks: `RuntimeMaxSec`
    vs session timeout, unmount racing with the kill, socket trigger limit.
    Lost: a separate account for analyzers that would parse hostile content
    in Python (P2 macros, YARA): to decide again then. D15 is withdrawn.
  - Removed settings: `[database]` (replaced by `[log] path`),
    `scan.eta_history_sessions`, `[analyzer_service]`, `web.require_scanner`.
    An old `/etc/februus/februus.toml` is invalid: `install.sh` stops with
    the list. The time left is unknown until the first measure (about 1 s).
  - New dev commands: `februus demo <folder>` (screens and a simulated key,
    Enter inserts / removes; `tools/demo.sh` uses it) and `februus web`
    (screens only). Removed commands: `scanner`, `analyzer`, `db`, `session`.
  - `install.sh`: one account `februus`; step 9 removes the old units and
    installs `februus.service`; old data (`/var/lib/februus`) and the
    accounts `februus-web` and `februus-analyzer` are left for the
    administrator to delete. NOT tested on the test PC (no root here):
    section 7 of the hardware checklist is the new list of checks.
  - Review wanted: `core/session.py` (rewritten without SQLite, same
    FAIL-CLOSED rules and tests), `core/worker.py`, `deploy/`.
- 2026-10-04 — Simplification, step 4 (D16, D18): no plugin registry.
  - Gone: `core/registry.py` (import of `februus/<type>/<name>.py` by name,
    `MODULE`), the abstract base classes, the `[modules]` and `[module.*]`
    tables, the options validated by each module, the `Notifier` type and
    `Event` (nothing used them; P3 will add what it needs).
    `core/modules.py` became `core/checks.py` (`Finding`, `ScannedFile`,
    `BlockDevice`, `Reader`, `Analyzer`, `read_chunks`).
  - Inspectors: one function `inspect(device)` per file, run in the fixed
    list `INSPECTORS` of `inspectors/__init__.py` (partitions, bootable,
    filesystem). Not configurable (D16 fixed them). The accepted file
    systems (FAT, exFAT, NTFS; mount types vfat, exfat, ntfs3, fuseblk) are
    constants in the code: they are what the station can read, not a
    tuning; changing them means changing code and tests.
  - Readers: chosen by the command, not by the TOML: `serve` uses
    `kernel_mount`, `scan` and `demo` use `directory`. `run_session` and
    `Scanner` receive the reader. `KernelMountReader(timeout, check_seconds)`;
    `/usr/bin/udisksctl` is a constant (a test passes a fake one). The
    "is the key still there" check during a mount reuses
    `scan.cancel_check_ms`.
  - Analyzers: `[analyzers] enabled = ["clamav"]` chooses among the two that
    exist (`clamav`, `fake`; at least one, else red), each with its own
    table (`[analyzers.clamav]`, `[analyzers.fake]`), required when enabled
    and refused otherwise. All validation is now in `core/config.py`
    (`AnalyzersConfig`); `analyzers.build_analyzers` builds them, and the
    analyzer child process gets the same plain settings. An analyzer that
    cannot be built raises (never fewer analyzers than asked).
  - Settings: removed `[modules]`, `[module.kernel_mount]` (udisksctl,
    filesystems, device_check_ms), `[module.filesystem]`; new
    `scan.mount_timeout_seconds` (was `command_timeout_seconds`);
    `[module.clamav]` and `[module.fake]` became `[analyzers.clamav]` and
    `[analyzers.fake]`. An old `/etc/februus/februus.toml` is invalid
    (`install.sh` stops with the list); copying the new example and setting
    the station name again is the quickest fix.
  - `februus config check` prints the enabled analyzers only. Tests for the
    registry were replaced by tests of `build_analyzers`, of the fixed
    inspector list and of the new config rules.

- 2026-10-05 — One key at a time is wanted (user). The station analyzes one
  key; a second key is ignored (journal line) until the first is removed.
  Stations will be fitted with a USB extension cable, the mini PC hidden under
  a piece of furniture, so the agent plugs a key into the cable's end. Hubs
  stay blocked by USBGuard (user decision, check 5.4). No code change.
- 2026-10-05 — Message when several keys are plugged in (follows the "one key
  at a time" decision). The scanner remembers the ignored keys
  (`Scanner._extra`), `Status.set_extra_keys` shows their number on the
  screens (`SessionStatus.extra_keys`, outside the session so that it
  survives `start` and `close`), and a notice (`templates/_notice.html`,
  very simple English, sent by the live stream too) says "Two USB keys are
  plugged in... Remove the other key. It is not checked." If the first key is
  removed and the second stays, the idle screen says "A USB key is still
  plugged in, but it was not checked. Remove it, then plug it in again.": the
  second key is NEVER analyzed by itself (the agent could not tell which key
  was checked). No TOML setting, no new service, no sound. Previews:
  `/preview/two_keys`, `/preview/key_left`. Tests: scanner, status, web.
- 2026-10-05 — Notice when USBGuard blocks a USB device (hub, keyboard, a
  "key" with another interface...). No usbguard-dbus: udev already shows the
  USB device with `authorized` = 0. `scanner/udev.py` also follows the `usb`
  devices; `BlockedDevices` waits `scanner.settle_seconds` after the plug
  (USBGuard allows a device a moment after it appears) and reports the
  ones still refused (`KeyEvent` "blocked" / "unblocked"). `Status` keeps the
  number (`blocked_devices`, outside the sessions, like the extra keys) and
  `_notice.html` says: not a normal USB key, do not use it if it was given as
  a key, unplug it, tell the IT support. Only devices plugged after the
  start are reported (internal devices blocked at boot would show a notice
  for ever). A device that cannot be read counts as blocked. Does not change
  what is blocked (hubs stay blocked). Preview: `/preview/blocked`.
- 2026-10-05 — Public repository and MIT licence (user). `LICENSE` (MIT,
  "The Februus authors" as holder: to change if wanted), `license` in
  `pyproject.toml` (checked with the CI install), README sections EN/FR.
  Components checked in the Debian copyright files: Februus imports FastAPI,
  Uvicorn, Jinja2 (MIT/BSD) and pyudev (LGPL, used as a library); ClamAV,
  udisks2, USBGuard and Firefox (GPL/MPL) are separate programs that Februus
  installs from Debian and talks to, never links or redistributes: MIT is
  compatible. The only file copied in the repository is the font Cinzel
  Decorative (SIL OFL 1.1, licence text kept next to it). The notes about a
  private repository (GitHub token, `scp`) were removed from the install
  guides. Not decided, to settle before the repository is made public: the
  Cerberus picture (rights not verified, `docs/CREDITS.md`), the author name
  and e-mail in the git history, the mentions of the préfecture and the
  SIDSIC. Install guides: the Debian ISO to use is
  `debian-13.7.0-amd64-netinst.iso`.
- 2026-10-05 — Cerberus picture removed (user), before the repository is made
  public: its rights could not be verified. `static/img/` is gone, the screens
  keep the plain color of the verdict. The font of the name stays (OFL).
- 2026-10-05 — Themes and the State design system (user: the project is made
  for the Préfecture de la Moselle, bloc-marque "Préfet de la Moselle" and
  DSFR wanted). The DSFR terms of use (LICENSE.md and doc/legal/cgu.md of
  GouvernementFR/dsfr) reserve it to State services and forbid confusion with
  an official service; Marianne and the bloc-marque follow. So the public MIT
  repository stays neutral and takes an optional THEME: `/etc/februus/theme`
  (`templates/` replace the templates of the same name, `static/` is served as
  `/theme/`), installed by `install.sh --theme DIR`, root-owned and read-only
  for the service; a fixed path, not a TOML setting (`create_app(...,
  theme_dir=)` for the tests). `deploy/theme-example/` is a neutral example,
  tested. The DSFR theme (header with the bloc-marque, Marianne, DSFR alerts,
  verdict colors = DSFR success / warning / error) is in a separate PRIVATE
  folder, `februus-theme-moselle` (not pushed anywhere yet). Open: validation
  of the bloc-marque by the communication service of the préfecture; the DSFR
  forbids changing its fundamentals (here: text size and kiosk layout only);
  the texts stay in English (D16) although the DSFR expects French.
- 2026-10-05 — D16 changed: the screens are in simple FRENCH (user). Reason:
  the State design system and the "Préfet de la Moselle" bloc-marque do not go
  with English instructions, and the agents of a préfecture read French (the
  use of French is in principle required in the public service: to confirm
  with the communication service). Still one language, no translation system
  (no gettext, no language bar, no `/lang`): the texts stay in the templates
  and in `web/messages.py` (tips, one message per finding code). `<html
  lang="fr">`; plural "fichier vérifié" for 0 and 1, "fichiers vérifiés" from 2.
  The neutral example theme, the private DSFR theme, the posters, the install
  guides and the tests follow. The code, the logs and the documents keep
  English as the reference. To read by the préfecture: the five tips and the
  warnings about viruses.
- 2026-10-05 — The theme of the Préfecture de la Moselle is a PUBLIC repository
  (user choice), `fbmguerin/februus-theme-moselle`, MIT for its own files only.
  It does not contain the DSFR nor Marianne: `fetch-dsfr.sh` downloads the
  official npm package `@gouvfr/dsfr` 1.15.3 at install time and refuses it if
  its SHA-512 differs from the pinned one (the registry's). A `NOTICE` says what
  the MIT licence does not cover (DSFR and Marianne: State, terms of use of the
  SIG; the bloc-marque: the préfecture). The earlier private repository, which
  held the DSFR files, was renamed `februus-theme-moselle-ancien` (private).
  `install.sh --theme` now copies only `templates/` and `static/`. Still to do:
  validation by the communication service of the préfecture.
- 2026-10-05 — Acceptance test with TWO keys (user: 12 keys are not possible).
  `tools/load-test-key.sh /dev/sdX <kit>` erases a test key and loads a kit
  (clean, ntfs, exfat, eicar, eicar-zip, encrypted, nested, two-partitions,
  two-partitions-eicar, big 900 MB, toobig 1.1 GB, iso). Safety: only a whole
  removable USB disk of 64 GB at most, nothing mounted, the device name typed
  again; it saves the `sha256sum` of the files (check 2.10) and erases the first
  16 MiB. Tried on a real key: red, orange, green, ISO red, ntfs/exfat green,
  1.1 GB red `scan.limit_exceeded`. Finding: a key once written with an ISO and
  only reformatted stays red (leftover El Torito record before the first
  partition); the inspector is NOT changed (fail-closed, a security rule), the
  question is in STATUS (known issues). `docs/TEST-PC-B.md` (EN/FR) rewritten
  around the two keys.
- 2026-10-06 — Kiosk at boot (first try of a station without desktop: cage
  failed with "Found 0 GPUs" and the screen stayed on the errors). Cause: at
  boot `/dev/dri/card0` is first the generic driver simpledrm; the real one
  (i915 here) replaces it a few seconds later and cage, started in between,
  lost its device; systemd then stopped restarting it (default limit: 5
  starts in 10 s). Fix, independent of the GPU: `deploy/kiosk/wait-for-gpu.sh`
  (`ExecStartPre`, installed in `/usr/local/lib/februus/`) runs `udevadm
  settle`, then waits at most 30 s for a DRM card whose driver is not a
  generic one (simpledrm and its kin); after 30 s it goes on with the generic
  one (PC or VM without a real driver), and fails only if there is no card at
  all. `StartLimitIntervalSec=0`: the kiosk never gives up. The 30 s are an
  argument in the unit, not a TOML setting: the kiosk is a deploy file that
  does not read the config, and the value is not a business setting.
  Not chosen: `systemd-udev-settle.service` (deprecated, and does not wait for
  the driver itself), a fixed `sleep`, a dependency on a GPU-specific device
  unit.
- 2026-10-06 — cage runs with `-s` (user): Ctrl+Alt+F2 opens a text console.
  Without it an administrator at the station was locked in the kiosk. The
  console asks for a login and password, like SSH; the agents do not have
  one. Documented in `docs/INSTALL.md` (troubleshooting).
- 2026-10-06 — A station never sleeps and its screen never goes blank (first
  try: the console went blank after a few minutes). `install.sh` always (not
  only with `--kiosk`) masks `sleep`, `suspend`, `hibernate` and
  `hybrid-sleep.target`, and writes `/etc/default/grub.d/februus.cfg`
  (`consoleblank=0` added to `GRUB_CMDLINE_LINUX_DEFAULT`) then runs
  `update-grub`: `/etc/default/grub` itself is left as Debian wrote it, so a
  Debian update never conflicts with it. Fixed values (no TOML setting): a
  station that sleeps is never wanted.
