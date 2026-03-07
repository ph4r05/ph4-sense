#!/usr/bin/env bash
# restore.sh — Reproduce all Option A (tuya-iot-core-sdk + ESP32 platform layer) changes
# from a clean git checkout of this repository.
#
# Run from the repository root:
#   bash docs/option-a-posix-sdk/restore.sh
#
# What this does:
#   1. Initialises the tuya-iot-core-sdk submodule
#   2. Copies the patched CMakeLists.txt into the submodule
#   3. Creates platform/esp32/ and writes the ESP32-native platform files:
#        storage_wrapper.c  — NVS-backed key-value storage (replaces fopen/fwrite)
#        network_wrapper.c  — TLS via esp_tls (replaces direct mbedtls 2.x API)
#        cipher_wrapper.c   — AES-GCM via PSA AEAD (mbedtls/cipher.h removed in mbedtls 4.x)
#        cipher_wrapper.h   — replaces include/cipher_wrapper.h (removes mbedtls/cipher.h include)
#        mbedtls/certs.h    — empty shim (mbedtls/certs.h removed in mbedtls 3.x)
#   4. Patches utils/log.h with an #ifndef guard for __FILENAME__
#      (ESP-IDF's assert.h also defines it; -Werror treats the double-define as error)
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

echo "==> Writing platform/esp32/network_wrapper.c..."
cp "$DOCS_DIR/network_wrapper.c" "$SDK_DIR/platform/esp32/network_wrapper.c"

echo "==> Writing platform/esp32/cipher_wrapper.c (PSA AEAD replacement)..."
cp "$DOCS_DIR/cipher_wrapper.c" "$SDK_DIR/platform/esp32/cipher_wrapper.c"

echo "==> Writing platform/esp32/cipher_wrapper.h (mbedtls/cipher.h shim)..."
cp "$DOCS_DIR/cipher_wrapper.h" "$SDK_DIR/platform/esp32/cipher_wrapper.h"

echo "==> Writing platform/esp32/mbedtls/certs.h (compat shim)..."
cp "$DOCS_DIR/certs.h" "$SDK_DIR/platform/esp32/mbedtls/certs.h"

echo "==> Patching utils/log.h (__FILENAME__ guard)..."
cp "$DOCS_DIR/log.h" "$SDK_DIR/utils/log.h"

echo "==> Writing firmware/main/tuya_cloud.c..."
cp "$DOCS_DIR/tuya_cloud.c" "$MAIN_DIR/tuya_cloud.c"

echo ""
echo "Option A restored. Next steps:"
echo "  cd firmware"
echo "  idf.py add-dependency mqtt"
echo "  idf.py update-dependencies"
echo "  idf.py set-target esp32c6"
echo "  idf.py build"
