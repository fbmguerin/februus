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
| USB extension cable | real use (the PC will be hidden) |
| The test keys of section 1 (about 12) and 10 ordinary keys of the préfecture | checks |
| A phone, a second USB keyboard, the USB hub | USBGuard (5.2, 5.4, 5.5) |
| A second PC with this repository (to prepare the keys) | section 1 |
| The printed poster (`docs/poster/affiche-fr.html`) | acceptance with an agent |
| A person who does not know the project | phase 8 |

## 1. Prepare the test keys (on another PC, the day before)

```
git clone https://github.com/fbmguerin/februus.git
cd februus
python3 tools/make-test-files.py ~/test-files           # eicar, archives, pdf
python3 tools/make-test-files.py ~/test-files-big --big 900   # + a 900 MB file
```

(The antivirus of that PC may delete `eicar.com`: turn it off for the folder.)

| Key | How to prepare it | Expected |
|---|---|---|
| K1 clean FAT32 | 20 or more ordinary files, with folders, plus `texte.txt` | **green** (2.2) |
| K2 EICAR | FAT32 with `eicar.com` | **red** `clamav.detected` (2.3, 7.3) |
| K3 EICAR in a zip | `eicar-dans-un-zip.zip` | **red** `clamav.detected` |
| K4 encrypted | `archive-chiffree.zip` and `pdf-chiffre.pdf` | **red** `archive.encrypted`, `pdf.encrypted` |
| K5 too nested | `zip-trop-imbrique.zip` | **red** `scan.limit_exceeded` |
| K6 two partitions, clean | two small FAT32 partitions with a file each | **orange** `device.multi_partition` (2.4) |
| K7 two partitions, EICAR on the second | as K6 + `eicar.com` on partition 2 | **red**, path `sdb2/...` |
| K8 bootable | `sudo dd if=debian-13.7.0-amd64-netinst.iso of=/dev/<key> bs=4M conv=fsync` (check the name of the key!) | **red** `device.bootable`, never mounted (2.5) |
| K9 NTFS, K10 exFAT | one clean file each | **green** |
| K11 big file | FAT32 + `big.bin` (900 MB) | long analysis, ETA, removal test (3.2) |
| K12 too big | FAT32 + a 1.1 GB file (`--big 1100`) | **red** `scan.limit_exceeded` |

Before copying, note the `sha256sum` of the files of K1, K2 and K6 (check 2.10:
nothing may change on a key after the station).

## 2. The phases

| # | Phase | Do | Checks | Time |
|---|---|---|---|---|
| 1 | Install Debian | [INSTALL.md](INSTALL.md) steps 1-2 (no desktop; note anything unclear) | — | 30 min |
| 2 | Install Februus | steps 3-5, with `--name f<N> --usbguard`, only keyboard and mouse plugged. **Note the minutes of each step** (freshclam wait!) | 6.1-6.3, 7.1, 7.2, 7.11 | 40 min |
| 3 | Keys | K1 to K12 one by one: see the screen, the `februus stats`, `mountinfo` after each | 2.1-2.10, 7.3, 7.4, 7.9, 7.10, 5.3 (the 10 ordinary keys) | 60 min |
| 4 | Blocked devices | phone, second keyboard, hub: the notice appears, the key behind the hub is not seen. Two keys at once (3.6, 3.7) | 5.1, 5.2, 5.4, 5.5, 3.6, 3.7 | 20 min |
| 5 | Robustness | key removed during the analysis (K11: 3.1, 3.2), reinsert at once (3.5), `kill -9` (7.7), timeout (7.5), `systemctl stop` (7.8), **power cut during an analysis** (pull the plug, boot again: the service starts, the key still in is analyzed again, no filesystem error), network cable pulled (the station keeps working) | 2.9, 3.x, 7.5-7.8 | 45 min |
| 6 | Kiosk | guide step 6, reboot. Screen at boot, sounds (green, orange, red, alarm) heard by a person, keyboard shortcuts (Ctrl+L, Ctrl+T, F11, Ctrl+Alt+F3) give no way out | 7.12, 8.1-8.7 | 40 min |
| 7 | Theme | guide "Theme of the Préfecture de la Moselle" (**read the warning**), then check every screen with the keys of phase 3 (idle, analysis, green, orange, red, removed, two keys, blocked device) | — | 25 min |
| 8 | Acceptance with an agent | a person who does not know the project, only the poster, no help: K1 (green), K2 (red), then removes K11 during the analysis. Note hesitations and wrong guesses | T15 | 20 min |
| 9 | Wrap-up | `sudo tools/station-report.sh` after the phases; write the results; commit the corrections of the guide | — | 20 min |

Run `sudo tools/station-report.sh > /root/report-phase<N>.txt` at the end of
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
