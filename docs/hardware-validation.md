# Hardware validation (mini-PC) — T10 / T12

The code of T10/T12 is only tested with simulated USB events and a fake
`udisksctl`. These checks are REQUIRED on the mini-PC (Debian 13, real
keys) before the station is used. Each line: what to do, expected result.
Write the result (OK / KO + notes) in the last column and keep this file
in the repository.

**Screen texts:** until 2026-10-05 the screens were in English; they are now in
French (D16 changed). The results written before that date quote the English
texts (for example "Insert your USB key" = "Insérez votre clé USB", "No threat
found" = "Aucune menace détectée", "Do not use this key" = "N'utilisez pas cette
clé"). The texts: `februus/web/templates/` and `februus/web/messages.py`.

Prepare: a FAT32 key, an exFAT key, an NTFS key, a key with two
partitions, a bootable key (ISO written with `dd`), a composite device (key + keyboard, or a phone),
EICAR generated on a key (`tests/samples.py`).

## 1. Privileges (polkit, udisks2, udev)

| # | Check | Expected | Result |
|---|---|---|---|
| 1.1 | As `februus`: `udisksctl mount -b /dev/sdb1 -o ro,noexec,nosuid,nodev --no-user-interaction` | Mounted, no password | OK (as `februus`, no password) |
| 1.2 | Then `grep sdb1 /proc/self/mountinfo` | `ro,nosuid,nodev,noexec` present | OK: `ro,nosuid,nodev,noexec,relatime` |
| 1.3 | As `februus`: `udisksctl mount -b /dev/sdb1 -o exec` (also `suid`, `dev`) | Refused (option not allowed) | OK: `OptionNotPermitted` for `exec`, `suid` and `dev` |
| 1.4 | As `februus`: `udisksctl mount -b /dev/sdb1` (no option) | Mounted with `ro,noexec,nosuid,nodev` (defaults) | OK: `ro,nosuid,nodev,noexec` |
| 1.5 | As another user (`februus-web`, a normal user; this account no longer exists since step 3): mount the key | Refused | `februus-web`: OK, refused (`NotAuthorizedCanObtain`). Desktop account `francois`: mounted (ro,noexec,nosuid,nodev) — expected on a dev PC, polkit allows the active desktop user; to redo on a station without desktop |
| 1.6 | As `februus`: mount an internal disk partition | Refused (filesystem-mount-system) | OK: `/dev/nvme0n1p1` refused (`NotAuthorizedCanObtain`) |
| 1.7 | `ls -l /dev/sdb` with a key in | `brw-r----- root februus` | OK: `brw-r----- root februus` |
| 1.8 | As `februus`: `dd if=/dev/zero of=/dev/sdb count=1` | Permission denied | OK: permission denied (reading works) |
| 1.9 | `id februus-web` (account removed in step 3) | not in group `februus` | OK: groups `februus-web` only |

## 2. Mounting and analysis (`pytest -m hardware`, `februus serve`)

| # | Check | Expected | Result |
|---|---|---|---|
| 2.1 | `FEBRUUS_PARTITION=/dev/sdb1 pytest -m hardware` (FAT, exFAT, NTFS) | Passed | OK: FAT32, exFAT, NTFS (`ntfs3`) with `FEBRUUS_PARTITION`; `FEBRUUS_FAT_DIR` on FAT32 |
| 2.2 | Clean FAT32 / exFAT / NTFS key | Green | OK: FAT32, exFAT, NTFS green |
| 2.3 | Key with EICAR | Red, key not modified (compare `sha256sum` of the files before/after) | OK: red `clamav.detected`, same `sha256sum` of the files before/after (FAT32, exFAT, NTFS) |
| 2.4 | Key with two partitions, EICAR on the second | Red, path `sdb2/...` | OK: red, `sda2/eicar.com` (+ `device.multi_partition`). Two clean partitions: orange 2026-10-05, new key in two FAT32 partitions: clean = orange `device.multi_partition` (screen "Key checked, with warnings"); EICAR on the second = red `clamav.detected` path `sdb2/test/eicar.com` + the orange code; nothing mounted after |
| 2.5 | Bootable key (ISO with `dd`) | Red "device.bootable", never mounted (no line in mountinfo during the session) | KO then OK after fix. Debian live key = ISO inside one partition: red and never mounted, but only `filesystem.unsupported`. Fix: El Torito is also searched in each partition -> `device.bootable`. ISO written on the whole key with `dd`: not tested 2026-10-05: an 8 MB image with ISO 9660 + El Torito descriptors (the one of `tests/disk_images.py`, no real ISO and no `xorriso` on the PC) written with `dd` on the WHOLE key: red `device.bootable` + `filesystem.unsupported`, "device refused by the inspectors", never mounted. A real Debian ISO: not tested |
| 2.6 | (write-protect switch) | Removed on 2026-10-04 (D16): the `write_protect` inspector no longer exists | — |
| 2.7 | Key already mounted before Februus (mount it by hand first) | Red ("already mounted") | OK: red, `already mounted before Februus`; the foreign mount is left alone |
| 2.8 | After each session: `grep /dev/sd /proc/self/mountinfo` | Nothing left mounted | OK after every session |
| 2.9 | Stop the scanner (`kill -9`) during an analysis, restart it | The session becomes red, nothing left mounted after removal | OK: interrupted session red (`the station stopped during this session`); key still in at restart: red (`already mounted`); nothing mounted after removal |
| 2.10 | After a green, an orange and a red session: `find /media/... -newer` or compare the file list and `sha256sum` of the key before/after (remount by hand, read-only) | Nothing added, nothing changed (no `.februus.json`) | OK for green and red (2026-10-05, key sda, FAT32, user files + folder `februus-test/` written by hand): `sha256sum` of every file identical before / after, for 5 red sessions (EICAR, EICAR in a zip, encrypted zip, encrypted PDF, zip nested 30 times) and the green ones; nothing left mounted. Orange: not done (the only orange rule is two partitions: needs a repartitioned key, destructive, to ask) 2026-10-05 also with the two-partition key: `sha256sum` and dates identical before / after, orange session and red session. Orange now covered |

## 3. Key removal (races)

| # | Check | Expected | Result |
|---|---|---|---|
| 3.1 | Remove the key during the inventory | Red "removed", alarm, idle after 30 s | KO then OK after fix: red but `internal.error` (read error seen before the removal event) and state `result`. Fix: now `device.removed`, state `aborted`, idle after 30 s. Alarm (sound) not checked |
| 3.2 | Remove during the analysis of a big file (> 1 GB) | Red within ~1 s, worker stopped (`ps`), nothing left mounted | OK: red in 0.02 s, worker stopped, nothing mounted (900 MB file). Found here: clamd answers `OK` for a file read only in part -> fixed, see below |
| 3.3 | (removal during the witness writing) | Removed on 2026-10-04 (D16): no witness file any more, nothing is written on the key | — |
| 3.4 | Remove after the result | Idle screen | OK: session closed, idle screen (web UI checked with curl) |
| 3.5 | Reinsert the same key at once | A new session (never the old result) | OK: a new session each time |
| 3.6 | Insert a second key during a session | Ignored until the first one is removed | OK (2026-10-05): with two keys plugged in, the first is analyzed and the second is ignored (journal: "key /dev/sdb ignored: /dev/sda is still plugged in"), at the start of the service and at boot. Insertion of a second key in the middle of a session by hand: not done |
| 3.7 | Two keys plugged in: look at the screen. Then remove the first one (the second stays) | During the analysis or the result: notice "Two USB keys are plugged in... Remove the other key. It is not checked.". After the first is removed: idle screen + "A USB key is still plugged in, but it was not checked. Remove it, then plug it in again.". The second key is never analyzed by itself | OK (2026-10-05, sda + sdb, first removed by software `delete`, put back with a SCSI rescan): the three screens as expected; the second key was not analyzed; notice gone when the extra key is removed |

## 4. Witness file (removed)

Removed on 2026-10-04 (D16): the station no longer writes anything on a
key. The former checks 4.1 to 4.3 are deleted; check 2.10 replaces them.

## 5. USBGuard

| # | Check | Expected | Result |
|---|---|---|---|
| 5.1 | Station keyboard and mouse after install | Allowed | OK: keyboard and mouse allowed (rules of `usbguard generate-policy`, tied to their USB port) |
| 5.2 | Composite device (key + HID, phone) | Blocked (`usbguard list-devices`) | OK with an Android phone (POCO X3 NFC), blocked in every mode: charge + ADB (`ff:42:01`), MTP, PTP (`06:01:01`), USB tethering (`ef:04:01 0a:00:00`, no network interface appeared), MIDI (`01:01:00 01:03:00`). Also blocked: webcam (video + audio), see the list below. Key + keyboard device: not tested |
| 5.3 | 10 ordinary keys of the préfecture | Allowed (list the refused ones: if many, the rule must be reviewed) | OK for 3 keys (2 SanDisk 3.2Gen1, 1 Kingston DataTraveler 3.0), allowed by the generic rule. Not yet 10 keys of the préfecture |
| 5.4 | Key through an external hub | Blocked | OK for the hubs themselves (2 models, USB 2 and USB 3 parts both blocked); nothing behind a blocked hub is seen by the kernel. Key behind the hub: to confirm by hand 2026-10-05, one-service version, same Genesys hub (05e3:0610 / 05e3:0626): kernel says "Device is not authorized for usage", USBGuard rules block both parts (`block ... with-interface 09:00:00`), no key behind it appears (`lsblk`), the screen stays on "Insert your USB key" (known issue: nothing says why). Hub kept blocked on purpose (rule "a key must be plugged in directly") |
| 5.5 | Plug a hub (or any device USBGuard blocks) while the station runs: look at the screen; unplug it | Notice "A USB device was blocked. It is not a normal USB key... Unplug it now and tell your IT support." about 2 s after the plug (settle time); it goes away when the device is unplugged. Devices already blocked when the service starts are not reported | Notice seen with the Genesys hub (2026-10-05, `authorized=0` on both parts, key behind it not seen). Unplugged: notice gone, journal "unblocked" for both parts. Not seen: a keyboard / phone blocked (only the hub was tried) |

## 6. Installation

| # | Check | Expected | Result |
|---|---|---|---|
| 6.1 | `sudo deploy/install.sh --name f9` | `hostname` and the screens show `f9`; `getent hosts f9` gives 127.0.1.1; `sudo` does not warn "unable to resolve host" | |
| 6.2 | `sudo deploy/install.sh --name F9` (also `f_9`) | Refused before any change (exit code 2) | |
| 6.3 | `sudo deploy/install.sh` again (no option) | Name kept, "station name: f9" printed | |

## 7. One service (step 3, 2026-10-04)

Done on 2026-10-05 except 7.12 (reboot), see Result. It replaces the former
section 7 (analyzers under their own account), removed with the service
`februus-analyzer` (D17). Before: edit `/etc/februus/februus.toml` (see
`docs/decisions.md`, step 3), then `sudo deploy/install.sh`.

| # | Check | Expected | Result |
|---|---|---|---|
| 7.1 | `systemctl list-units 'februus*'` after the install | Only `februus.service` (the old scanner, web and analyzer units are gone) and it is active | OK: only `februus.service`, active; the old scanner and web units were removed by `install.sh` |
| 7.2 | `ss -ltnp` | Only `127.0.0.1:8080` listens for Februus | OK: only `127.0.0.1:8080` (python3 of the service) |
| 7.3 | Key with EICAR | Red `clamav.detected`: clamd accepts the descriptors given by the analyzer child process (risk of decision D14). If every file is `internal.error`: STOP, tell the user (fallback INSTREAM to discuss) | OK: EICAR alone and EICAR inside a zip give red `clamav.detected` (path `februus-test/eicar.com`, `februus-test/doc.zip`). No `internal.error`: clamd accepts the descriptors of the analyzer child, risk of D14 not seen. Also red with the right code: `archive.encrypted`, `pdf.encrypted`, `scan.limit_exceeded` |
| 7.4 | Clean key | Green; during the analysis `pgrep -P $(systemctl show -p MainPID --value februus)` shows the analyzer child, and nothing after the session | OK: green; the analyzer child (`multiprocessing.spawn`) seen during the analysis, gone after. One Python helper (`resource_tracker`) stays as long as the service lives: normal, not an analyzer |
| 7.5 | A file that hangs the analysis (`scan.file_timeout_seconds` set very low and a big file) | Red `scan.timeout`; the child process is gone (`pgrep -P`) | OK: 700 MB random file and `file_timeout_seconds = 1` (put back to 120 after): red `scan.timeout` on `februus-test/big.bin`, no analyzer child left, nothing mounted |
| 7.6 | Key removed during the analysis | Red "removed"; no child process left | OK (key pulled by the user during an analysis, 10 files): red `device.removed`, `removed: true` in the key log, nothing mounted, no child left. The journal gets a traceback (`udisksctl unmount failed: Error looking up object`) from the unmount of the vanished key: noisy, verdict right |
| 7.7 | `kill -9` the main process during an analysis | systemd restarts it; no child process left; a key mounted at the time of the kill gives RED ("already mounted"), a key not yet mounted is analyzed again | OK, with a different outcome than expected: systemd restarted the service (NRestarts=1), no child left. The key was mounted when killed, so the new session is RED (`internal.error`, "already mounted"), like 2.9: fail-closed, the key must be unplugged. Mount removed by hand afterwards; then green again. Expected text corrected |
| 7.8 | `systemctl stop februus` with a green result on screen | The browser shows an error, never the old green | OK: with the service stopped the screen does not answer (connection refused), the old green is not shown |
| 7.9 | After 7.3 to 7.6: `sudo cat /var/log/februus/keys.jsonl`, `ls -l /var/log/februus` | One line per key; no file name except the files with a warning; folder `februus:februus` 0750, file 0640 | OK: `/var/log/februus` is `februus:februus` 0750, `keys.jsonl` 0640; one line per key; the line of a problem has only the code (no file name for a clean key) |
| 7.10 | `sudo -u februus februus stats` | Counts match the keys of this section | OK: `sudo -u februus februus stats` showed 4 sessions, 4 green, 20 files = the 4 lines of the log at that time |
| 7.11 | `systemd-analyze security februus.service` | Exposure noted here | Exposure 2.9 OK. No `ProtectSystem`, `PrivateTmp`, `PrivateNetwork` etc. (wanted: clamd under AppArmor, loopback for the screens). `UMask` not set |
| 7.12 | Reboot the PC | The service starts by itself, the screens answer on `127.0.0.1:8080` (T14) | OK (2026-10-05): after the reboot `februus.service` started by itself 8 s after boot (`enabled`, `NRestarts=0`), screens answer on `127.0.0.1:8080`, clamd and USBGuard active. Both keys were plugged in at boot: the first was analyzed (green), the second ignored ("still plugged in"). The kiosk (no desktop session) is still NOT tested: this PC has a desktop session (`francois`, tty2) |

## 8. Kiosk (cage + Firefox, `deploy/kiosk`)

Test A of 2026-10-05: `cage` (nested in a window of the LXQt desktop of the
test PC, `WLR_BACKENDS=x11`) + `firefox-esr --kiosk` with `policies.json`
installed only for the test (removed after). Not the real kiosk (no boot,
no console 1, no desktop-free PC).

| # | Check | Expected | Result |
|---|---|---|---|
| 8.1 | `cage -- firefox-esr --kiosk http://127.0.0.1:8080` | The station screen alone: no address bar, no tabs | OK (screenshot): only the Februus screen, with the picture |
| 8.2 | Open `https://example.com` with the policies | Blocked page | OK: "Blocked Page - Your organization has blocked access to this page or website" |
| 8.3 | Open `about:config` with the policies | Blocked | OK: same blocked page |
| 8.4 | Sounds (green / orange / red / alarm) in the kiosk | Played without a click | Not done (needs a key result and a listening person) |
| 8.5 | PC without desktop: boot to the kiosk (`februus-kiosk.service`, console 1, user `februus-kiosk`) | Screen at boot, no way out of the browser | Not done: needs a PC without desktop session (test B) |
| 8.6 | Keyboard shortcuts (Ctrl+L, Ctrl+T, F11, Ctrl+Alt+F3...) | No way to open another page or a shell | Not done (needs a human at the keyboard, in the real kiosk) |
| 8.7 | polkit: no desktop session means no user allowed to mount keys | Only `februus` mounts keys | Not done (needs test B) |

## 9. Second mini PC (test B): order of the work

Goal: the real station, with no desktop session. Everything is done by
following [INSTALL.md](INSTALL.md) as a beginner would, and the guide is
corrected where it fails. Write the results in the tables above (add the
date and "PC B" in the Result column).

Before (on another PC): the ISO `debian-13.7.0-amd64-netinst.iso` on a USB
stick (the installer), and the test keys:

| Key | Content | Used for |
|---|---|---|
| clean | a few ordinary files, FAT32 | green (2.2), 7.4 |
| EICAR | `eicar.com` (`INSTALL.md`, step 5) | red (2.3, 7.3) |
| two partitions | two small FAT32 partitions | orange (2.4) |
| ISO | the Debian netinst ISO written with `dd` on the whole key | red `device.bootable`, a real ISO (2.5) |
| encrypted | an encrypted zip and PDF (`tests/samples.py`) | 7.x |

Order:

1. Install Debian and Februus with the guide (note every step that is unclear
   or fails: the guide is part of the test). Steps 1 to 5 of the guide.
2. Checks without the screen: 2.x (keys), 3.x (removal, second key), 5.x
   (USBGuard, hub, blocked device), 6.x (installation, `--name`), 7.x.
3. Kiosk (guide step 6) and reboot: 7.12, then the whole section 8 (screen at
   boot, sounds, shortcuts such as Ctrl+L / Ctrl+T / F11 / Ctrl+Alt+F3, the
   user cannot leave the browser), and 8.7 (only `februus` mounts keys).
4. Commit the results and the corrections of the guide.

Remote work (optional): with the SSH server of the installation, commands can
be run from another PC (`ssh admin@<address>`, then `su -`), which keeps the
kiosk screen untouched.

## Results of 2026-10-02 (test PC)

Test PC (not the final mini-PC): Debian 13 with LXQt, ClamAV 1.4.3,
udisks2 2.10.1, polkitd 126, branch `claude/elegant-mendel-km4wd2`.
Scanner run by hand as `februus` (`sudo -u februus februus scanner`), no
systemd unit yet (T14). One key only (SanDisk 32 GB), formatted for each
test: Debian live image, FAT32, exFAT, NTFS, two FAT32 partitions.

SIMULATED, to redo by hand on the mini-PC:

- Key removal (2.9, section 3): the USB device was unbound from the kernel
  (`/sys/bus/usb/drivers/usb/unbind`), nobody pulled the key out. The
  kernel and udev see the same events, but a real removal was not done.
- USBGuard was stopped and disabled during sections 1 to 4 (the Debian
  package enables it with generated rules, new keys were blocked).

Section 5 (USBGuard), done after sections 1 to 4: `/etc/usbguard/rules.conf`
= the generated rules of the controllers, keyboard and mouse, then
`deploy/usbguard/rules.conf`; `ImplicitPolicyTarget=block` is the Debian
default. No other machine on the network, so SSH could not be the rescue
access: a temporary root timer re-authorized the keyboard and mouse if
they were blocked (tested by blocking the mouse, removed afterwards).
A charge-only cable shows nothing at all on the PC (no USB event).

Problems found and fixed:

- clamd 1.4.3 does not know `EnableVersionCommand` and did not start:
  line removed from `deploy/clamav/clamd-februus.conf`.
- FAIL-OPEN (3.2): clamd answers `OK` for a file it could read only in
  part (key pulled out, or damaged sectors: reproduced with a
  device-mapper `error` target, without any removal). A damaged key could
  be green. Fix: the worker reads every file itself before the analyzers;
  a read error gives `internal.error` (red).
- 2.5 and 3.1: see the tables.

Left open (see `docs/STATUS.md`):

- 3.3: key pulled out exactly while udisks2 unmounts it: `udisksctl
  unmount` waits about 20 s, the screen stays on the analysis, then red.
- Many small files: about 17 ms per file on FAT32 (6000 files: 2 min 40),
  and the ETA shows 0 because it is computed from bytes.
- A file bigger than clamd `MaxFileSize` (1000M) is red at once.

### USBGuard: devices plugged in on 2026-10-02 (audit log)

| Device | USB id | Interfaces | Decision |
|---|---|---|---|
| Other mouse | 18f8:0f97 | `03:01:02 03:00:01` | block |
| Webcam AVerMedia Live Streamer CAM 313 | 07ca:313a | video `0e` + audio `01` | block |
| Keyboards (3, one is a numeric pad) | 1a2c:4324, 1a2c:2c27, 1ea7:2001 | `03:01:01 03:00:00` | block |
| Barcode reader (declares a keyboard) | 0d6c:0200 | `03:01:01` | block |
| Hub (Genesys, USB 2 + USB 3 parts) | 05e3:0610, 05e3:0626 | `09` | block |
| Hub / dock (ASMedia ASM107x) | 174c:2074, 174c:3074 | `09` | block |
| Smart card reader (CCID, payment terminal) | 0f14:0038 | `0b:00:00` | block |
| Fingerprint device (Sagem / Morpho) | 079b:0087 | `ff:ff:ff` x4 | block |
| Fingerprint scanner Suprema RealScan-G10 | 16d1:1026 | `ff:00:00` | block |
| Keys: SanDisk 3.2Gen1 (2), Kingston DataTraveler 3.0 | 0781:5581, 0951:1666 | `08:06:50` | allow |
| Laptop hard disk on a USB-IDE/SATA adapter (JMicron bridge) | 152d:2338 | `08:06:50` | allow |
| Storage enclosure "Generic External" (Initio), no medium seen | 13fd:0840 | `08:06:50` | allow |

Not seen at all by the PC (no USB event): the CD drive, and the disk
behind the blocked dock.

To decide: an external hard disk on a USB adapter is pure mass storage,
so USBGuard allows it like a key. USBGuard cannot tell them apart; the
kernel can ("removable" flag: keys are removable disks, the hard disk
was not).
