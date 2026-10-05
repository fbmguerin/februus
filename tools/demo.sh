#!/bin/bash
# Demo of the live screens on a test folder (no USB key, no ClamAV needed).
# Usage: tools/demo.sh [green|red|long]
#   green: clean folder, red: one "malicious" file (fake marker),
#   long: shows the "come back at HH:MM" screen.
# Open http://127.0.0.1:8080 in a browser (Codespaces: "Ports" tab, 8080).
set -euo pipefail

cd "$(dirname "$0")/.."
MODE="${1:-green}"
FEBRUUS="${FEBRUUS:-februus}"
WORK="$(mktemp -d)"
CONFIG="$WORK/demo.toml"

# Development configuration, with its own key log and a slow fake
# analyzer so that the progress can be watched.
sed -e "s|^path = \".*\"|path = \"$WORK/keys.jsonl\"|" \
    -e "s|^delay_ms = 0|delay_ms = 150|" \
    config/februus.dev.toml > "$CONFIG"
if [ "$MODE" = long ]; then
  sed -i "s|^long_scan_warning_minutes = .*|long_scan_warning_minutes = 0|; s|^delay_ms = 150|delay_ms = 1500|" "$CONFIG"
fi

mkdir "$WORK/key"
for i in $(seq 1 80); do
  echo "Document number $i" > "$WORK/key/document-$i.txt"
done
if [ "$MODE" = red ]; then
  echo "FEBRUUS-FAKE-MALWARE" > "$WORK/key/document-42.txt"
fi

trap 'rm -rf "$WORK"' EXIT
# The screens and a simulated key: Enter inserts it, Enter removes it.
"$FEBRUUS" demo -c "$CONFIG" "$WORK/key"
