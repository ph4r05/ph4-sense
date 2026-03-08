# ph4_tuya_esp32bridge

ESP32-C6 firmware that bridges **Tuya/SmartLife** with **Home Assistant via MQTT**.

The device connects to Tuya cloud using pre-provisioned credentials (UUID + AuthKey
from the Tuya IoT Platform developer console) and bridges bidirectionally:

- **Switch (HA → Tuya)**: HA publishes MQTT → ESP32 → Tuya cloud → SmartLife
- **Socket (Tuya → HA)**: SmartLife triggers → ESP32 receives → MQTT → HA

---

## DP Layout

| Channel type | Count | Tuya DP IDs      | MQTT topic                     |
|--------------|-------|------------------|-------------------------------|
| Switch       | 1–16  | DP 1 .. 16       | `{prefix}/switch/{n}/set` / `state` |
| Socket       | 1–16  | DP 101 .. 116    | `{prefix}/socket/{n}/set` / `state` |

Default prefix: `ph4/bridge`

### Switch (HA controls Tuya)

```
# HA turns switch 3 ON:
mosquitto_pub -t ph4/bridge/switch/3/set -m ON

# ESP32 responds with state echo:
ph4/bridge/switch/3/state  -> ON
# And Tuya DP 3 is set to true (SmartLife shows it)
```

### Socket (SmartLife controls HA)

```
# SmartLife user taps socket 5 in app:
# Tuya DP 105 -> true
# ESP32 publishes:
ph4/bridge/socket/5/state  -> ON
# HA automation triggers on this topic
# After socket_auto_reset_ms (500ms by default):
ph4/bridge/socket/5/state  -> OFF
# DP 105 -> false (ready to trigger again)
```

---

## Prerequisite: Tuya Developer Setup

> **Critical:** This firmware uses the **TuyaLink SDK**. You MUST create a **TuyaLink-type**
> product. Hardware module products (e.g. T1-U-HL, WB3S, etc.) use a different protocol and
> their credentials will be rejected by the TuyaLink MQTT broker with error 11
> "Connection not authorized". Virtual devices also do not work for physical hardware auth.

### 0. Account region / Data Center

When you first sign up on the Tuya IoT Platform the default data center is **China**.
If your devices are in Europe you must set the data center to **Central Europe** or
**Western Europe** during project/product creation. The MQTT broker host differs by region:

| Data Center | MQTT Host |
|---|---|
| China | `m1.tuyacn.com` |
| Central/Western Europe | `m1.tuyaeu.com` |
| Eastern/Western America | `m1.tuyaus.com` |
| India | `m1.tuyain.com` |

Set the correct host in `idf.py menuconfig` → **PH4 Tuya ESP32 Bridge** → **Tuya Cloud** →
**Tuya MQTT broker host**, or at runtime via the `tuya.host` JSON field.

### 1. Create a TuyaLink Product

1. Go to [iot.tuya.com](https://iot.tuya.com) (or your regional console) → **Cloud** → **Development**
2. Click **Create Product**
3. Choose any category (e.g. **Electrical** → **Scene Panel Switch**)
4. **On the protocol/solution screen**, select **TuyaLink** (NOT a hardware module like
   T1-U-HL, WB3S, etc.). This is critical — hardware module products use a different
   protocol and their credentials are incompatible with this firmware.
5. Set the data center to your region (e.g. **Central Europe Data Center**)
6. Name the product (e.g. "ph4-bridge") and confirm
7. Copy the **Product ID (PID)** shown in the product overview

### 2. Define Properties (TuyaLink data model)

The firmware uses the **TuyaLink protocol** which identifies properties by string name,
not integer DP ID. In your product's data model, add Boolean properties named **exactly**:

| Property name | Type    | Mode | Maps to                        |
|---------------|---------|------|-------------------------------|
| `dp_1` – `dp_16`   | Boolean | R/W  | Switch channels (HA→Tuya) |
| `dp_101` – `dp_116` | Boolean | R/W  | Socket channels (Tuya→HA)|

> **Why `dp_N`?** The firmware maps its internal DP ID (integer) to the property name
> `dp_{id}`. This convention must match what you define in the Tuya IoT Platform product schema.

### 3. Get Device Credentials (Device access authorization code)

This firmware requires **pre-provisioned credentials** — there is no SmartLife pairing flow.
Credentials come from **registering a device** under the product:

1. In the Tuya console → your product → **Device Management** → **Register Device**
2. Select **"Device access authorization code"** (this is the TuyaLink credential type)
3. Register one device → you receive:
   - **Device ID** (UUID, 20 chars, starts with `uuid...`)
   - **Device Secret** (AuthKey, 16 chars for TuyaLink virtual/registered devices)
4. Copy both values and set them in your config (see provisioning steps below)

> **Note:** The TuyaLink SDK uses only 16 chars for the HMAC key. TuyaLink device secrets
> are 16 chars. Hardware license AuthKeys (32 chars) are for a different SDK and
> will not authenticate correctly.

---

## Setup: ESP-IDF

**ESP-IDF** is Espressif's official C SDK and build system for ESP32 chips. It provides the compiler toolchain, FreeRTOS, WiFi/MQTT drivers, and `idf.py` — the command-line tool used to configure, build, and flash firmware. You need it installed before you can compile this project.

The **Tuya IoT Core SDK** is already included in this repo as a git submodule at `firmware/components/tuya-iot-core-sdk`. No manual steps needed — just `git submodule update --init --recursive` after cloning.

### 1. Install ESP-IDF v5.4+ (or v6.x)

This project builds against **ESP-IDF 5.4 or later** (tested with 6.1-dev). Earlier
versions (≤ 5.3) use a different mbedtls API and will not compile.

```bash
git clone --recursive https://github.com/espressif/esp-idf.git ~/esp/esp-idf
cd ~/esp/esp-idf
git checkout v5.4             # or: v6.0, v6.1, latest
./install.sh esp32c6          # installs compiler + tools for ESP32-C6
source export.sh              # activates idf.py in your shell (needed each session)
```

> Add `source ~/esp/esp-idf/export.sh` to your `~/.bashrc` or `~/.zshrc` to avoid running it manually each time.

### 2. Clone this repo with submodules

`tuya-iot-core-sdk` setup:

```bash
cd firmware
git submodule add https://github.com/tuya/tuya-iot-core-sdk \
    components/tuya-iot-core-sdk
```

Or just refresh submodule:
```bash
git submodule update --init --recursive
```

---

## Build & Flash

`idf.py` is the ESP-IDF build tool — think of it as `make` + `cmake` + flashing all in one.

```bash
cd firmware

# Fetch managed components (only needed once; downloads espressif/mqtt from the registry)
idf.py add-dependency mqtt
idf.py update-dependencies

# Tell IDF which chip you're targeting (only needed once per checkout)
idf.py set-target esp32c6

# Optional: open a menu to set compile-time defaults (WiFi SSID, Tuya PID, etc.)
# You can skip this if you plan to provision credentials at runtime via config JSON
idf.py menuconfig
# Navigate to: PH4 Tuya ESP32 Bridge

# Compile the firmware
idf.py build

# Flash to the device and open serial monitor
# On Linux the port is usually /dev/ttyUSB0 or /dev/ttyACM0
# On macOS it is usually /dev/cu.usbserial-XXXX
idf.py -p /dev/ttyUSB0 flash monitor
```

> **Note on `espressif/mqtt`**: In newer ESP-IDF releases (5.2+) the MQTT client was moved out of the built-in components into the IDF Component Manager registry. The `idf.py add-dependency mqtt` + `idf.py update-dependencies` steps download it once and save it under `managed_components/`. This is needed regardless of whether you install ESP-IDF yourself or use a pre-built toolchain image.

---

## First Boot / Provisioning

**Provisioning** means giving the device its initial configuration — WiFi credentials, MQTT broker address, and Tuya product ID — so it knows how to connect to everything. This only needs to be done once. After provisioning the device remembers its config in flash memory (NVS) and uses it on every subsequent boot.

There are two independent provisioning steps:
1. **WiFi/MQTT config** — tell the ESP32 which network and broker to use
2. **Tuya cloud pairing** — register the device with Tuya so SmartLife can see it

### Step 1 — Get WiFi credentials onto the device

#### Option A: Kconfig (compile-time, simplest for dev)

Set WiFi SSID/pass in `idf.py menuconfig` → **PH4 Tuya ESP32 Bridge** → **WiFi** before building.

#### Option B: AP mode HTTP (runtime, no rebuild needed)

1. Flash device with empty WiFi config (or erase NVS)
2. Device starts a provisioning AP: **ph4-bridge-XXXXXX** (open network, IP 192.168.4.1)
3. Connect your laptop to that AP
4. Copy and edit the config file:
   ```bash
   cp config/config-example.json config/config.json
   # edit config/config.json — fill in wifi, mqtt, tuya.pid at minimum
   ```
5. Upload config:
   ```bash
   cd tools
   pip install -r requirements.txt
   python provision.py ap --config ../config/config.json
   ```
6. Device reboots and connects to your home WiFi

### Step 2 — Push Tuya credentials to the device

The firmware requires a **Device ID** (UUID) and **Device Secret** (AuthKey) from the
Tuya IoT Platform. There is **no SmartLife pairing flow** — the device cannot be discovered
via SmartLife "Add Device". Credentials must be pushed via config.

#### Via provisioning AP (most common)

While the device is in AP mode (connected to `ph4-bridge-XXXXXX`):

```bash
curl -X POST http://192.168.4.1/config \
  -H 'Content-Type: application/json' \
  -d '{
    "tuya": {
      "pid":      "YOUR_PRODUCT_ID",
      "uuid":     "YOUR_DEVICE_ID",
      "auth_key": "YOUR_DEVICE_SECRET"
    }
  }'
```

The device saves the credentials and reboots. On boot it connects directly to Tuya cloud
(`m1.tuyacn.com:8883`) using mutual authentication.

#### Via Kconfig (compile-time)

Set `TUYA_UUID`, `TUYA_AUTH_KEY`, and `TUYA_PID` in `idf.py menuconfig` →
**PH4 Tuya ESP32 Bridge** → **Tuya Cloud** before building.

> **Note:** You do not need to release the product in the Tuya developer console.
> A product in draft/development state connects and functions normally.

---

## MQTT Topics Reference

### Input (subscribe from HA)

| Topic                        | Payload          | Description               |
|------------------------------|------------------|---------------------------|
| `ph4/bridge/switch/{n}/set`  | `ON` / `OFF`     | Control switch channel n  |
| `ph4/bridge/socket/{n}/set`  | `ON` / `OFF`     | Override socket channel n |
| `ph4/bridge/cmd`             | see below        | Control commands          |

### Output (published by ESP32)

| Topic                        | Payload          | Description               |
|------------------------------|------------------|---------------------------|
| `ph4/bridge/switch/{n}/state`| `ON` / `OFF`     | Current switch state      |
| `ph4/bridge/socket/{n}/state`| `ON` / `OFF`     | Socket trigger state      |
| `ph4/bridge/status`          | JSON             | Device status             |

### Control commands (`ph4/bridge/cmd`)

| Payload  | Effect                                                    |
|----------|-----------------------------------------------------------|
| `reset`  | Factory reset (clears Tuya pairing + config), reboots    |
| `reboot` | Reboot only                                              |
| `status` | Publish JSON status to `ph4/bridge/status`               |
| `sync`   | Re-report all DP states to Tuya cloud                    |

---

## Home Assistant Configuration

### Switch (HA side — 16 channels)

```yaml
# configuration.yaml
mqtt:
  switch:
    - name: "Bridge Switch 1"
      unique_id: ph4_bridge_switch_1
      command_topic: ph4/bridge/switch/1/set
      state_topic:   ph4/bridge/switch/1/state
      payload_on:  ON
      payload_off: OFF
      retain: false
    # ... repeat for 2-16
```

### Automations triggered by socket

```yaml
automation:
  - alias: "Tuya Socket 1 Triggered"
    trigger:
      - platform: mqtt
        topic: ph4/bridge/socket/1/state
        payload: "ON"
    action:
      - service: scene.turn_on
        target:
          entity_id: scene.evening_lights
```

---

## Factory Reset

- **Via MQTT**: `mosquitto_pub -t ph4/bridge/cmd -m reset`
- **Via button**: Hold BOOT (GPIO9) for 5 seconds during boot

Clears NVS config and Tuya activation data. Device re-enters provisioning mode.

---

## Storage: How Config is Persisted

ESP32 has **no EEPROM**. All persistent data is stored in the **flash chip** (the same physical chip that holds the firmware), accessed through **NVS (Non-Volatile Storage)** — an ESP-IDF key-value store with wear levelling and crash safety.

### Flash partition layout

| Partition  | Type | Size    | Contents                            |
|------------|------|---------|-------------------------------------|
| `nvs`      | data | 24 KB   | System NVS (WiFi stack, etc.)       |
| `factory`  | app  | 1.5 MB  | Main firmware                       |
| `ota_0`    | app  | 1.5 MB  | OTA update slot                     |
| `tuya_kv`  | data | 64 KB   | Tuya credentials (UUID, AuthKey)    |
| `app_cfg`  | data | 64 KB   | Device config (WiFi, MQTT, etc.)    |

### NVS namespaces used by this firmware

| Namespace  | Written by           | Contains                                              |
|------------|----------------------|-------------------------------------------------------|
| `app_cfg`  | `config.c`           | WiFi SSID/pass, MQTT host/port/creds, Tuya PID/UUID/AuthKey, channel config |
| `tuya_kv`  | Tuya SDK (via `platform/esp32/storage_wrapper.c`) | Internal SDK state (session data). Credentials are configured via `app_cfg`, not written here by the SDK activation flow. |

Factory reset erases `tuya_kv` to force the SDK to reinitialise its internal state.

### Flash wear

Flash cells survive ~100 000 write cycles per page. NVS spreads writes across the partition so in practice it lasts the lifetime of the device for config storage. The shadow DP state (switch/socket on/off) is kept only in RAM and never written to flash on every toggle — flash is only written when the device config changes.

---

## Project Structure

```
ph4_tuya_esp32bridge/
├── firmware/                     # ESP-IDF C project
│   ├── CMakeLists.txt
│   ├── sdkconfig.defaults        # ESP32-C6 defaults
│   ├── partitions.csv
│   ├── idf_component.yml         # managed dependency: espressif/mqtt
│   ├── components/
│   │   └── tuya-iot-core-sdk/   # git submodule
│   └── main/
│       ├── CMakeLists.txt
│       ├── Kconfig.projbuild     # menuconfig options
│       ├── main.c                # entry point, boot sequence
│       ├── config.h / config.c   # NVS config management
│       ├── wifi_manager.h / .c   # WiFi + AP provisioning
│       ├── tuya_cloud.h / .c     # Tuya SDK wrapper
│       ├── ha_mqtt.h / .c        # Home Assistant MQTT client
│       └── dp_bridge.h / .c      # DP <-> MQTT bridge logic
├── tools/
│   ├── provision.py              # AP/MQTT provisioning CLI
│   └── requirements.txt
└── config/
    └── config-example.json
```
