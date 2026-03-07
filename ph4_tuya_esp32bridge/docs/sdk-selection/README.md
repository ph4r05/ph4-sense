# Tuya SDK Selection — Investigation Notes

This document records all Tuya SDK options that were evaluated for the ESP32-C6
firmware, with rationale for why each was accepted or rejected.

---

## Project requirements

The firmware is an **ESP-IDF component** that runs alongside WiFi, MQTT, GPIO,
and other components inside a standard `idf.py`-based project. The Tuya
integration only needs to:

1. Activate a device on Tuya Cloud (first-time pairing via token)
2. Report boolean DP (Data Point) values to the cloud (device → cloud)
3. Receive boolean DP commands from the cloud (cloud → device)
4. Reconnect automatically on WiFi/cloud drops

That is: **a thin Tuya MQTT cloud client**, not a full product framework.

---

## Options evaluated

### Option A: `tuya-iot-core-sdk` (POSIX/mbedtls) — CHOSEN

Repository: https://github.com/tuya/tuya-iot-core-sdk

**Status:** Active at time of evaluation, ~200 stars, C language, last commit ~2022.

**Architecture:** POSIX portable C library. Uses mbedtls directly for TLS,
coreMQTT for the MQTT layer, and a PAL (platform abstraction layer) with
pluggable `network_wrapper.c` / `storage_wrapper.c`.

**Why chosen:** Smallest footprint, designed to be embedded as a component,
clean PAL boundary allows swapping the platform layer. The MQTT/protocol logic
does not touch hardware.

**Challenges and fixes:**

| Problem | Fix |
|---------|-----|
| `cmake_minimum_required(VERSION 3.2.0)` — CMake 4.x dropped <3.5 | Replaced entire CMakeLists.txt with `idf_component_register()` wrapper |
| `libraries/mbedtls/` bundled — conflicts with openthread's bundled copy | `file(REMOVE_RECURSE)` at configure time |
| `platform/posix/storage_wrapper.c` uses `fopen/fwrite` — no filesystem on ESP32 | New `platform/esp32/storage_wrapper.c` using NVS |
| `mbedtls/certs.h` missing — removed in mbedtls 3.x | Empty shim at `platform/esp32/mbedtls/certs.h` |
| `platform/posix/network_wrapper.c` uses mbedtls 2.x struct internals | New `platform/esp32/network_wrapper.c` using `esp_tls` |
| coreJSON uses `true` as enum constant — illegal in C23 | `target_compile_options` adding `-std=c11` for that file |
| `__FILENAME__` macro — defined in both Tuya `log.h` and ESP-IDF `assert.h` | `#ifndef` guard added to SDK's `log.h` copy |

See `docs/option-a-posix-sdk/README.md` for the full history of the POSIX
network approach (before the ESP32-native `network_wrapper.c` was written).

---

### Option B: `tuya-connect-kit-for-mqtt-embedded-c` — REJECTED (archived)

Repository: https://github.com/tuya/tuya-connect-kit-for-mqtt-embedded-c

**Status:** **Archived and deprecated** by Tuya. README explicitly says to use
TuyaOpen instead.

**Architecture:** Same POSIX/mbedtls structure as `tuya-iot-core-sdk`. Would
have had identical mbedtls 2.x vs 3.x compatibility problems.

**Why rejected:** Deprecated upstream; same problems as Option A but without a
path forward.

---

### Option C: `tuya-connect-kit-for-esp-idf` — REJECTED (does not exist)

This repository name was referenced in documentation and discussions, but
**does not exist** on Tuya's GitHub. No such repository was found.

---

### Option D: TuyaOpen (`tuya/tuyaopen`) — REJECTED (wrong model)

Repository: https://github.com/tuya/tuyaopen

**Status:** Active, ~1370 stars (as of 2026-03), updated continuously, C
language. Officially recommended by Tuya as the successor to the deprecated SDKs.

**ESP32-C6 support:** Yes — `TuyaOpen-esp32` platform repo has
`sdkconfig_esp32c6` targeting ESP-IDF 5.4.0. The `tuyaos_adapter` layer
contains proper ESP-IDF native implementations (`tkl_network.c`, `tkl_wifi.c`,
etc.) that don't touch mbedtls internals directly. No mbedtls 2.x vs 3.x
issues.

**Why rejected despite being the "right" SDK:**

TuyaOpen is a **full product firmware framework**, not a library you embed.
Using it would require inverting the project structure:

1. **Own build system:** TuyaOpen uses `tos.py` as its build orchestrator, not
   `idf.py`. It downloads and manages its own copy of ESP-IDF. You cannot use
   `idf.py build` in a TuyaOpen project.

2. **Incompatible component model:** The project is structured as a standard
   ESP-IDF project where Tuya is one component among many (WiFi, HA-MQTT,
   GPIO, NVS config). TuyaOpen expects to own the entire application — your
   app logic would live inside TuyaOpen as an "app", not the other way around.

3. **Massive scope:** TuyaOpen includes AI agents, LVGL display stacks, audio
   (ASR/TTS/KWS), Bluetooth, OTA, and full device lifecycle management. The
   firmware only needs Tuya cloud MQTT. Pulling in TuyaOpen would add thousands
   of files and a completely alien build system for a feature that is ~300 lines
   of protocol code.

4. **API incompatibility:** TuyaOpen uses a `tal_*`/`tkl_*` API (Tuya
   Abstraction Layer / Tuya Kernel Layer). The existing `tuya_cloud.c` public
   interface (`tuya_cloud_init`, `tuya_cloud_report_bool`, etc.) and all its
   callers (`dp_bridge.c`, `main.c`) would need to be rewritten from scratch —
   no incremental migration path.

5. **`arduino-TuyaOpen`:** Arduino wrapper targeting Tuya's own T2/T3/T5
   modules. Does not support ESP32-C6 with ESP-IDF.

**Conclusion:** TuyaOpen solves the right problem (modern Tuya SDK with ESP32
support) but for full product builds. For a focused ESP-IDF component, the
correct approach is Option A with an ESP32-native platform layer.

---

## Decision

**Use `tuya-iot-core-sdk` (Option A) with a custom `platform/esp32/` layer.**

The SDK's MQTT protocol logic (`src/`, `libraries/coreMQTT/`, `middleware/`)
is stable and correct. Only the platform layer needs replacing:

- `storage_wrapper.c` → NVS (done)
- `network_wrapper.c` → `esp_tls` (replaces direct mbedtls 2.x usage)

This gives a clean ESP-IDF component with no dependency on any specific mbedtls
version, fully compatible with ESP-IDF 5.x and 6.x.
