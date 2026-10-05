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
- A USB stick with the Debian 13 installer.
- The name of the station: `f1`, `f2`, ... `f12` (no leading zero).
- A test USB key (optional, to check at the end).

## Step 1: install Debian 13

Download the installer **`debian-13.7.0-amd64-netinst.iso`** (64-bit, small, the
rest is downloaded during the installation) from
<https://www.debian.org/distrib/netinst> (a newer `13.x` is fine), and write
it on a USB stick (on Linux: `sudo dd if=debian-13.7.0-amd64-netinst.iso
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

After the reboot, the screen "Insérez votre clé USB" ("Insert your USB key") must appear by itself.

> The kiosk was tried in a window, **not yet at the boot of a PC without
> desktop** (see `docs/hardware-validation.md`, section 8). If the screen
> stays black, log in over SSH and look at `journalctl -u februus-kiosk -b`;
> the station itself (the analysis of keys) keeps working.

To be even cleaner, then do the checks of sections 7 and 8 of
`docs/hardware-validation.md` (write the results in the "Result" column).

## Optional: a look of your own (theme)

The screens can take the look of a place (logo, colors, fonts) with a *theme*
folder, without changing the code: `sudo ./deploy/install.sh --theme
/path/to/the/theme`. See `deploy/theme-example/`. A theme that uses an official
mark (for example the State design system) must stay out of this repository.
For the Préfecture de la Moselle (State design system, French):
<https://github.com/fbmguerin/februus-theme-moselle>.

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

## What the installation put on the PC

- the code in `/opt/februus` (read-only for the services);
- the command `februus`;
- the configuration `/etc/februus/februus.toml` (do not change it without a
  reason);
- one single service, `februus` (the screens on `http://127.0.0.1:8080`, local
  to the machine);
- the key log `/var/log/februus/keys.jsonl` (one line per key);
- the USB rules (USBGuard), udev, udisks2 and polkit;
- with `--kiosk`: the service `februus-kiosk` and the Firefox rules that only
  allow the station screen.

How it works in detail: `docs/HOW-IT-WORKS.md`. Decisions: `docs/decisions.md`.
