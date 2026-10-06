#!/bin/bash
# Install or update Februus on a Debian 13 station. Run as root, from a
# copy of the repository (su -):   deploy/install.sh [options]
#
# The script can be run again after each update of the code: every step
# replaces what the previous run installed. It never touches
# /etc/februus/februus.toml once it exists, nor the key log.
#
# Options:
#   --no-apt     do not install the Debian packages (already installed, or
#                no network)
#   --usbguard   also install the USBGuard rules. The devices plugged in
#                NOW (keyboard, mouse...) become the only non-storage
#                devices allowed: unplug everything else first.
#   --kiosk      also install the kiosk (cage + Firefox). NOT TESTED YET.
#   --theme DIR  copy the theme folder DIR (templates/ and static/) to
#                /etc/februus/theme: another look for the screens. See
#                deploy/theme-example/.
#   --name NAME  name of the station (f1, f2, ... f12: no leading zeros).
#                It becomes the name of the machine (hostname), shown on
#                the screens. Without this option the current name is kept.
#
# FR : installe ou met à jour Februus. Peut être relancé sans risque.
set -euo pipefail

APT=yes USBGUARD=no KIOSK=no NAME= THEME=
while [ $# -gt 0 ]; do
  case "$1" in
    --no-apt) APT=no ;;
    --usbguard) USBGUARD=yes ;;
    --kiosk) KIOSK=yes ;;
    --theme) [ $# -ge 2 ] || { echo "--theme needs a folder" >&2; exit 2; }
             THEME="$2"; shift ;;
    --name) [ $# -ge 2 ] || { echo "--name needs a value (example: --name f3)" >&2; exit 2; }
            NAME="$2"; shift ;;
    --name=*) NAME="${1#--name=}" ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
# A valid machine name: lowercase letters, digits and "-", at most 63.
if [ -n "$NAME" ] && ! [[ "$NAME" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; then
  echo "invalid station name: '$NAME' (example: f3)" >&2
  exit 2
fi
if [ -n "$THEME" ] && ! { [ -d "$THEME/templates" ] || [ -d "$THEME/static" ]; }; then
  echo "invalid theme: '$THEME' has no templates/ or static/ folder" >&2
  exit 2
fi
[ "$(id -u)" = 0 ] || { echo "run as root (su -): $0" >&2; exit 1; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PATH="$PATH:/usr/sbin:/sbin"
step() { echo; echo "== $*"; }

step "0. Station name"
if [ -n "$NAME" ]; then
  hostnamectl set-hostname "$NAME"
  # Debian keeps the name of the machine in /etc/hosts too (127.0.1.1).
  if grep -q '^127\.0\.1\.1[[:space:]]' /etc/hosts; then
    sed -i "s/^127\.0\.1\.1[[:space:]].*/127.0.1.1\t$NAME/" /etc/hosts
  else
    printf '127.0.1.1\t%s\n' "$NAME" >> /etc/hosts
  fi
fi
echo "station name: $(hostname)"
if [ -e /etc/februus/februus.toml ] && grep -Eq '^[[:space:]]*name[[:space:]]*=' /etc/februus/februus.toml; then
  echo "note: /etc/februus/februus.toml sets station.name, which wins over the machine name"
fi

step "1. Debian packages"
PACKAGES="python3 python3-fastapi python3-uvicorn python3-jinja2
  python3-pyudev clamav-daemon clamav-freshclam udisks2 polkitd usbguard"
[ "$KIOSK" = yes ] && PACKAGES="$PACKAGES cage firefox-esr alsa-utils"
if [ "$APT" = yes ]; then
  # shellcheck disable=SC2086
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends $PACKAGES
else
  echo "skipped (--no-apt)"
fi

step "2. Account (no home, no shell)"
# februus: the one account of the service (it can read the raw USB disks
# and mount the keys, nothing else).
id februus >/dev/null 2>&1 || adduser --system --group --no-create-home februus

step "3. Code in /opt/februus (owned by root, read-only for the services)"
rm -rf /opt/februus.new
install -d -m 755 /opt/februus.new
cp -r "$REPO/februus" /opt/februus.new/
find /opt/februus.new -name __pycache__ -prune -exec rm -rf {} +
chown -R root:root /opt/februus.new
chmod -R u=rwX,go=rX /opt/februus.new
python3 -m compileall -q /opt/februus.new/februus
# An update may need new keys in an existing configuration: check it with
# the NEW code BEFORE replacing the old one, so that a station is never
# left with new code and a configuration it refuses.
# FR : la configuration existante est vérifiée avec le NOUVEAU code avant
# de remplacer l'ancien ; sinon rien n'est changé.
if [ -e /etc/februus/februus.toml ] \
    && ! PYTHONPATH=/opt/februus.new /usr/bin/python3 -m februus config check >/dev/null 2>&1; then
  PYTHONPATH=/opt/februus.new /usr/bin/python3 -m februus config check || true
  echo "fix /etc/februus/februus.toml (see config/februus.example.toml), then run this script again" >&2
  echo "nothing was changed in /opt/februus" >&2
  rm -rf /opt/februus.new
  exit 1
fi
rm -rf /opt/februus.old
[ -d /opt/februus ] && mv /opt/februus /opt/februus.old
mv /opt/februus.new /opt/februus
rm -rf /opt/februus.old
cat > /usr/local/bin/februus <<'LAUNCHER'
#!/bin/sh
# Februus command (installed by deploy/install.sh): runs the code of
# /opt/februus with the Python packages of Debian.
PYTHONPATH=/opt/februus exec /usr/bin/python3 -m februus "$@"
LAUNCHER
chmod 755 /usr/local/bin/februus

step "4. Configuration"
install -d -m 755 /etc/februus /etc/februus/conf.d
if [ -e /etc/februus/februus.toml ]; then
  echo "/etc/februus/februus.toml kept"
else
  install -m 644 "$REPO/config/februus.example.toml" /etc/februus/februus.toml
  echo "/etc/februus/februus.toml created from the example"
fi

if [ -n "$THEME" ]; then
  step "4b. Theme"
  # Owned by root, read-only for the service.
  # Only templates/ and static/ are copied (not .git, README, scripts...).
  rm -rf /etc/februus/theme.new
  install -d /etc/februus/theme.new
  for part in templates static; do
    if [ -d "$THEME/$part" ]; then cp -r "$THEME/$part" /etc/februus/theme.new/; fi
  done
  chown -R root:root /etc/februus/theme.new
  chmod -R u=rwX,go=rX /etc/februus/theme.new
  rm -rf /etc/februus/theme
  mv /etc/februus/theme.new /etc/februus/theme
  echo "theme installed in /etc/februus/theme"
fi

step "5. ClamAV settings"
"$REPO/deploy/clamav/apply-clamd-settings.sh"
systemctl enable --now clamav-freshclam.service
# clamd refuses to start without signatures (first install: freshclam is
# still downloading them).
if ls /var/lib/clamav/*.c[lv]d >/dev/null 2>&1; then
  systemctl enable clamav-daemon.service
  systemctl restart clamav-daemon.service
else
  echo "no ClamAV signatures yet: wait for freshclam, then run this script again"
fi

step "6. udev, udisks2 and polkit rules"
install -m 644 "$REPO/deploy/udev/70-februus.rules" /etc/udev/rules.d/70-februus.rules
install -m 644 "$REPO/deploy/udisks2/mount_options.conf" /etc/udisks2/mount_options.conf
install -m 644 "$REPO/deploy/polkit/49-februus-udisks2.rules" /etc/polkit-1/rules.d/49-februus-udisks2.rules
udevadm control --reload
udevadm trigger --subsystem-match=block --action=change
systemctl restart udisks2.service

step "7. Key log folder"
install -m 644 "$REPO/deploy/systemd/februus.tmpfiles" /etc/tmpfiles.d/februus.conf
systemd-tmpfiles --create /etc/tmpfiles.d/februus.conf

step "7b. Never sleep, screen always on"
# A station waits for keys all day: no suspend, and the text console (what
# the screen shows when the kiosk is not running) never goes blank. A file
# in grub.d, so /etc/default/grub stays as Debian wrote it.
# FR : jamais de mise en veille ; la console ne s'éteint jamais.
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
install -d -m 755 /etc/default/grub.d
cat > /etc/default/grub.d/februus.cfg <<'GRUB'
# Written by Februus (deploy/install.sh): the console never goes blank.
GRUB_CMDLINE_LINUX_DEFAULT="$GRUB_CMDLINE_LINUX_DEFAULT consoleblank=0"
GRUB
if command -v update-grub >/dev/null; then
  update-grub
  echo "consoleblank=0 is active after the next reboot"
else
  echo "update-grub not found: add consoleblank=0 to the kernel command line by hand" >&2
fi

if [ "$USBGUARD" = yes ]; then
  step "8. USBGuard rules"
  # Station devices = what is plugged in now, without the storage devices
  # (keys are allowed by the generic rule of deploy/usbguard/rules.conf).
  # FR : les périphériques branchés maintenant (clavier, souris) sont les
  # seuls autorisés en plus des clés de stockage pur.
  new=$(mktemp)
  {
    echo "# Written by deploy/install.sh on $(date -I)."
    echo "# Devices of the station itself:"
    usbguard generate-policy | grep -v 'with-interface 08:' || true
    echo
    cat "$REPO/deploy/usbguard/rules.conf"
  } > "$new"
  [ -e /etc/usbguard/rules.conf ] && cp -p /etc/usbguard/rules.conf /etc/usbguard/rules.conf.before-februus
  install -m 600 "$new" /etc/usbguard/rules.conf
  rm -f "$new"
  systemctl enable usbguard.service
  systemctl restart usbguard.service
  sleep 2
  # Safety: no keyboard or mouse (interface class 03) may be blocked by
  # the new rules, else the station cannot be administered any more.
  if usbguard list-devices | grep ' block ' | grep -q 'with-interface.* 03:'; then
    echo "a keyboard or mouse is BLOCKED by the new rules: old rules restored" >&2
    if [ -e /etc/usbguard/rules.conf.before-februus ]; then
      cp -p /etc/usbguard/rules.conf.before-februus /etc/usbguard/rules.conf
      systemctl restart usbguard.service
    else
      systemctl stop usbguard.service
    fi
    exit 1
  fi
  usbguard list-devices | sed -E 's/ serial "[^"]*"//; s/ hash .* with-interface/ with-interface/'
else
  step "8. USBGuard rules: skipped (use --usbguard)"
fi

step "9. Service"
# An older install had three services (scanner, web, analyzers) and a
# SQLite database: they are replaced by the one service "februus". The
# old data and the accounts februus-web and februus-analyzer are NOT
# deleted (remove them by hand when sure: userdel, rm -r /var/lib/februus).
# FR : l'ancienne installation (3 services, base SQLite) est remplacée ;
# anciennes données et comptes ne sont pas supprimés.
for old in februus-scanner.service februus-web.service februus-analyzer.socket; do
  if [ -e "/etc/systemd/system/$old" ]; then
    systemctl disable --now "$old" || true
    rm -f "/etc/systemd/system/$old"
  fi
done
rm -f "/etc/systemd/system/februus-analyzer@.service"
install -m 644 "$REPO/deploy/systemd/februus.service" /etc/systemd/system/februus.service
systemctl daemon-reload
/usr/local/bin/februus config check >/dev/null || { /usr/local/bin/februus config check; exit 1; }
systemctl enable februus.service
systemctl restart februus.service

if [ "$KIOSK" = yes ]; then
  step "10. Kiosk (NOT TESTED YET)"
  id februus-kiosk >/dev/null 2>&1 || adduser --system --group --home /var/lib/februus-kiosk februus-kiosk
  install -d -m 755 /usr/lib/firefox-esr/distribution
  install -m 644 "$REPO/deploy/kiosk/policies.json" /usr/lib/firefox-esr/distribution/policies.json
  install -d -m 755 /usr/local/lib/februus
  install -m 755 "$REPO/deploy/kiosk/wait-for-gpu.sh" /usr/local/lib/februus/wait-for-gpu.sh
  install -m 644 "$REPO/deploy/kiosk/februus-kiosk.service" /etc/systemd/system/februus-kiosk.service
  # Forget the files cached by the kiosk browser (style sheets of an older
  # version or theme). Only the cache: the profile is kept.
  rm -rf /var/lib/februus-kiosk/.cache/mozilla
  # One rescue text console (tty2), none on tty3 to tty6 (next boot).
  install -d -m 755 /etc/systemd/logind.conf.d
  install -m 644 "$REPO/deploy/logind/februus.conf" /etc/systemd/logind.conf.d/februus.conf
  systemctl daemon-reload
  systemctl enable februus-kiosk.service
  # Sounds of the screens: the sound card starts muted on a minimal Debian.
  # Every output at full volume, saved (alsa-utils restores it at boot).
  # FR : la carte son démarre muette : tout au maximum, réglage conservé.
  if command -v amixer >/dev/null && [ -e /proc/asound/cards ] \
      && ! grep -q 'no soundcards' /proc/asound/cards; then
    amixer scontrols | sed -n "s/^Simple mixer control '\([^']*\)',.*/\1/p" |
      while IFS= read -r control; do
        amixer -q sset "$control" 100% unmute 2>/dev/null || true
      done
    alsactl store && echo "sound: every output at full volume"
  else
    echo "no sound card found: the screens will be silent"
  fi
  echo "kiosk installed; it starts at the next boot (graphical target)"
fi

step "Done"
sleep 2
systemctl --no-pager --lines=0 status februus.service | grep -E '●|Active:'
