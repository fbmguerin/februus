#!/bin/bash
# Apply the settings of clamd-februus.conf to clamd.conf (idempotent):
# each listed key replaces any existing line for the same key.
# Usage: apply-clamd-settings.sh [clamd.conf]   (run as root)
set -euo pipefail

SETTINGS="$(dirname "$0")/clamd-februus.conf"
CONF="${1:-/etc/clamav/clamd.conf}"

while read -r key value; do
  case "$key" in
    "" | \#*) continue ;;
  esac
  sed -i "/^${key}[[:space:]]/d" "$CONF"
  echo "$key $value" >> "$CONF"
done < "$SETTINGS"
