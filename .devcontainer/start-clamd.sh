#!/bin/bash
# Runs at each Codespace start: there is no systemd in the container,
# so clamd is started by hand.
set -euo pipefail

if clamdscan --ping 1 >/dev/null 2>&1; then
  exit 0
fi
sudo mkdir -p /run/clamav
sudo chown clamav:clamav /run/clamav
sudo clamd
# Loading the full signature set takes up to a minute.
clamdscan --ping 60:2
