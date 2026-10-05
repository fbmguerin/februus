#!/bin/bash
# Runs once when the Codespace is created, from the repository root.
set -euo pipefail

VENV_DIR=/home/vscode/.venvs/februus

# Install februus in editable mode, in a venv that reuses the Debian
# packages (pytest, setuptools): no package downloaded from PyPI.
python3 -m venv --system-site-packages "$VENV_DIR"
"$VENV_DIR/bin/pip" install --no-build-isolation --no-deps -e .

# Download the ClamAV signatures (several hundred MB), not stored in the
# image so that the image stays small and signatures are fresh.
sudo freshclam
