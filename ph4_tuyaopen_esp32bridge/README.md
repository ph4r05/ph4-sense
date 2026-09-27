# ph4_tuyaopen_esp32bridge

ESP32 bridge firmware using **TuyaOpen SDK** for SmartLife app pairing.

Unlike the TuyaLink variant (`ph4_tuya_esp32bridge`), this version uses the standard
Tuya WiFi device protocol — the device pairs interactively with the SmartLife app
and is automatically bound to the user's home account.

> See [`HISTORY.md`](./HISTORY.md) for why this is the second attempt: the
> TuyaLink/`tuya-iot-core-sdk` approach in `ph4_tuya_esp32bridge` got a working
> MQTT client built, but had no real SmartLife pairing path and hit
> "Connection not authorized" (error 11) with hardware-style products.

## Key differences from TuyaLink variant

| Feature | TuyaLink (old) | TuyaOpen (this) |
|---|---|---|
| Pairing | Pre-provisioned credentials | SmartLife app (AP/EZ mode) |
| Binding | Manual API calls / quota issues | Automatic during pairing |
| DP format | Named properties (`switch_1`) | Numeric DP IDs (1, 2, ...) |
| Product type | TuyaLink product | WiFi custom product |
| SDK | tuya-iot-core-sdk | tuyaopen |

## Setup

### 1. Clone TuyaOpen SDK

```bash
cd ph4_tuyaopen_esp32bridge
git clone --recurse-submodules https://github.com/tuya/tuyaopen.git
```

### 2. Tuya Product

Already created: **Ph4BridgeSwitch** (PID `g8lfcppln9qlvug2`), Custom Solution →
WiFi (not TuyaLink), Central Europe data center. See [DP Layout](#dp-layout)
below for the actual DP IDs assigned — they are **not** a clean 1-32 range,
so don't recreate this from a fresh linear DP plan; use dp_map.h as source of
truth.

Free development licenses (UUID + AUTH_KEY) were obtained from **Device →
Authorization**. Two are available — one is in active use, the second is a
spare for a second unit.

### 3. Configure

Real credentials go in `src/tuya_config.local.h` (gitignored, **never
committed** — see [`tuya_config.h`](./src/tuya_config.h)), not in
`tuya_config.h` itself. Copy the template if it doesn't already exist:

```bash
cp src/tuya_config.local.h.example src/tuya_config.local.h
# edit src/tuya_config.local.h with the real PID/UUID/AUTHKEY
```

Edit Kconfig (or `sdkconfig`) for HA MQTT broker settings.

### 4. Build

This is a standalone TuyaOpen app (not an `idf.py`/ESP-IDF component like
`ph4_tuya_esp32bridge`) — `tos.py` owns the build, see `CMakeLists.txt`.
Run everything from `ph4_tuyaopen_esp32bridge/` (not from inside `tuyaopen/`):

```bash
source tuyaopen/export.sh          # bootstraps uv/python/deps into tuyaopen/.venv (first run only)
tos.py config choice -c ESP32-C6.config   # select the board once; re-run if you switch chips
tos.py build -v
```

The device is an **ESP32-C6**. `tos.py build` may prompt to update the
platform submodule to a pinned commit on first run — answer `y`. First build
also downloads the ESP-IDF toolchain for the target chip (multi-GB, one-time).

If this is a fresh `tuyaopen` clone, also reapply the local SDK patch (an
upstream `esp-dl` incompatibility unrelated to this app — see
[`HISTORY.md`](./HISTORY.md) and `docs/tuyaopen-sdk-patches/`) after the
first build attempt fetches `espressif__esp-dl`:

```bash
bash docs/tuyaopen-sdk-patches/fix-esp-dl-malloc-cap-simd.sh
tos.py build -v   # rerun
```

Output: `dist/ph4_tuyaopen_esp32bridge_<version>/ph4_tuyaopen_esp32bridge_QIO_<version>.bin`

### 5. Pair with SmartLife

1. Flash the firmware: `tos.py flash -p /dev/ttyUSB0` (macOS: `/dev/cu.usbserial-XXXX`)
   — then `tos.py monitor -p /dev/ttyUSB0` to watch boot logs
2. On first boot, device enters **AP pairing mode** (LED blinks fast)
3. Open SmartLife app → Add Device → Auto-scan or Manual → select your product
4. Follow SmartLife prompts to provide WiFi credentials
5. Device activates and appears in your SmartLife home

### DP Layout

Real DP IDs from the Tuya console — **not** contiguous, see `src/dp_map.h` and
[`HISTORY.md`](./HISTORY.md) for why. Firmware looks these up per-channel,
it does not compute them from a base offset.

| Channel | Switch DP (HA → Tuya) | Relay/socket DP (Tuya → HA) |
|---|---|---|
| 1 | 1 | 121 |
| 2 | 2 | 122 |
| 3 | 3 | 123 |
| 4 | 4 | 124 |
| 5 | 5 | 125 |
| 6 | 6 | 126 |
| 7 | 101 | 111 |
| 8 | 102 | 112 |
| 9 | 103 | 113 |
| 10 | 104 | 114 |
| 11 | 105 | 115 |
| 12 | 106 | 116 |
| 13 | 107 | 117 |
| 14 | 108 | 118 |
| 15 | 109 | 119 |
| 16 | 110 | 120 |

All switch and relay DPs are boolean, R/W, "Send and Report". Channels 1-6's
relay/socket DPs (121-126) are identified `relay_trigger_1`..`relay_trigger_6`
in the console, not `relay_status_1..6` — the console wouldn't release those
identifiers from the deleted DP 29-34 ("Restart Status" enum function), so a
different name was used. The identifier string doesn't matter to the
firmware, only the numeric DP ID does.
