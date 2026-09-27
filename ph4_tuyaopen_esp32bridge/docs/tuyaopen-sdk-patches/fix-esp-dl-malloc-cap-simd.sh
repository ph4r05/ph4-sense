#!/usr/bin/env bash
# Reapplies the MALLOC_CAP_SIMD compatibility shim after a fresh `tuyaopen`
# clone (or after `tos.py build` re-fetches espressif__esp-dl from scratch).
# See README.md in this directory for why.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ESPDL_DIR="$SCRIPT_DIR/../../tuyaopen/platform/ESP32/tuya_open_sdk/managed_components/espressif__esp-dl"

FILES=(
    "vision/image/dl_image_process.cpp:#include \"esp_log.h\""
    "dl/tool/src/dl_tool.cpp:#include \"soc/soc_caps.h\""
)

if [ ! -d "$ESPDL_DIR" ]; then
    echo "error: $ESPDL_DIR not found — run 'tos.py build' once first so the" >&2
    echo "component manager fetches espressif__esp-dl, then rerun this script." >&2
    exit 1
fi

SHIM='
/* MALLOC_CAP_SIMD not defined in the ESP-IDF version pinned by this
 * TuyaOpen platform commit; harmless as a no-op allocation hint fallback.
 * See ph4_tuyaopen_esp32bridge/docs/tuyaopen-sdk-patches/. */
#ifndef MALLOC_CAP_SIMD
#define MALLOC_CAP_SIMD 0
#endif
'

for entry in "${FILES[@]}"; do
    file="${entry%%:*}"
    anchor="${entry#*:}"
    path="$ESPDL_DIR/$file"

    if [ ! -f "$path" ]; then
        echo "warning: $path not found, skipping" >&2
        continue
    fi
    if grep -q 'ifndef MALLOC_CAP_SIMD' "$path"; then
        echo "Already patched: $path"
        continue
    fi

    awk -v anchor="$anchor" -v shim="$SHIM" '
        { print }
        $0 == anchor && !done { print shim; done=1 }
    ' "$path" > "$path.tmp" && mv "$path.tmp" "$path"
    echo "Patched: $path"
done
