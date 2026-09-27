# Project History

This bridge exists to let an ESP32 device present up to 16 switch channels and
16 relay/socket channels to both **Tuya/SmartLife** and **Home Assistant**
(bidirectionally, over MQTT on the HA side). Two different Tuya SDK approaches
have been tried. This file records both, so the reasoning doesn't have to be
rediscovered from scratch if a third approach is ever needed.

There is no separate "old Claude transcript" for this work beyond what's in
git history and in `ph4_tuya_esp32bridge/docs/` — that directory already
contains the investigation notes from the first attempt, written while it was
being built. This file summarizes that record and adds the reasoning for the
pivot to TuyaOpen.

## Attempt 1 — `ph4_tuya_esp32bridge` (TuyaLink + `tuya-iot-core-sdk`), Mar 2026

**Approach:** Embed Tuya's portable POSIX C SDK (`tuya-iot-core-sdk`) as a
regular ESP-IDF component inside a normal `idf.py` project, alongside a WiFi
manager, an HA MQTT client, and a DP↔MQTT bridge module. Talk to Tuya cloud
using the **TuyaLink** protocol with **pre-provisioned device credentials**
(Device ID + Device Secret registered manually in the Tuya console), no
SmartLife pairing flow.

Two other SDKs were considered and rejected before settling on this one — see
`ph4_tuya_esp32bridge/docs/sdk-selection/README.md` for the full comparison:

- `tuya-connect-kit-for-mqtt-embedded-c` — archived/deprecated by Tuya.
- `tuya-connect-kit-for-esp-idf` — doesn't actually exist as a repo.
- **TuyaOpen** (`tuya/tuyaopen`) — rejected *at the time* as "the right SDK for
  the wrong shape of project": it owns the whole build (`tos.py`, not
  `idf.py`) and the whole application (your code runs as a TuyaOpen "app",
  not the other way around), and pulls in AI/LVGL/audio/BLE machinery far
  beyond what a Tuya MQTT client needs. See more below — this rejection is
  exactly what got revisited for attempt 2.

**Porting work done** (full detail + a `restore.sh` reproduction script in
`ph4_tuya_esp32bridge/docs/option-a-posix-sdk/README.md`):

| Problem | Fix |
|---|---|
| SDK's `CMakeLists.txt` requires CMake <3.5, incompatible with CMake 4.x | Replaced with an `idf_component_register()` wrapper |
| Bundled `libraries/mbedtls/` clashes with openthread's copy | Removed at configure time |
| POSIX storage wrapper uses `fopen`/`fwrite` (no filesystem on ESP32) | New NVS-backed `platform/esp32/storage_wrapper.c` |
| `mbedtls/certs.h` removed in mbedtls 3.x | Empty shim header |
| POSIX network wrapper pokes mbedtls 2.x struct internals, broken on mbedtls 3.x/ESP-IDF 5+ | New `platform/esp32/network_wrapper.c` using `esp_tls` |
| `mbedtls/cipher.h` removed entirely in mbedtls 4.x / ESP-IDF 6.x (moved to PSA Crypto) | New `platform/esp32/cipher_wrapper.c` using PSA AEAD |
| coreJSON uses `true` as an enum constant, illegal in C23 | Force `-std=c11` for that one file |
| `__FILENAME__` macro collision between SDK's `log.h` and ESP-IDF's `assert.h` | `#ifndef` guard |

This got the SDK compiling and connecting as a clean ESP-IDF component with a
stable public API (`tuya_cloud_init/start/report_bool/...`) that the rest of
the firmware (`dp_bridge.c`, `main.c`) talked to without caring which SDK was
underneath.

**Why it was abandoned:** the porting work succeeded, but the *protocol
model* was wrong for a device meant to be paired by a normal user:

- TuyaLink credentials are pre-provisioned per-device from the Tuya console
  ("Device access authorization code") — there is **no SmartLife "Add
  Device" pairing flow**. Every physical unit needs its credentials generated
  and flashed by hand.
- Hardware-module product types (the ones SmartLife actually knows how to
  pair) reject TuyaLink-style credentials outright — the broker returns
  **error 11 "Connection not authorized"**. Virtual devices don't help either;
  they don't authenticate as physical hardware.
- Binding a device to a user's home therefore requires manual Tuya API calls
  instead of the app-driven flow, which ran into **binding quota limits**.

In short: technically working MQTT client, but no viable path to "buy/flash a
device, open SmartLife, add it" — which is the actual requirement.

## Attempt 2 — `ph4_tuyaopen_esp32bridge` (TuyaOpen SDK), May 2026 — current

**Approach:** Use Tuya's own **TuyaOpen** framework and let it own the
project, instead of fighting to embed it as one `idf.py` component among
others. The app (`src/app_main.c`, adapted from TuyaOpen's
`apps/tuya_cloud/switch_demo`) is built via `tos build`, and this directory is
either symlinked into `tuyaopen/apps/` or built with `--project` pointing back
here. WiFi credentials and Tuya binding both happen through the standard
**SmartLife AP/EZ pairing flow**, and the product is a normal **WiFi custom
product** (numeric DPs 1-32, not named TuyaLink properties) instead of a
TuyaLink product.

This directly fixes what killed attempt 1: pairing and binding are automatic
and app-driven, and the device authenticates as a real hardware-module-style
product, so error 11 doesn't apply.

**Why the earlier rejection of TuyaOpen no longer applies:** attempt 1's
`docs/sdk-selection/README.md` rejected TuyaOpen because it doesn't fit inside
an existing multi-component `idf.py` project. That constraint doesn't exist
here — this is a standalone TuyaOpen app from the start, so "TuyaOpen owns the
build and the app" is no longer a downside, it's just how the SDK works. The
tradeoff accepted going in: TuyaOpen pulls in far more than a bare MQTT
client (its own SDK layer, `tal_*`/`tkl_*` abstractions, its own build
tooling), so `tuya_cloud.c` / `dp_bridge.c` were rewritten against the
TuyaOpen API rather than ported from attempt 1's SDK-agnostic interface.

**Status as of this writing:** initial scaffold committed (single commit,
2026-05-02) — `app_main.c`, `config.c`, `tuya_cloud.c`, `dp_bridge.c`,
`ha_mqtt.c`. Since then (2026-09-27): real credentials obtained and stored in
gitignored `src/tuya_config.local.h` (not committed — `tuya_config.h` keeps
placeholders); the full 32-DP schema is now correctly assigned in the console
and matches `src/dp_map.h`; **first successful `tos.py build` for ESP32-C6**
(see "First successful build" below) — flashing/pairing on real hardware is
the next step, not yet done.

## DP schema mismatch discovered 2026-09-27

Real credentials and the actual product DP export (`Ph4BridgeSwitch`, PID
`g8lfcppln9qlvug2`) surfaced that the DP layout isn't the clean 1-32 range
`README.md` originally assumed:

- Switch channels: DP 1-6 (channels 1-6), DP 101-110 (channels 7-16) — both
  correct, boolean, R/W.
- Relay/socket channels 7-16: DP 111-120 — correct, boolean.
- Relay/socket channels 1-6: **no correct DP exists yet.** DP 29-34 has the
  `relay_status_1`..`relay_status_6` identifiers, but it's Tuya's
  auto-generated "Restart Status" standard function (enum: off/on/memory —
  power-on behavior), not a custom boolean trigger DP. It got those
  identifiers by coincidence/mistake when the product was created, not by
  design.

**Decision:** leave DP 29-34 alone (it's a legitimate standard function, just
not the one we want) and add 6 **new** custom boolean DPs for the real
relay/socket trigger behavior on channels 1-6, mirroring 111-120.

Deleting DP 29-34 from the product did **not** release the
`relay_status_1..6` identifiers — the Tuya console still reported them as
taken when trying to recreate the DPs under those names (apparently once an
identifier has been bound to a standard function on a product, the console
won't let a custom DP reuse it, even after that function is removed).
Worked around by using different identifiers instead:
`relay_trigger_1`..`relay_trigger_6`, at DP **121-126** (bool, R/W, "Send and
Report") — done 2026-09-27. The identifier string is purely cosmetic on the
Tuya side; the firmware only ever addresses DPs by numeric ID, so this has
no code impact.

The firmware (`dp_bridge.c`, `tuya_cloud.c`) was changed to look up each
channel's DP ID from an explicit table (`src/dp_map.h`) instead of computing
it from a linear base+offset, since the real layout was never going to be
contiguous. While in `tuya_cloud.c`, a fully dead code path was also removed:
`iot_event_handler` duplicated the DP/event dispatch that `app_main.c`'s
`event_handler` already does and was never registered with `tuya_iot_init` —
`app_main.c` is the one actually wired up.

Real credentials (PID, device UUID/AuthKey) are kept out of git in
`src/tuya_config.local.h` (gitignored), following this repo's no-hardcoded-
credentials rule — `src/tuya_config.h` keeps placeholder values and includes
the local file when present.

## First successful build, 2026-09-27

The initial scaffold (attempt 2, above) had never actually been built. Doing
so surfaced that it mixed two incompatible APIs: `app_main.c` correctly used
TuyaOpen's `tal_*` abstraction layer, but `config.c`, `dp_bridge.c`,
`tuya_cloud.c`, and `ha_mqtt.c` were written against raw ESP-IDF APIs
(`esp_log.h`/`ESP_LOG*`, `esp_err_t`, `nvs_flash.h`, `esp_timer.h`,
FreeRTOS headers, `esp_mqtt_client`) — none of which are reachable from app
code in a TuyaOpen build (this app only sees TuyaOpen's own headers, not raw
ESP-IDF ones), exactly the incompatibility attempt 1's rejection of TuyaOpen
(see "Attempt 2" above) predicted. This wasn't a design tradeoff to weigh —
it just needed porting to compile at all:

- **Logging:** `ESP_LOGI/W/E/D` → `PR_INFO/WARN/ERR/DEBUG` (`tal_log.h`, no
  per-call tag).
- **Error type:** `esp_err_t`/`ESP_OK` → `OPERATE_RET`/`OPRT_OK` (and related
  `OPRT_*` codes from `tuya_error_code.h`) across every function signature
  in `config.h`, `dp_bridge.h`, `tuya_cloud.h`, `ha_mqtt.h`.
- **Config storage:** NVS (`nvs_open`/`nvs_get_str`/...) → `tal_kv_set/get`,
  storing the whole config as one JSON blob under a single key instead of
  per-field NVS entries (reusing the existing `config_to_json`/
  `config_apply_json` round-trip).
- **Per-socket auto-reset timer:** `esp_timer_create/start_once/stop` →
  `tal_sw_timer_create/start/stop` (`TAL_TIMER_ONCE`).
- **Reboot:** `esp_restart()` → `tal_system_reset()`.
- **HA MQTT client:** ESP-IDF's `esp_mqtt_client` isn't reachable at all, so
  `ha_mqtt.c` was rewritten against TuyaOpen's own portable
  `mqtt_client_interface.h` (`src/libmqtt/`) — the same client TuyaOpen uses
  internally for its Tuya-cloud MQTT connection. Since that connection is a
  second, independent broker (the local HA instance, not Tuya cloud), it
  needed its own connect/retry/yield loop on a dedicated `tal_thread`, unlike
  the Tuya-cloud link which is pumped by `tuya_iot_yield()` in the existing
  main loop. Known regression: this interface has no last-will/testament
  option, so the broker won't auto-publish "offline" on an unclean
  disconnect (only an explicit `ha_mqtt_stop()` does) — acceptable for now,
  revisit if it matters in practice.

**Unrelated upstream build failure hit along the way:** TuyaOpen's ESP32
platform bundles `espressif/esp-sr` (voice recognition) as a hard dependency
for every app via `tuyaos_adapter`'s component requirements — not something
this app opted into or can opt out of by editing `main/idf_component.yml`
(tried; CMake then fails to resolve the `esp-sr` component required by
`tuyaos_adapter`). `esp-sr` pulls in `espressif/esp-dl ~3.3.12`, which
references `MALLOC_CAP_SIMD`, a flag missing from the ESP-IDF version pinned
to this platform commit for `esp32c6`. Patched with a `#ifndef` fallback
(`MALLOC_CAP_SIMD` → `0`, a no-op allocation hint) in two esp-dl source
files. Full writeup + a script to reapply it after a fresh `tuyaopen` clone:
`docs/tuyaopen-sdk-patches/`.

Result: `tos.py build` for ESP32-C6 completes —
`dist/ph4_tuyaopen_esp32bridge_1.0.0/ph4_tuyaopen_esp32bridge_QIO_1.0.0.bin`.

## First hardware flash + boot, 2026-09-27

The physical board has two USB-C connectors: **CH343** (an external
USB-UART bridge, WCH vendor ID `0x1A86`, shows up on macOS as
`/dev/cu.usbmodemXXXX` — not `wchusbserial*`, since modern macOS's built-in
CDC-ACM driver handles it directly, no WCH kernel extension needed) and the
**ESP32-C6's native USB** (its built-in USB-Serial-JTAG peripheral,
identifies via `ioreg` as `"USB Vendor Name" = "Espressif"` /
`"USB Product Name" = "USB JTAG_serial debug unit"`).

**Flashing:** TuyaOpen's own `tos.py flash` (wrapping Tuya's `tyutool_cli`)
could not connect over the native USB port — its auto-reset-into-bootloader
handshake didn't work there (`could not connect to ESP32C6`), even after a
manual BOOT+RESET button sequence. Standard **`esptool.py`** (already on
PATH via pyenv, separate from TuyaOpen's bundled `tyutool_cli`) connected
and flashed over the same native USB port immediately, no manual
BOOT/RESET needed — its auto-reset sequence for USB-Serial-JTAG is simply
more robust than `tyutool_cli`'s. Used directly:
```bash
esptool.py --chip esp32c6 --port /dev/cu.usbmodemXXXX --baud 460800 \
  --before default_reset --after hard_reset write_flash -z \
  --flash_mode dio --flash_size 8MB --flash_freq 40m \
  0x0 dist/ph4_tuyaopen_esp32bridge_1.0.0/ph4_tuyaopen_esp32bridge_QIO_1.0.0.bin
```
(this also surfaced the flash-size mismatch below — the original 16MB-sized
image wouldn't fit until that was fixed).

**Flash-size mismatch:** `esptool.py flash_id` reported the chip's actual
flash as 8MB, but the only ESP32-C6 board config TuyaOpen ships hardcodes
16MB (see `docs/tuyaopen-sdk-patches/` for the fix — three coordinated
patches: board Kconfig, a per-chip sdkconfig seed file, and the partition
table). Merged image dropped from 15.5MB (didn't fit) to 7.1MB after the
fix.

**Console output goes out CH343, not native USB.** The default console
config is `CONFIG_ESP_CONSOLE_UART_DEFAULT=y` (physical UART0 pins, wired
to CH343) with USB-Serial-JTAG only as a secondary/early-boot console — so
`tos.py monitor` / any serial terminal needs the **CH343** port to see the
running app's log output (`PR_INFO`/`PR_WARN`/etc.), even though flashing
works fine over the native USB port.

**First boot result (via `esptool.py` flash + serial monitor over CH343):**
clean boot, no crashes/watchdog resets. All ported logging came through
correctly (confirms the TAL API port compiles *and* runs correctly, not
just compiles) — the DP mapping table printed exactly as designed (switch
ch1-6 → DP 1-6, ch7-16 → DP 101-110; socket ch1-6 → DP 121-126, ch7-16 →
DP 111-120), `tal_kv` (LittleFS) read/write worked (expected "lfs key not
found" on a blank device), and it read the hardcoded UUID/AuthKey from
`tuya_config.local.h` since no prior activation was stored. Most
importantly, it correctly entered **pairing mode**:
```
Device entering pairing mode — use SmartLife app to add
```
broadcasting a WiFi AP (`SmartLife-FE37`, DHCP on 192.168.4.1) and BLE
advertising simultaneously (dual-mode pairing), with the `ap_netcfg`/`tuya
ap using tls + psk` secure pairing listener up on port 6668. A `tuya>` CLI
prompt (the `switch`/`reset`/`mem` commands from `app_main.c`) also came up
cleanly.

Not yet done: actually completing SmartLife pairing (device needs to be on
the same network as the phone doing the pairing — deferred until on home
WiFi), and verifying HA MQTT bridging end-to-end (still blocked on the
missing runtime config mechanism noted in the "what to test" discussion —
no Kconfig defaults or CLI setter for `mqtt_host` yet).

## Where to look for more detail

- `ph4_tuya_esp32bridge/docs/sdk-selection/README.md` — full SDK comparison
  (4 options) from attempt 1.
- `ph4_tuya_esp32bridge/docs/option-a-posix-sdk/README.md` — every upstream
  patch applied to `tuya-iot-core-sdk`, plus `restore.sh` to reproduce them
  against a clean checkout of the SDK.
- `ph4_tuya_esp32bridge/README.md` — the TuyaLink attempt's full setup/build/
  provisioning docs, including the error-11 warning.
- `git log -- ph4_tuya_esp32bridge` — commit-by-commit progression of attempt 1.
- `docs/tuyaopen-sdk-patches/` — local patches to the gitignored `tuyaopen/`
  clone (currently: the `MALLOC_CAP_SIMD` esp-dl fix) and scripts to reapply
  them after a fresh clone.
- `src/dp_map.h` — the real (non-contiguous) per-channel DP ID tables.
