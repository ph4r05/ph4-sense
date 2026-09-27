#!/usr/bin/env bash
# Reapplies the 8MB-flash fix for ESP32-C6 after a fresh `tuyaopen` clone.
# See README.md in this directory for why.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUYAOPEN="$SCRIPT_DIR/../../tuyaopen"
SDK="$TUYAOPEN/platform/ESP32/tuya_open_sdk"

BOARD_KCONFIG="$TUYAOPEN/boards/ESP32/ESP32-C6/Kconfig"
SDKCONFIG_SEED="$SDK/sdkconfig_esp32c6"
PARTITIONS="$SDK/partitions.csv"
PARTITIONS_8M="$SDK/partitions_8M.csv"

if [ ! -f "$BOARD_KCONFIG" ]; then
    echo "error: $BOARD_KCONFIG not found — clone tuyaopen first (see ph4_tuyaopen_esp32bridge/README.md)" >&2
    exit 1
fi

# 1. Board Kconfig: select 8M instead of 16M flash size.
if grep -q 'select PLATFORM_FLASHSIZE_16M' "$BOARD_KCONFIG"; then
    sed -i.bak 's/select PLATFORM_FLASHSIZE_16M/select PLATFORM_FLASHSIZE_8M/' "$BOARD_KCONFIG"
    rm -f "$BOARD_KCONFIG.bak"
    echo "Patched: $BOARD_KCONFIG"
else
    echo "Already patched (or upstream changed): $BOARD_KCONFIG"
fi

# 2. Per-chip sdkconfig seed: same flash-size flip (this file is what
#    build_setup.py's set-target step actually seeds sdkconfig from, so the
#    Kconfig default above isn't enough on its own).
if [ -f "$SDKCONFIG_SEED" ] && grep -q 'CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y' "$SDKCONFIG_SEED"; then
    sed -i.bak \
        -e 's/# CONFIG_ESPTOOLPY_FLASHSIZE_8MB is not set/CONFIG_ESPTOOLPY_FLASHSIZE_8MB=y/' \
        -e 's/CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y/# CONFIG_ESPTOOLPY_FLASHSIZE_16MB is not set/' \
        -e 's/CONFIG_ESPTOOLPY_FLASHSIZE="16MB"/CONFIG_ESPTOOLPY_FLASHSIZE="8MB"/' \
        "$SDKCONFIG_SEED"
    rm -f "$SDKCONFIG_SEED.bak"
    echo "Patched: $SDKCONFIG_SEED"
elif [ ! -f "$SDKCONFIG_SEED" ]; then
    echo "warning: $SDKCONFIG_SEED not found, skipping (run 'tos.py build' once first)" >&2
else
    echo "Already patched (or upstream changed): $SDKCONFIG_SEED"
fi

# 3. Partition table: swap in the ready-made 8MB layout (partitions.csv is
#    gitignored inside tuya_open_sdk — it's meant to be hand-set per board).
if [ -f "$PARTITIONS_8M" ]; then
    cp "$PARTITIONS_8M" "$PARTITIONS"
    echo "Copied: $PARTITIONS_8M -> $PARTITIONS"
else
    echo "warning: $PARTITIONS_8M not found, skipping" >&2
fi

# After running this, do a full clean rebuild so the stale 16MB sdkconfig/
# build dir don't linger:
#   rm -f "$SDK/sdkconfig"
#   tos.py config choice -c ESP32-C6.config
#   tos.py build -v
