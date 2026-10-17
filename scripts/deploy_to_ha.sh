#!/usr/bin/env bash
# Copy the integration into a Home Assistant instance over SSH and restart core.
#
# Usage: scripts/deploy_to_ha.sh [user@host] [config_dir]
#   default host:       root@192.168.0.3   (HAOS VM with the Terminal & SSH add-on)
#   default config dir: /config
#
# Environment:
#   SSH_KEY   identity file to use (optional)
#   NO_RESTART=1  copy only, do not restart core
#
# The Terminal & SSH add-on has no rsync, so the tree is streamed as a tarball.
set -euo pipefail

HOST="${1:-root@192.168.0.3}"
CONFIG_DIR="${2:-/config}"
SRC="$(cd "$(dirname "$0")/.." && pwd)/custom_components"

SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10)
if [ -n "${SSH_KEY:-}" ]; then
  SSH+=(-i "${SSH_KEY}" -o IdentitiesOnly=yes)
fi

echo "Deploying ${SRC}/kestrel -> ${HOST}:${CONFIG_DIR}/custom_components/kestrel"
tar czf - --exclude='__pycache__' --exclude='*.pyc' -C "${SRC}" kestrel \
  | "${SSH[@]}" "${HOST}" \
      "mkdir -p '${CONFIG_DIR}/custom_components' \
       && rm -rf '${CONFIG_DIR}/custom_components/kestrel' \
       && tar xzf - -C '${CONFIG_DIR}/custom_components' \
       && echo 'Copied:' && ls '${CONFIG_DIR}/custom_components/kestrel'"

if [ "${NO_RESTART:-0}" = "1" ]; then
  echo "Skipping restart (NO_RESTART=1)."
elif "${SSH[@]}" "${HOST}" 'command -v ha >/dev/null 2>&1'; then
  echo "Restarting Home Assistant core..."
  "${SSH[@]}" "${HOST}" 'ha core restart'
  echo "Restart requested."
else
  echo "Copied. Restart Home Assistant from Settings -> System to load the integration."
fi
