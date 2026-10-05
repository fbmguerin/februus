#!/bin/bash
# Setup script for the Claude Code web environment ("februus").
# Copy of the script pasted in the environment settings (Script de
# configuration): keep both in sync. It runs as root before each session.
# Prepares a dev environment close to the target station:
# Python 3.13 venv with pytest, and the ClamAV daemon (clamd).
# Codespaces uses .devcontainer/ instead.
set -euo pipefail

VENV_DIR=/opt/februus-venv
REPO_DIR=/home/user/februus
PYTHON=python3.13
CLAMAV_DB_DIR=/var/lib/clamav
CLAMAV_RUN_DIR=/run/clamav

warn() {
  echo "februus setup: WARNING: $*" >&2
}

# 1. ClamAV packages (apt). Skipped when already installed.
if ! command -v clamd >/dev/null || ! command -v clamdscan >/dev/null \
    || ! command -v freshclam >/dev/null; then
  apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
    clamav-daemon clamav-freshclam clamdscan
fi

# 2. Python venv with the target Python version and test tools,
# put first in PATH for the shells of the session.
if [ ! -x "$VENV_DIR/bin/python" ]; then
  "$PYTHON" -m venv "$VENV_DIR"
fi
# Same versions as the Debian 13 packages used on the station.
"$VENV_DIR/bin/pip" install -q --disable-pip-version-check pytest \
  "fastapi==0.115.*" "starlette==0.46.*" "uvicorn==0.32.*" "jinja2==3.1.*" \
  "httpx==0.28.*" "pyudev==0.24.*"
PATH_LINE="export PATH=\"$VENV_DIR/bin:\$PATH\""
grep -qxF "$PATH_LINE" ~/.bashrc 2>/dev/null || echo "$PATH_LINE" >> ~/.bashrc

# 3. ClamAV signatures (database.clamav.net must be allowed by the network
# policy). freshclam drops to the clamav user, which cannot read the proxy
# CA bundle under /root: use the system bundle.
CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt freshclam --quiet \
  || warn "freshclam failed (network policy?), signatures may be missing or outdated."

# 4. clamd settings required by Februus (encrypted files, limits), kept in
# the repository. Applied only if the repository is already cloned.
if [ -x "$REPO_DIR/deploy/clamav/apply-clamd-settings.sh" ]; then
  "$REPO_DIR/deploy/clamav/apply-clamd-settings.sh"
else
  warn "$REPO_DIR not found, clamd settings not applied (run deploy/clamav/apply-clamd-settings.sh)."
fi

# 5. Start clamd (no systemd in this container) if signatures exist.
if ! compgen -G "$CLAMAV_DB_DIR/*.c[vl]d" >/dev/null; then
  warn "no ClamAV signatures in $CLAMAV_DB_DIR, clamd not started."
  warn "ClamAV integration tests (pytest -m clamav) will be skipped."
  exit 0
fi
if ! clamdscan --ping 1 >/dev/null 2>&1; then
  mkdir -p "$CLAMAV_RUN_DIR"
  chown clamav:clamav "$CLAMAV_RUN_DIR"
  clamd
  # Loading the full signature set takes up to a minute.
  clamdscan --ping 60:2 >/dev/null || warn "clamd did not answer in time."
fi
