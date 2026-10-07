# Test plan: second mini PC ("PC B")

*[Version française](TEST-PC-B.fr.md)*

Goal: prove that a station installed **from scratch, with the install guide
only**, works like the real thing (no desktop, kiosk screen, real keys, an
agent who does not know the project). About 4 to 5 hours with a person who
plugs the keys. The install guide ([INSTALL.md](INSTALL.md)) is **part of the
test**: every step that is unclear or fails is a bug of the guide, to note
and to fix.

Results go in the "Result" columns of
[hardware-validation.md](hardware-validation.md), written as
`PC B 2026-10-xx: OK / KO + notes`. Never write a result that was not seen.
The checks keep their numbers (2.3, 7.12...); this plan gives the order.

## 0. What to bring

| Item | Why |
|---|---|
| PC B, screen, speaker, keyboard, mouse, network cable | the station |
| USB stick with `debian-13.7.0-amd64-netinst.iso` (the installer) | install |
| **Two test USB keys** (1 GB or more, 8 to 32 GB is fine), **which will be erased** | the checks (section 1) |
| USB extension cable | real use (the PC will be hidden) |
| 10 ordinary keys of the préfecture (clean, **not erased**: only plugged in) | check 5.3 |
| A phone, a second USB keyboard, the USB hub | USBGuard (5.2, 5.4, 5.5) |
| The printed poster (`docs/poster/affiche-fr.html`) | acceptance with an agent |
| A person who does not know the project | phase 8 |

No second PC is needed: the test keys are prepared on PC B itself.

## 1. The test keys: two are enough (load a "kit" for each test)

Instead of 12 keys, **two** keys are reloaded as often as needed with
`tools/load-test-key.sh` (after the install of the guide, the repository is in
`/usr/local/src/februus`). It erases the key, then writes the files of a kit.
For safety it refuses everything that is not a small removable USB disk with
nothing mounted, and asks to type the device name again. As root (`su -`):

```
cd /usr/local/src/februus
lsblk -o NAME,SIZE,MODEL,TRAN       # find the key: /dev/sdb for example (not a partition!)
tools/load-test-key.sh /dev/sdb eicar
```

Then **unplug the key and plug it in again**: the station analyzes it. Wait
for the end (the result stays on the screen) before loading another kit.
**Key A** serves for the kits one after the other; **key B** stays for the tests
with two keys at once and for the USBGuard tests.

| Kit | Command (`/dev/sdb` = the key) | Expected |
|---|---|---|
| clean FAT32 (26 ordinary files) | `tools/load-test-key.sh /dev/sdb clean` | **green** (2.2) |
| NTFS, exFAT | `... ntfs`, `... exfat` | **green** |
| EICAR | `... eicar` | **red** `clamav.detected` (2.3, 7.3) |
| EICAR in a zip | `... eicar-zip` | **red** `clamav.detected` |
| encrypted zip and PDF | `... encrypted` | **red** `archive.encrypted`, `pdf.encrypted` |
| too nested zip | `... nested` | **red** `scan.limit_exceeded` |
| two clean partitions | `... two-partitions` | **orange** `device.multi_partition` (2.4) |
| two partitions, EICAR on the second | `... two-partitions-eicar` | **red**, path `sdb2/...` |
| 900 MB file | `... big` | long analysis, ETA, removal test (3.1, 3.2) |
| 1.1 GB file | `... toobig` | **green** since the 3 GB limit (about 1 minute); a file above 3 GB is red `file.too_big` at once |
| real bootable ISO | `... iso /root/debian-13.7.0-amd64-netinst.iso` | **red** `device.bootable`, never mounted (2.5) |

For the ISO: `curl -fL -o /root/debian-13.7.0-amd64-netinst.iso
https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-13.7.0-amd64-netinst.iso`
(or the file of the installer stick).

**Check 2.10 (nothing written on the key).** The tool saves the `sha256sum` of
the files in `/root/test-keys/<kit>.sha256`. After the station has analyzed the
key and the result is on screen, compare (read-only):

```
mkdir -p /mnt/k && mount -o ro /dev/sdb1 /mnt/k
(cd /mnt/k && sha256sum --quiet -c /root/test-keys/clean.sha256 && echo ALL-IDENTICAL)
umount /mnt/k
```

Expected: `ALL-IDENTICAL` (any difference is listed instead).

**Good to know.** A key that once held an ISO and was only reformatted stays
**red** (`device.bootable`): the boot record of the ISO remains in the empty
space before the first partition. The tool erases the first 16 MiB for that
reason; a quick format does not.

## 2. The phases

| # | Phase | Do | Checks | Time |
|---|---|---|---|---|
| 1 | Install Debian | [INSTALL.md](INSTALL.md) steps 1-2 (no desktop; note anything unclear) | — | 30 min |
| 2 | Install Februus | steps 3-5, with `--name f<N> --usbguard`, only keyboard and mouse plugged. **Note the minutes of each step** (freshclam wait!) | 6.1-6.3, 7.1, 7.2, 7.11 | 40 min |
| 3 | Keys | the kits of section 1, one by one on key A: see the screen, `februus stats`, `mountinfo` after each; check 2.10 with the saved hashes | 2.1-2.10, 7.3, 7.4, 7.9, 7.10, 5.3 (the 10 ordinary keys) | 60 min |
| 4 | Blocked devices | phone, second keyboard, hub: the notice appears, the key behind the hub is not seen. Two keys at once (3.6, 3.7) | 5.1, 5.2, 5.4, 5.5, 3.6, 3.7 | 20 min |
| 5 | Robustness | key removed during the analysis (kit `big`: 3.1, 3.2), reinsert at once (3.5), `kill -9` (7.7), timeout (7.5), `systemctl stop` (7.8), **power cut during an analysis** (pull the plug, boot again: the service starts, the key still in is analyzed again, no filesystem error), network cable pulled (the station keeps working) | 2.9, 3.x, 7.5-7.8 | 45 min |
| 6 | Kiosk | guide step 6, reboot. Screen at boot, sounds (green, orange, red, alarm) heard by a person, keyboard shortcuts (Ctrl+L, Ctrl+T, F11, Ctrl+Alt+F3) give no way out | 7.12, 8.1-8.7 | 40 min |
| 7 | Theme | guide "Theme of the Préfecture de la Moselle" (**read the warning**), then check every screen with the keys of phase 3 (idle, analysis, green, orange, red, removed, two keys, blocked device) | — | 25 min |
| 8 | Acceptance with an agent | a person who does not know the project, only the poster, no help: the kits `clean` (green), `eicar` (red), then removes the key during the analysis of the kit `big`. Note hesitations and wrong guesses | T15 | 20 min |
| 9 | Wrap-up | `tools/station-report.sh` (as root) after the phases; write the results; commit the corrections of the guide | — | 20 min |

As root (`su -`), run `tools/station-report.sh > /root/report-phase<N>.txt` at the end of
each phase: it is a read-only snapshot (services, signatures age, USBGuard
devices, mounts, last keys, journal). Paste it in a message to get help.

## 3. Go / no-go

**Must pass** (a failure blocks the use of the station):

| Rule | Check |
|---|---|
| Nothing is ever written on a key (hashes identical before/after) | 2.10 |
| Every failure is red (removed key, timeout, limit, encrypted, bootable, unreadable) | 2.3-2.5, 3.x, 7.5, 7.6 |
| EICAR is found, also inside an archive | 2.3, 7.3 |
| Keys are mounted `ro,noexec,nosuid,nodev` and nothing stays mounted | 1.x, 2.8 |
| Hubs and non-key devices are blocked, keyboard and mouse still work | 5.1, 5.2, 5.4 |
| The station starts by itself after a reboot and after a power cut | 7.12, phase 5 |
| An agent without help understands green / red | phase 8 |
| In the kiosk there is no way to open another page or a shell | 8.6 |

**Should pass** (to fix, but not blocking): sounds, theme details, timings of
the guide, wording of the screens.

**Stop and report at once** (do not try to fix by hand): every key gives
`internal.error`; a key is modified; a keyboard or mouse is blocked and the PC
cannot be administered.

## 4. Friction log of the guide

Fill during phases 1-2 and 6-7 (one line per problem, then fix the guide).

| Step of the guide | What was unclear or failed | Fix |
|---|---|---|
|  |  |  |

## 5. Remote help (optional)

With the SSH server chosen in the installer, commands can be run from another
PC (`ssh admin@<address>`, then `su -`), which leaves the kiosk screen alone.
For help, paste the output of `tools/station-report.sh` and the exact message.
