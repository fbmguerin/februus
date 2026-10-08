#!/bin/bash
# Report of the state of a station (read-only): to paste in a message when
# something goes wrong, or to note the state during the acceptance test.
# Run as root (su -):   tools/station-report.sh
# FR : rapport en lecture seule de l'état de la station.
PATH="$PATH:/usr/sbin:/sbin"
title() { echo; echo "== $*"; }

title "System"
echo "date: $(date -Is)"; echo "host: $(hostname)"
grep PRETTY_NAME /etc/os-release; uname -r
echo "desktop session: $(loginctl list-sessions --no-legend 2>/dev/null | grep -c seat0) (0 on a real kiosk)"

title "Februus"
dpkg -l python3-fastapi python3-uvicorn python3-jinja2 python3-pyudev 2>/dev/null | awk '/^ii/{print $2, $3}'
systemctl is-active februus; systemctl is-enabled februus
systemctl show -p NRestarts,ActiveEnterTimestamp februus
echo "screen: $(curl -s -m 5 http://127.0.0.1:8080 | grep -o '<h1>[^<]*' | head -1)"
ss -ltn | grep 8080
februus config check 2>&1 | tail -3
ls -ld /etc/februus/theme 2>&1 | cut -c1-60
systemctl is-active februus-kiosk 2>&1

title "ClamAV"
systemctl is-active clamav-daemon clamav-freshclam
ls -l /var/lib/clamav/*.c[lv]d 2>/dev/null | awk '{print $5, $6, $7, $8, $9}'

title "USB (USBGuard) and mounts"
systemctl is-active usbguard
usbguard list-devices 2>/dev/null | sed -E 's/ serial "[^"]*"//; s/ hash .* (via-port|with-interface)/ \1/' | cut -c1-140
echo "--- mounts of removable disks:"; grep -E ' /media/| /dev/sd' /proc/self/mountinfo | cut -c1-140

title "Keys log (last 5 lines) and statistics"
tail -n 5 /var/log/februus/keys.jsonl 2>&1 | cut -c1-240
runuser -u februus -- februus stats 2>&1 | head -8

title "Journal (last 25 lines)"
journalctl -u februus -n 25 --no-pager -o cat 2>&1 | grep -v 'GET ' | cut -c1-200
