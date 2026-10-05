# Februus

**[Install a station: step-by-step guide](docs/INSTALL.md)** · *[Version française](README.fr.md)*

Open-source USB sheep-dip station: scans USB drives (ClamAV, YARA, VBA, LibreOffice macros) and gives a simple green/orange/red verdict. Built for public offices and schools.

> **Status: P1 prototype, not ready for production.** The analysis
> pipeline and the screens are written and tested. The USB handling
> (scanner service, udisks2 mount, system rules, USBGuard) passed a first
> round of checks on a test PC with real devices
> ([docs/hardware-validation.md](docs/hardware-validation.md)); some checks
> are still to do. The installer and the services exist; the kiosk screen
> was only tried in a window, not at boot. Progress: [docs/STATUS.md](docs/STATUS.md).

## What it does

An agent plugs a USB key into the station. Without any click, the
station:

1. **inspects the key itself**: partitions, boot code, file system. A key that can start a computer is refused before any
   file is read;
2. **mounts it read-only** (`ro,noexec,nosuid,nodev`) and lists its files;
3. **analyzes every file** with ClamAV, one at a time, with a progress
   bar and the time left;
4. **shows a verdict**:

| Color | Meaning | What the agent does |
|---|---|---|
| Green | No threat found | Uses the key |
| Orange | Checked, with warnings (several partitions...) | Uses the key with care |
| Red | Threat found, or the key could not be fully checked | Does not use the key, brings it to IT support |

Nothing is ever written on the key.

If the key is removed before the end, the result is red: a key that was
not fully checked is never trusted.

## Security principles

- **Fail-closed.** Any error, timeout or unknown case gives red. The worst
  bug for a sheep-dip station is a false green.
- **Files are only read as bytes.** Nothing from the key is ever executed,
  opened or rendered, and nothing is ever written on it.
- **Nothing leaves the station.** No cloud service, no file sent anywhere.
- **No Februus code runs as root.** Mounting is done by udisks2 (Debian
  system service) under a polkit rule; the real mount options are checked
  in `/proc/self/mountinfo`.
- **Least privilege.** The scanner, the analyzers and the web UI run
  without privileges; the web UI only reads the status of the station.
- **USBGuard** accepts only plain mass-storage devices (no keyboard hidden
  in a key).

## Architecture

```
USB key ─▶ USBGuard ─▶ ┌───────── februus serve (one service) ─────────┐
                       │ scanner ◀──D-Bus──▶ udisks2 + polkit          │
                       │    │  (mount read-only)                       │
                       │    ├─ analyzer process ─▶ clamd               │
                       │    ▼                                          │
                       │ status (memory) ◀── reads only ── web screens │──▶ kiosk browser
                       └─────────────────────────────┬─────────────────┘
                                                     ▼
                                    key log: one line per key
```

- **`februus serve`**: one service, one process. A thread follows USB
  events (pyudev) and runs one session per key; the main thread serves the
  kiosk screens (FastAPI, Jinja2, live progress by Server-Sent Events), in
  simple French. The screens only read the status of the station,
  kept in memory.
- **Analyzer process**: a child process that reads the file content and
  asks ClamAV; it is killed when a file takes too long or the key is
  removed.
- **Key log**: one JSON line per key (`/var/log/februus/keys.jsonl`),
  read by `februus stats`.
- **The checks** are plain Python files:
  - *inspectors* look at the raw key (`partitions`, `bootable`,
    `filesystem`): one function each, run in a fixed list
    (`februus/inspectors/__init__.py`);
  - *analyzers* check each file (`clamav`; `fake` for development): the
    TOML (`[analyzers] enabled`) chooses which ones run;
  - *readers* give access to the files: `kernel_mount` on a station,
    `directory` for development (chosen by the command, not by the TOML).
- **Verdict rules**: checks return finding codes (`clamav.detected`,
  `device.bootable`...); the configuration maps each code to a color. An
  unknown code is red, the worst color wins.

Details and design decisions (in French): [PLAN.md](PLAN.md), section 4.

## Try it without a USB key

The whole pipeline runs on a folder, with a development configuration
(`directory` reader). Requirements: Debian 13 (or the Codespaces
devcontainer of this repository), Python 3.13 and the Debian packages
`python3-fastapi python3-uvicorn python3-jinja2 python3-pyudev`.

```sh
pip install -e .                                    # once, in a venv
februus config check -c config/februus.dev.toml    # validate the configuration
februus scan -c config/februus.dev.toml <folder>   # analyze a folder
tools/demo.sh green                                 # live demo of the screens
```

`tools/demo.sh` starts the web UI on http://127.0.0.1:8080 and simulates
a key (`green`, `red`, or `long` for the "come back at HH:MM" screen). The
development configuration uses a fake analyzer: no ClamAV needed. With
clamd running, `pytest -m clamav` runs the ClamAV tests (EICAR is
generated at runtime, never stored in the repository).

Other commands: `februus --help`, and the list in [AGENTS.md](AGENTS.md)
("Useful commands").

## Install a station

**Step-by-step guide, copy and paste: [docs/INSTALL.md](docs/INSTALL.md)** ([en français](docs/INSTALL.fr.md)).

On Debian 13, from a copy of the repository:

```
sudo deploy/install.sh --name f3    # first install: name of the station
sudo deploy/install.sh              # packages, accounts, rules, services
sudo deploy/install.sh --usbguard   # also the USBGuard rules: the devices
                                    # plugged in now (keyboard, mouse) are
                                    # the only non-storage devices allowed
```

Stations are named f1, f2, ... f12 (no leading zeros). `--name` sets
the name of the machine (hostname), which is shown on the screens;
without it, the current name is kept.

The script can be run again after each update. It installs the code in
`/opt/februus`, the command `februus`, the configuration
`/etc/februus/februus.toml` (kept if it exists) and one service,
`februus` (screens on http://127.0.0.1:8080). The former three-service
install is NOT checked on the new layout yet; the older one was checked on a
test PC; see [docs/hardware-validation.md](docs/hardware-validation.md).

Not finished yet: the kiosk screen (`--kiosk`: cage + Firefox, tried in a
window, not at boot). Target system: Debian 13 minimal, no desktop, on a small
PC with a screen and a speaker. The system files are in
[`deploy/`](deploy/) (systemd units, udev, udisks2, polkit, USBGuard,
clamd settings).

## Configuration

One TOML file, `/etc/februus/februus.toml`, the same on every station
(local overrides in `/etc/februus/conf.d/*.toml`). Every key is required
and validated at startup: `februus config check`. Annotated example:
[config/februus.example.toml](config/februus.example.toml).

## Development

- Tests: `pytest` (unit tests, also run by GitHub Actions);
  `pytest -m clamav` and `pytest -m hardware` need clamd or a real key.
- Rules for contributors and coding agents: [AGENTS.md](AGENTS.md).

## Documentation

| Document | Content |
|---|---|
| [docs/INSTALL.md](docs/INSTALL.md) | Install a station, step by step ([en français](docs/INSTALL.fr.md)) |
| [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) | Plain explanation of how it works ([en français](docs/HOW-IT-WORKS.fr.md)) |
| [docs/STATUS.md](docs/STATUS.md) | Progress, decisions, open questions |
| [PLAN.md](PLAN.md) | Project plan and architecture (French) |
| [docs/hardware-validation.md](docs/hardware-validation.md) | Checks to pass on the real station |
| [docs/poster/](docs/poster/) | Poster for the users, to print next to the station |
| [docs/demo.md](docs/demo.md) | Demonstration script (French) |

## License

[MIT](LICENSE). Third-party components and their licences (Debian
packages, the font of the screens): [docs/CREDITS.md](docs/CREDITS.md).

## Why "Februus"?

The name **Februus** refers to the Roman god associated with purification, expiation, and the underworld. The month of February (*Februarius*) is thought to derive its name from this figure and the purification rites celebrated during this period.

Like Februus, the Februus project aims to **purify** removable media: it inspects USB drives, detects threats and provides a simple verdict before their use in schools and administrations.

Find out more: [Februus - Wikipedia](https://wikipedia.org/wiki/Februus)
