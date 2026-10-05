# How Februus works

*[Version française](HOW-IT-WORKS.fr.md)*

One page, simple words. If something here is not clear, it is a bug in this
page: please say so.

## What it does

An agent plugs a USB key into the station. The station checks the key
**without opening any file** and shows one color:

- **Green**: nothing found. The key can be used.
- **Orange**: something unusual. Ask for help before using the key.
- **Red**: danger, or the station could not check. Do not use the key.

If anything goes wrong (error, timeout, key unplugged, unknown case), the
result is **red**. The station never says "green" by default.

## What happens, step by step

```
 USB key plugged in
        |
        v
 1. The station is told (udev) and checks the device is allowed (USBGuard)
        |
        v
 2. The key is opened READ-ONLY (udisks2): no writing, no running programs
        |
        v
 3. Shape check ("inspectors"), before reading any file:
      - bootable?         key can start a computer      -> red
      - file system?      not FAT32 / exFAT / NTFS      -> red
      - partitions?       more than one                 -> orange
        |
        v
 4. Virus check (ClamAV): every file is read as plain bytes
        |
        v
 5. Verdict: the worst color wins
        |
        v
 6. The screen shows green / orange / red
        |
        v
 Key unplugged -> the screen goes back to "waiting"
```

## The parts

| Part | Job |
|---|---|
| `februus/scanner/` | Waits for USB events and runs the steps above (one service, `februus`, with the screens inside) |
| `februus/inspectors/` | Shape checks (step 3) |
| `februus/analyzers/clamav.py` | Virus check (step 4) |
| `februus/core/verdict.py` | Turns findings into a color (step 5) |
| `februus/web/` | The screens the agent sees (step 6) |
| `config/*.toml` | All settings, including which finding gives which color |
| `deploy/` | Install script and system settings for a station |

## Findings and colors

Each check returns *findings*, each with a stable code such as
`clamav.detected` or `device.bootable`. The file `config/februus.toml` says
which color each code gives. A code that is not in the file gives **red**.
To make a rule stricter or softer, change one word in that file.

## Safety rules, in short

1. Files from the key are never opened or run, only read as bytes.
2. Nothing leaves the station (no cloud, no online scan).
3. Doubt means red.
4. The key is mounted read-only. Nothing is ever written on it.
5. The station has no network use except `freshclam`, which downloads new
   virus signatures. The screens listen on `127.0.0.1` only.
6. One line per key is added to a log file (verdict, number of files, and
   the names of the files that gave a warning), nothing else is kept.
