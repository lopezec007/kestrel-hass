#!/usr/bin/env bash
# Copy the integration into a Home Assistant instance over SSH and restart core.
#
# Usage: scripts/deploy_to_ha.sh [user@host] [config_dir]
#   default host:       root@192.168.0.3   (HAOS VM with the SSH add-on)
#   default config dir: /config
#
# Requires the "Advanced SSH & Web Terminal" (or "Terminal & SSH") add-on on
# HAOS with your public key authorised. The `ha` CLI is used to restart core;
# if it is unavailable the script tells you to restart from the UI instead.
set -euo pipefail

HOST="${1:-root@192.168.0.3}"
CONFIG_DIR="${2:-/config}"
SRC="$(cd "$(dirname "$0")/.." && pwd)/custom_components/kestrel"

echo "Deploying ${SRC} -> ${HOST}:${CONFIG_DIR}/custom_components/kestrel"
ssh "${HOST}" "mkdir -p '${CONFIG_DIR}/custom_components/kestrel'"
rsync -az --delete \
  --exclude '__pycache__' --exclude '*.pyc' \
  "${SRC}/" "${HOST}:${CONFIG_DIR}/custom_components/kestrel/"

if ssh "${HOST}" 'command -v ha >/dev/null 2>&1'; then
  echo "Restarting Home Assistant core..."
  ssh "${HOST}" 'ha core restart'
else
  echo "Copied. Restart Home Assistant from Settings -> System to load the integration."
fi
