#!/usr/bin/env bash
# Sync local ph4ha config/apps to the rock server and update AppDaemon's
# live app directory in place. Uses a single shared SSH connection so the
# OTP is only entered once.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="rock"
CONTROL_PATH="/tmp/ssh-mux-${HOST}-$$"

cleanup() {
    ssh -o ControlPath="$CONTROL_PATH" -O exit "$HOST" 2>/dev/null || true
}
trap cleanup EXIT

# Open the shared connection (prompts for OTP once).
ssh -o ControlMaster=yes -o ControlPath="$CONTROL_PATH" -o ControlPersist=5m -fN "$HOST"

rsync -av -e "ssh -o ControlPath=$CONTROL_PATH" "$SCRIPT_DIR/" "$HOST:ph4ha/"

ssh -o ControlPath="$CONTROL_PATH" "$HOST" '
set -euo pipefail
cp ~/ph4ha/apps/blinds.py ~/ha-py/apps/blinds/
cp ~/ph4ha/apps/blinds_policy.py ~/ha-py/apps/blinds/
cp ~/ph4ha/config/blinds_policy.yaml ~/ha-py/apps/blinds/
'
