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

## ESP32-C6 board config hardcodes 16MB flash; our chip is 8MB

**Files patched:**

- `tuyaopen/boards/ESP32/ESP32-C6/Kconfig` (top-level `tuyaopen` repo)
- `tuyaopen/platform/ESP32/tuya_open_sdk/sdkconfig_esp32c6` (nested
  `TuyaOpen-esp32` platform repo)
- `tuyaopen/platform/ESP32/tuya_open_sdk/partitions.csv` (gitignored inside
  that nested repo — meant to be hand-set per board, not tracked)

**Problem:** the only generic `ESP32-C6` board config TuyaOpen ships
hardcodes `select PLATFORM_FLASHSIZE_16M` in its Kconfig — there's no 8MB
variant (only `WAVESHARE_ESP32C6_DEV_KIT_N16`, also 16MB, exists as an
alternative). Our actual hardware has an **8MB** flash chip (confirmed via
`esptool.py flash_id`: `Detected flash size: 8MB`). Building with the
16MB-sized default `partitions.csv` produces a firmware image where the
`model` (voice-model) partition sits at offset `0xED0000` (~14.8MB) — past
the end of an 8MB chip entirely — so the merged flash image comes out to
15.5MB and physically cannot be written:

```
A fatal error occurred: File ...QIO_1.0.0.bin (length 15532036) at offset 0
will not fit in 8388608 bytes of flash.
```

**Fix:** three coordinated changes, since flash size is seeded in two
different places before Kconfig ever runs, and the partition table is a
separate, unrelated hand-maintained file:

1. `boards/ESP32/ESP32-C6/Kconfig`: `select PLATFORM_FLASHSIZE_16M` →
   `select PLATFORM_FLASHSIZE_8M` (this alone isn't sufficient — see next).
2. `tuya_open_sdk/sdkconfig_esp32c6`: this is a per-chip seed file that
   `build_setup.py`'s "set-target" step requires and copies in before
   Kconfig merging runs; its hardcoded `CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y`
   would otherwise win regardless of the board Kconfig default. Flipped to
   `8MB` to match.
3. `tuya_open_sdk/partitions.csv`: not derived from the flash-size Kconfig
   at all (checked `build_setup.py` — no such logic exists). TuyaOpen ships
   ready-made `partitions_4M.csv`/`_8M.csv`/`_16M.csv`/`_32M.csv` reference
   layouts; copied `partitions_8M.csv` over the active `partitions.csv`
   (whose 8MB layout fits exactly: last partition ends at `0x800000` = 8MB).

After patching, the stale 16MB `sdkconfig` (and the `.build`/`build` dirs
seeded from it) must be cleared and regenerated — see the script below.

**Reapply after a fresh `tuyaopen` clone:**

```bash
bash ph4_tuyaopen_esp32bridge/docs/tuyaopen-sdk-patches/fix-esp32c6-8mb-flash.sh
rm -f ph4_tuyaopen_esp32bridge/tuyaopen/platform/ESP32/tuya_open_sdk/sdkconfig
cd ph4_tuyaopen_esp32bridge && source tuyaopen/export.sh
tos.py config choice -c ESP32-C6.config
tos.py build -v
```
