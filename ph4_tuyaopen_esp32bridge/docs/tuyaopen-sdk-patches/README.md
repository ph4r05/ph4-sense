# TuyaOpen SDK patches

`ph4_tuyaopen_esp32bridge/tuyaopen/` is a plain `git clone` of
https://github.com/tuya/tuyaopen (gitignored — never committed, see repo
root `.gitignore`). Because of that, any local edit inside it is lost on a
fresh clone. This directory records those edits and how to reapply them.

## `MALLOC_CAP_SIMD` undeclared in `espressif/esp-dl` for ESP32-C6

**Files patched** (both inside the `espressif__esp-dl` managed component,
fetched by the nested `TuyaOpen-esp32` platform repo at
`tuyaopen/platform/ESP32/tuya_open_sdk/managed_components/espressif__esp-dl/`):

- `vision/image/dl_image_process.cpp`
- `dl/tool/src/dl_tool.cpp`

**Problem:** `tuyaos_adapter` (TuyaOpen's own ESP32 platform adapter code)
unconditionally `REQUIRES`s the `esp-sr` component — even for apps that
don't use voice recognition, like this switch/relay bridge — so `esp-sr`
can't simply be removed from `main/idf_component.yml` (tried that first;
CMake then fails with `Failed to resolve component 'esp-sr' required by
component 'tuyaos_adapter': unknown name`). `esp-sr` in turn pulls in
`espressif/esp-dl ~3.3.12` (on-device vision/ML), and esp-dl's
`heap_caps_malloc(..., MALLOC_CAP_DEFAULT | MALLOC_CAP_SIMD)` /
`heap_caps_aligned_alloc(..., caps | MALLOC_CAP_SIMD)` calls reference
`MALLOC_CAP_SIMD` — a capability flag not defined in
`esp-idf/components/heap/include/esp_heap_caps.h` for the ESP-IDF version
pinned to this platform commit (`5a120d0b99c99e6b01f4e6796cbc0cad3501ee89`
as of 2026-09-27), even though esp-dl 3.3.12 lists `esp32c6` as supported.
Reproduces on a clean `tos.py build` for ESP32-C6 before any of our own app
code is touched — it's an upstream esp-dl/ESP-IDF version-skew bug, unrelated
to this bridge (which has no use for vision or speech features at all).

```
error: 'MALLOC_CAP_SIMD' was not declared in this scope; did you mean 'MALLOC_CAP_TCM'?
```

**Fix:** add a `#ifndef MALLOC_CAP_SIMD / #define MALLOC_CAP_SIMD 0 / #endif`
guard before first use in both files. `MALLOC_CAP_SIMD` is only ever OR'd
into an allocation-hint bitmask (`caps | MALLOC_CAP_SIMD`), so falling back
to `0` (no-op bit) is safe — worst case, allocations skip a SIMD-alignment
optimization this device's firmware never exercises anyway.

**Reapply after a fresh `tuyaopen` clone:**

```bash
bash ph4_tuyaopen_esp32bridge/docs/tuyaopen-sdk-patches/fix-esp-dl-malloc-cap-simd.sh
```
