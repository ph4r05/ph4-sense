# Option A: tuya-iot-core-sdk (POSIX/mbedtls approach) — ABANDONED

## Why it was attempted

The `tuya-iot-core-sdk` (https://github.com/tuya/tuya-iot-core-sdk) is Tuya's
portable C SDK, designed to run on Linux/POSIX systems. It uses a platform
abstraction layer (PAL) so theoretically it can run on any OS by implementing
a handful of wrapper functions.

The approach was to compile it as an ESP-IDF component by:
1. Overriding the upstream `CMakeLists.txt` with an IDF `idf_component_register()` definition
2. Replacing the POSIX filesystem storage with an NVS-backed wrapper
3. Using ESP-IDF's built-in mbedtls instead of the SDK's bundled copy
4. Using the POSIX network_wrapper.c as-is (lwIP provides POSIX sockets on ESP32)

## Why it was abandoned

The `tuya-iot-core-sdk` was written for **mbedtls 2.x**. ESP-IDF 5.0+ uses
**mbedtls 3.x**, which made breaking API changes:

| Issue | Details |
|-------|---------|
| `mbedtls_ssl_context.state` removed | Struct members made private/opaque in mbedtls 3.0 |
| `mbedtls_ssl_conf_rng()` changed | PSA Crypto integration changed RNG API in 3.6+ |
| `mbedtls/certs.h` removed | Removed in mbedtls 3.0 |
| `coreJSON true` enum conflict | coreJSON uses `true` as an enum constant, illegal in C23 |
| `__FILENAME__` macro redefined | Conflicts with ESP-IDF's assert.h |

**There is no ESP-IDF version that supports both ESP32-C6 (requires ESP-IDF 5.0+)
and mbedtls 2.x (requires ESP-IDF 4.x).** Downgrading is not an option.

## What was built before abandoning

### New files created in the submodule

```
firmware/components/tuya-iot-core-sdk/
├── CMakeLists.txt                    ← REPLACED: idf_component_register() wrapper
├── platform/
│   └── esp32/
│       ├── storage_wrapper.c         ← NEW: NVS-backed storage (replaces fopen/fwrite)
│       └── mbedtls/
│           └── certs.h               ← NEW: empty shim (mbedtls/certs.h removed in 3.x)
```

### Changes to the overridden CMakeLists.txt

- Calls `idf_component_register()` instead of CMake `project()`
- Sources: all of src/, coreJSON, coreMQTT, coreHTTP, middleware/, utils/
- Excludes: `mbedtls_sockets_wrapper.c` (duplicate symbols with ESP-IDF mbedtls),
            `platform/posix/storage_wrapper.c` (replaced), `libraries/mbedtls/`
- Adds `file(REMOVE_RECURSE libraries/mbedtls)` at configure time to prevent
  ESP-IDF's header scanner from flagging mbedtls/cipher.h as ambiguous
  (same header physically exists in openthread's bundled copy too)
- `REQUIRES mbedtls nvs_flash lwip esp_timer`

### The NVS storage wrapper (`platform/esp32/storage_wrapper.c`)

Implements `local_storage_set/get/del` from `storage_interface.h` using
`nvs_open/nvs_set_blob/nvs_get_blob` in the `tuya_kv` NVS namespace.
NVS keys are truncated to 15 chars (NVS limit). Tuya SDK's internal key
names (devid, seckey, localkey, etc.) are all short enough.

### firmware/main/tuya_cloud.c API surface (compatible with option B)

The public interface is clean and SDK-agnostic enough that it can be reimplemented
for a different Tuya SDK without changing any other files:

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

Only `tuya_cloud.c` needs to change between options. The public header
`tuya_cloud.h` and all callers (`dp_bridge.c`, `main.c`) remain unchanged.

## How to restore Option A from a clean checkout

Run `docs/option-a-posix-sdk/restore.sh` from the repository root.
