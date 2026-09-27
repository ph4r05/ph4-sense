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

```bash
cd tuyaopen
source export.sh
tos build --project ../  --platform esp32
```

This is a standalone TuyaOpen app (not an `idf.py`/ESP-IDF component like
`ph4_tuya_esp32bridge`) — `tos` owns the build, see `CMakeLists.txt`.

### 5. Pair with SmartLife

1. Flash the firmware
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
