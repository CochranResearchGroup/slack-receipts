#!/usr/bin/env bash
set -euo pipefail

# Uninstall systemd --user units for Slack Receipts live mode.
#
# Usage:
#   scripts/uninstall_live_mode_systemd_user.sh [workspace]

UNIT_DIR="${HOME}/.config/systemd/user"
WORKSPACE="${1:-}"
if [[ -n "${WORKSPACE}" ]]; then
  UNITS=(
    "slack-receipts-webhooks-${WORKSPACE}.service"
    "slack-receipts-daemon-${WORKSPACE}.service"
    "slack-mirror-webhooks-${WORKSPACE}.service"
    "slack-mirror-daemon-${WORKSPACE}.service"
    "slack-mirror-events-${WORKSPACE}.service"
    "slack-mirror-embeddings-${WORKSPACE}.service"
  )
else
  mapfile -t UNITS < <(
    systemctl --user list-unit-files 'slack-receipts-webhooks-*.service' 'slack-receipts-daemon-*.service' 'slack-mirror-webhooks*.service' 'slack-mirror-daemon*.service' 'slack-mirror-events*.service' 'slack-mirror-embeddings*.service' --no-legend --no-pager 2>/dev/null \
      | awk '{print $1}' \
      | sort -u
  )
fi

if [[ ${#UNITS[@]} -eq 0 ]]; then
  echo "No Slack Receipts or legacy Slack Mirror live-mode units found."
  exit 0
fi

echo "Stopping + disabling services (if present)..."
for u in "${UNITS[@]}"; do
  systemctl --user disable --now "$u" 2>/dev/null || true
done

echo "Removing unit files..."
for u in "${UNITS[@]}"; do
  rm -f "${UNIT_DIR}/${u}"
done

systemctl --user daemon-reload
systemctl --user reset-failed

echo "Uninstall complete."
echo
systemctl --user --no-pager --full status "${UNITS[@]}" 2>/dev/null || true
