# Install a Februus station (step by step, copy and paste)

*[Version française](INSTALL.fr.md)*

This guide starts from an empty mini PC. It only assumes that you know how to
install Debian 13 ("Trixie"). Every code block is to be **copied and pasted
as it is** into the terminal. Words between `<` and `>` must be replaced.

Time: about 1 hour, part of it waiting for downloads.

## What you need

- A mini PC with screen, keyboard, mouse, speaker and a network cable
  (Internet is needed for the installation, then to update the antivirus
  signatures).
- A screen connected with **HDMI or DisplayPort**. Avoid VGA: on the first
  tries it gave a cut picture and a screen going to sleep.
- A USB stick with the Debian 13 installer.
- The name of the station: `f1`, `f2`, ... `f12` (no leading zero).
- A test USB key (optional, to check at the end).

## Step 1: install Debian 13

Download the installer **`debian-13.7.0-amd64-netinst.iso`** (64-bit, small, the
rest is downloaded during the installation) from
<https://www.debian.org/distrib/netinst> (a newer `13.x` is fine), and write
it on a USB stick (on Linux, as root: `dd if=debian-13.7.0-amd64-netinst.iso
of=/dev/<the-stick> bs=4M status=progress conv=fsync`; on Windows: Rufus, DD
mode). **Check the name of the stick before `dd`: it erases it.**

In the Debian installer:

1. Language and keyboard: yours.
2. Machine name: type the name of the station (for example `f3`).
3. Password of `root`: choose one and write it down. Also create a normal
   user (for example `admin`).
4. Partitioning: "Guided, use the entire disk" is enough to try. For a real
   station: separate partitions `/`, `/var`, `/tmp`, `/home` and swap,
   **without LVM and without encryption** (the station must start by itself).
5. Software selection: **untick everything** (above all "desktop
   environment" and "GNOME"). Tick only:
   - **SSH server** (to administer it from another PC);
   - **standard system utilities**.
6. Finish and reboot on the disk.

No desktop, on purpose: the station shows one screen and nothing else.

## Step 2: log in and become administrator

Log in (screen + keyboard, or over SSH from another PC), then:

```
su -
```

Type the password of `root`. The prompt must show `root@...#`. **All the
following commands are typed as `root`.**

## Step 3: get Februus

```
apt-get update
apt-get install -y git
git clone https://github.com/fbmguerin/februus.git /usr/local/src/februus
cd /usr/local/src/februus
```

Choose the version to install:

```
git checkout main
```

## Step 4: first installation

**Unplug everything USB except the keyboard and the mouse** (no key, no hub).
The installation allows those two devices, and only them, besides storage
keys.

Replace `f3` by the name of the station, then run:

```
./deploy/install.sh --name f3 --usbguard
```

This installs the Debian packages, the ClamAV antivirus, the Februus service
and the USB security rules. It takes a few minutes. At the end you must see a
line `Active: active (running)`.

### If the script says "no ClamAV signatures yet"

This is normal at the first installation: the antivirus is still downloading
its database (a few minutes). Wait, check that files exist, then run the same
command again:

```
ls /var/lib/clamav
./deploy/install.sh --name f3 --usbguard
```

The list must contain `.cvd` or `.cld` files (for example `daily.cld`). If it
stays empty after 15 minutes, look at `journalctl -u clamav-freshclam` (often:
no Internet access).

## Step 5: check that it works (without the station screen)

```
systemctl status februus --no-pager
curl -s http://127.0.0.1:8080 | grep "<h1>"
```

Expected: `active (running)`, then `<h1>Insérez votre clé USB</h1>` (the screens
are in French: "Insert your USB key").

Then plug in a normal USB key. After a few seconds:

```
curl -s http://127.0.0.1:8080 | grep "<h1>"
februus stats
```

For a key without any problem you see `Aucune menace détectée` ("No threat found") and `green: 1`.

### Try with a fake virus (optional)

EICAR is a harmless test file that every antivirus knows. On **another PC**,
create it on a **test** key (never on an important key):

```
printf '%s%s' 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR' '-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' > /media/<your-key>/eicar.com
```

(The antivirus of that other PC may complain: this is normal.) Plug the key
into the station: it must show **red** (`Un virus ou un fichier
malveillant a été trouvé`, "A virus or malicious file was found").

## Step 6: install the station screen (kiosk)

The screen shows green / orange / red in full screen, with sounds. It is
installed with Firefox and `cage` (a tiny window manager).

```
./deploy/install.sh --kiosk
reboot
```

After the reboot, the screen "Insérez votre clé USB" ("Insert your USB key")
must appear by itself. Before it, for up to about 30 seconds, you may see
lines of text or a black screen: the kiosk waits for the graphics driver.

If after one minute the screen still shows lines of text (for example
`Found 0 GPUs` or `Unable to create the wlroots backend`), a login prompt, or
stays black, the kiosk did not start: see [Get back control of a station in
kiosk mode](#get-back-control-of-a-station-in-kiosk-mode) and look at
`journalctl -u februus-kiosk -b`. The station itself (the analysis of keys)
keeps working.

To be even cleaner, then do the checks of sections 7 and 8 of
`docs/hardware-validation.md` (write the results in the "Result" column).

## Optional: a look of your own (theme)

The screens can take the look of a place (logo, colors, fonts) with a *theme*
folder, without changing the code: `./deploy/install.sh --theme
/path/to/the/theme`. See `deploy/theme-example/`. A theme that uses an official
mark must stay out of this repository.

### Theme of the Préfecture de la Moselle (State design system)

> **WARNING: official identity of the State. Read before installing.**
>
> This theme shows the **bloc-marque "Préfet de la Moselle"**, the **Marianne**
> font and the **State design system (DSFR)**. They belong to the State. Their
> terms of use (<https://github.com/GouvernementFR/dsfr>, file
> `doc/legal/cgu.md`) **reserve them to the services of the State** and forbid
> any use "likely to create confusion with an official public service".
>
> - Install it **only** on a station used by the Préfecture de la Moselle (or
>   another State service that is entitled to it), with the agreement of the
>   préfecture (the maintainer of this project states that it was obtained,
>   on 2026-10-05).
> - Do **not** install it for a school, a company, a private person or a test
>   outside the préfecture, and do **not** copy the mark elsewhere. The MIT
>   licence of this project does **not** give any right on it.
> - **Risks.** Using the State identity outside its framework can expose the
>   person who does it to criminal penalties: article 433-13 of the French
>   Penal Code (activity "in conditions likely to create confusion with the
>   exercise of a public function": up to one year of imprisonment and a
>   15,000 euro fine; check the current text), and to the actions that the
>   State reserves the right to take against misleading uses (terms of use
>   of the DSFR, `LICENSE.md` of the DSFR). This is a reminder, not legal
>   advice: ask the legal department of the préfecture if in doubt.

As `root`, on the station where Februus is already installed (steps 1 to 5):

```
apt-get install -y curl
git clone https://github.com/fbmguerin/februus-theme-moselle.git /usr/local/src/februus-theme-moselle
cd /usr/local/src/februus-theme-moselle
./fetch-dsfr.sh
cd /usr/local/src/februus
./deploy/install.sh --theme /usr/local/src/februus-theme-moselle
```

`fetch-dsfr.sh` downloads the State design system from the official npm package
(checked with a fixed SHA-512 fingerprint: a modified file is refused). Without
it, the screens appear without the style. Then the screen shows the bloc-marque
"Préfet de la Moselle" and the Marianne font. If you use the kiosk (step 6),
reboot.

Update the theme later:

```
cd /usr/local/src/februus-theme-moselle
git pull
./fetch-dsfr.sh
cd /usr/local/src/februus
./deploy/install.sh --theme /usr/local/src/februus-theme-moselle
```

Go back to the plain screens (for example before lending the PC, or for a test
outside the préfecture):

```
rm -r /etc/februus/theme
systemctl restart februus
```

## Use by an agent

1. Plug in **one** key (the mini PC is hidden, use the USB extension cable).
2. Wait for the screen: green (nothing found), orange (unusual, ask for help)
   or red (do not use the key).
3. Remove the key when the screen says so.

One key at a time: if a second key is plugged in, a message asks to remove it.
USB hubs are blocked on purpose: a key is plugged in directly.

## Update later

```
cd /usr/local/src/februus
git pull
./deploy/install.sh
```

The script can be run again safely. It keeps the configuration
(`/etc/februus/februus.toml`) and the key log. If a new version needs a new
setting, it stops **without breaking anything** and tells what to fix (compare
with `config/februus.example.toml`).

**Station installed before 2026-10-07:** the new version needs three
settings. Add them, then run the script again:

```
F=/etc/februus/februus.toml
sed -i '/^stream_seconds = /a watchdog_seconds = 10' $F
sed -i '/^max_entries = /a max_file_mb = 2000' $F
sed -i 's/^file_timeout_seconds = .*/file_timeout_seconds = 600/' $F
sed -i '/^"scan.limit_exceeded" /a "file.too_big"            = "red"' $F
februus config check
./deploy/install.sh --kiosk
```

With the theme, add `--theme /usr/local/src/februus-theme-moselle` (after a
`git pull` in that folder).

## If something goes wrong

| Symptom | What to do |
|---|---|
| Screen "Station hors service" ("out of service") | `systemctl restart februus` then `journalctl -u februus -n 50` |
| The key is never seen | It may be behind a hub (blocked), or not a plain storage key. The screen then shows "Un appareil USB a été bloqué" ("A USB device was blocked") |
| Every key is red with "La station n'a pas pu terminer l'analyse" ("The station could not finish the analysis") | `journalctl -u februus -n 100`; check `systemctl status clamav-daemon`; tell the person who manages the project, with the lines of the journal |
| Key red "already mounted" | Remove the key, wait 5 seconds, plug it in again |
| See what happened | `journalctl -u februus -f` (live), `februus stats`, `cat /var/log/februus/keys.jsonl` |
| Keyboard or mouse blocked after `--usbguard` | The script detects it and puts the old rules back by itself. Otherwise: `systemctl stop usbguard` |
| Change the name of the station | `./deploy/install.sh --name f4` |
| The kiosk does not start, or you need a terminal on the station | See the next section |

## Get back control of a station in kiosk mode

The kiosk takes the whole screen on purpose. To get a terminal on the station:

1. **Change console:** press **Ctrl+Alt+F2**. A text console asks for a login
   (`root`, or your user then `su -`). **Ctrl+Alt+F1** goes back to the
   kiosk. Only console 2 has a login: F3 to F6 show an empty screen. If the
   kiosk restarts (for example `systemctl restart februus-kiosk`), it takes
   the screen back: press Ctrl+Alt+F2 again.
2. **Start without the kiosk** (if the screen is stuck): restart the PC. In
   the GRUB menu (the list shown at the start), press `e`. Go to the end of
   the line that starts with `linux` and add ` 3` (a space, then 3). Press
   **Ctrl+X** to start. The PC starts in text mode, without the kiosk (the
   kiosk belongs to the graphical mode). This is for this boot only: the next
   normal reboot starts the kiosk again.
   - GRUB always uses an **English (QWERTY) keyboard**. On a French AZERTY
     keyboard, `3` is the key `"` **without** Shift.
   - If the GRUB menu does not show, hold **Esc** (or **Shift**) during the
     start of the PC.
3. **Otherwise, use SSH** from another PC: `ssh <user>@<station-address>`,
   then `su -`.

## What the installation put on the PC

- the code in `/opt/februus` (read-only for the services);
- the command `februus`;
- the configuration `/etc/februus/februus.toml` (do not change it without a
  reason);
- one single service, `februus` (the screens on `http://127.0.0.1:8080`, local
  to the machine);
- the key log `/var/log/februus/keys.jsonl` (one line per key);
- the USB rules (USBGuard), udev, udisks2 and polkit;
- the ClamAV settings: files up to 2 GB are checked (bigger: red at once),
  extracted archive contents go to `/var/lib/februus-clamd` (allowed by
  `/etc/apparmor.d/local/usr.sbin.clamd`);
- no sleep: the sleep targets are masked, and `consoleblank=0`
  (`/etc/default/grub.d/februus.cfg`) keeps the screen on;
- with `--kiosk`: the service `februus-kiosk` and the Firefox rules that only
  allow the station screen; the browser can only reach this machine (network
  limit on its account); one rescue console (Ctrl+Alt+F2); sounds at full
  volume.

How it works in detail: `docs/HOW-IT-WORKS.md`. Decisions: `docs/decisions.md`.
