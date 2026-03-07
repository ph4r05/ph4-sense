#!/usr/bin/env bash
# restore.sh — Reproduce all Option A (tuya-iot-core-sdk POSIX) changes
# from a clean git checkout of this repository.
#
# Run from the repository root:
#   bash docs/option-a-posix-sdk/restore.sh
#
# What this does:
#   1. Initialises the tuya-iot-core-sdk submodule
#   2. Copies the patched CMakeLists.txt into the submodule
#   3. Creates the ESP32 NVS storage wrapper
#   4. Creates the mbedtls/certs.h compatibility shim
#   5. Copies the Option A tuya_cloud.c into firmware/main/

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SDK_DIR="$REPO_ROOT/firmware/components/tuya-iot-core-sdk"
MAIN_DIR="$REPO_ROOT/firmware/main"
DOCS_DIR="$REPO_ROOT/docs/option-a-posix-sdk"

echo "==> Initialising submodule..."
git -C "$REPO_ROOT" submodule update --init --recursive

echo "==> Writing tuya-iot-core-sdk/CMakeLists.txt..."
cp "$DOCS_DIR/tuya-sdk-CMakeLists.txt" "$SDK_DIR/CMakeLists.txt"

echo "==> Creating platform/esp32/..."
mkdir -p "$SDK_DIR/platform/esp32/mbedtls"

echo "==> Writing platform/esp32/storage_wrapper.c..."
cp "$DOCS_DIR/storage_wrapper.c" "$SDK_DIR/platform/esp32/storage_wrapper.c"

echo "==> Writing platform/esp32/mbedtls/certs.h (compat shim)..."
cp "$DOCS_DIR/certs.h" "$SDK_DIR/platform/esp32/mbedtls/certs.h"

echo "==> Writing firmware/main/tuya_cloud.c..."
cp "$DOCS_DIR/tuya_cloud.c" "$MAIN_DIR/tuya_cloud.c"

echo ""
echo "Option A restored. Next steps:"
echo "  cd firmware"
echo "  idf.py add-dependency mqtt"
echo "  idf.py update-dependencies"
echo "  idf.py set-target esp32c6"
echo "  idf.py build"
echo ""
echo "NOTE: This approach was abandoned because tuya-iot-core-sdk uses mbedtls 2.x"
echo "APIs that are incompatible with ESP-IDF 5.x+ (mbedtls 3.x). See README.md."
