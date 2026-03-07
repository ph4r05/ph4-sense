# Option A: tuya-iot-core-sdk + ESP32 platform layer — CURRENT APPROACH

## Overview

The `tuya-iot-core-sdk` (https://github.com/tuya/tuya-iot-core-sdk) is Tuya's
portable C SDK, designed to run on Linux/POSIX systems. It uses a platform
abstraction layer (PAL) so it can run on any OS by implementing a handful of
wrapper functions.

The approach is to compile it as an ESP-IDF component by:
1. Overriding the upstream `CMakeLists.txt` with an IDF `idf_component_register()` definition
2. Replacing the POSIX filesystem storage with an NVS-backed wrapper
3. Replacing the POSIX/mbedtls network wrapper with an `esp_tls`-based wrapper
4. Using `platform/posix/system_wrapper.c` as-is (clock_gettime/nanosleep work on ESP-IDF)

## Problems encountered and how they were fixed

| Problem | Fix |
|---------|-----|
| `cmake_minimum_required(VERSION 3.2.0)` — CMake 4.x dropped <3.5 | Replaced entire CMakeLists.txt with `idf_component_register()` wrapper |
| `libraries/mbedtls/` bundled — conflicts with openthread's bundled mbedtls headers | `file(REMOVE_RECURSE)` at configure time |
| `platform/posix/storage_wrapper.c` uses `fopen/fwrite` — no filesystem on ESP32 | `platform/esp32/storage_wrapper.c` using NVS |
| `mbedtls/certs.h` not found — removed in mbedtls 3.x | Empty shim at `platform/esp32/mbedtls/certs.h` |
| `platform/posix/network_wrapper.c` uses mbedtls 2.x struct internals (`ssl.state`, `mbedtls_ssl_conf_rng`) — broken in mbedtls 3.x / ESP-IDF 5+ | `platform/esp32/network_wrapper.c` using `esp_tls` — no direct mbedtls API |
| `mbedtls/cipher.h` not found — entire cipher API removed from public API in mbedtls 4.x / ESP-IDF 6.x (moved to PSA Crypto) | `platform/esp32/cipher_wrapper.h` + `platform/esp32/cipher_wrapper.c` using PSA AEAD API |
| coreJSON uses `true` as enum constant — illegal in C23 | `set_source_files_properties` with `-std=c11` for `core_json.c` |
| `__FILENAME__` macro redefined — defined in both `utils/log.h` and ESP-IDF's `assert.h` | `#ifndef __FILENAME__` guard added to `utils/log.h` |

## Files changed / created

```
firmware/components/tuya-iot-core-sdk/
├── CMakeLists.txt                      ← REPLACED: idf_component_register() wrapper
├── utils/
│   └── log.h                           ← PATCHED: #ifndef __FILENAME__ guard
└── platform/
    └── esp32/
        ├── network_wrapper.c           ← NEW: TLS via esp_tls (replaces posix/network_wrapper.c)
        ├── cipher_wrapper.c            ← NEW: AES-GCM via PSA AEAD (replaces src/cipher_wrapper.c)
        ├── cipher_wrapper.h            ← NEW: shadows include/cipher_wrapper.h (no mbedtls/cipher.h)
        ├── storage_wrapper.c           ← NEW: NVS-backed storage (replaces fopen/fwrite)
        └── mbedtls/
            └── certs.h                 ← NEW: empty shim (mbedtls/certs.h removed in 3.x)
```

## CMakeLists.txt highlights

- Calls `idf_component_register()` instead of CMake `project()`
- Sources: all of src/, coreJSON, coreMQTT, coreHTTP, middleware/, utils/
- Excludes: `mbedtls_sockets_wrapper.c`, `platform/posix/network_wrapper.c`,
            `platform/posix/storage_wrapper.c`, `libraries/mbedtls/`
- Adds `file(REMOVE_RECURSE libraries/mbedtls)` at configure time
- `REQUIRES esp_tls nvs_flash lwip esp_timer`
- `set_source_files_properties(core_json.c PROPERTIES COMPILE_FLAGS "-std=c11")`

## ESP32 network wrapper (`platform/esp32/network_wrapper.c`)

Implements the same `NetworkContext_t` interface as the POSIX version but uses
`esp_tls` instead of direct mbedtls API calls:

- `network_tls_init` — allocates `tls_context_t`, sets function pointers
- `network_tls_connect` — calls `esp_tls_init` + `esp_tls_conn_new_sync`
- `network_tls_read/write` — call `esp_tls_conn_read/write`; map WANT_READ/TIMEOUT → 0
- `network_tls_disconnect/destroy` — call `esp_tls_conn_destroy`; free context

No mbedtls headers included. Compatible with ESP-IDF 5.x and 6.x regardless
of underlying mbedtls version.

## NVS storage wrapper (`platform/esp32/storage_wrapper.c`)

Implements `local_storage_set/get/del` from `storage_interface.h` using
`nvs_open/nvs_set_blob/nvs_get_blob` in the `tuya_kv` NVS namespace.
NVS keys are truncated to 15 chars (NVS limit). Tuya SDK's internal key
names (devid, seckey, localkey, etc.) are all within this limit.

## `firmware/main/tuya_cloud.c` API surface

The public interface is SDK-agnostic. Only `tuya_cloud.c` needs to change if
the Tuya SDK is ever swapped. The header `tuya_cloud.h` and all callers
(`dp_bridge.c`, `main.c`) remain unchanged.

```c
esp_err_t tuya_cloud_init(cfg, dp_cb, state_cb, user_data);
esp_err_t tuya_cloud_start(void);
esp_err_t tuya_cloud_report_bool(uint8_t dp_id, bool value);
esp_err_t tuya_cloud_report_multi(dp_ids[], values[], count);
esp_err_t tuya_cloud_report_all(void);
tuya_state_t tuya_cloud_get_state(void);
void tuya_cloud_factory_reset(void);
void tuya_cloud_stop(void);
```

## How to restore from a clean checkout

Run `docs/option-a-posix-sdk/restore.sh` from the repository root.
