# ph4_tuya_esp32bridge

ESP32-C6 firmware that bridges **Tuya/SmartLife** with **Home Assistant via MQTT**.

The device appears in the SmartLife app as a paired device with 16 switch channels
and 16 socket channels. It bridges bidirectionally:

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

### 1. Create a Product

1. Go to [iot.tuya.com](https://iot.tuya.com) → **Cloud** → **Development**
2. Click **Create Product**
3. Choose category: **Electrical** → **Scene Panel Switch** (or Custom)
4. Name it (e.g. "ph4-bridge")
5. Select **Standard Instruction Set** or **Custom**
6. The **Product ID (PID)** is shown immediately — copy it now. You do **not** need to release the product.

### 2. Define Data Points (DPs)

In the product panel, add these DPs:

| DP ID  | Name        | Type    | Mode | Description                  |
|--------|-------------|---------|------|------------------------------|
| 1–16   | switch_1..16| Boolean | R/W  | Switch channels (HA→Tuya)    |
| 101–116| socket_1..16| Boolean | R/W  | Socket channels (Tuya→HA)    |

### 3. Device Credentials — two options

#### Option A: Activation flow (recommended for development — no pre-provisioning needed)

Leave `uuid` and `auth_key` **empty** in your config. Only `pid` is required.

On first boot the device enters pairing mode. Open SmartLife → **Add Device** and follow the instructions. The app sends a token to the device, Tuya cloud issues a permanent UUID + AuthKey, and the SDK stores them in the `tuya_kv` NVS partition. On all subsequent boots the stored credentials are used automatically — no re-pairing needed.

This is identical to how real consumer Tuya products work.

#### Option B: Pre-provisioned credentials (for production / batch flashing)

Useful when you want to skip the SmartLife pairing step (e.g. CI flashing or multiple devices).

1. In the Tuya console go to your product → **Hardware Development** → **Batch Test Devices**
2. Generate 1–N device credential pairs and download the CSV
3. Each row contains a **UUID** (20 chars) and **Auth Key** (32 chars)
4. Set them in your `config.json` alongside the PID

The firmware detects which mode to use: if `uuid` or `auth_key` are empty → activation flow; if both are present → pre-provisioned direct connect.

---

## Setup: ESP-IDF

**ESP-IDF** is Espressif's official C SDK and build system for ESP32 chips. It provides the compiler toolchain, FreeRTOS, WiFi/MQTT drivers, and `idf.py` — the command-line tool used to configure, build, and flash firmware. You need it installed before you can compile this project.

The **Tuya IoT Core SDK** is already included in this repo as a git submodule at `firmware/components/tuya-iot-core-sdk`. No manual steps needed — just `git submodule update --init --recursive` after cloning.

### 1. Install ESP-IDF v5.2

```bash
git clone --recursive https://github.com/espressif/esp-idf.git ~/esp/esp-idf
cd ~/esp/esp-idf
git checkout v5.2.1
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

### Step 2 — Tuya cloud pairing (activation flow)

If `uuid` and `auth_key` are empty in your config (recommended for development):

1. After the device connects to WiFi it enters **Tuya activation mode**
2. Open **SmartLife** → **+** → **Add Device** → **Add Manually** → choose the product category
3. Follow the on-screen steps (EZ mode or AP mode)
4. The app sends your WiFi credentials + an activation token to the device
5. The device contacts Tuya cloud, receives its permanent UUID + AuthKey, and stores them in NVS
6. The device appears in SmartLife — pairing is complete
7. On all future reboots the device connects directly to Tuya cloud using the stored credentials

> **Note:** You do not need to release the product in the Tuya developer console for this to work.
> A product in draft/development state pairs and functions normally.

### Step 2 (alternative) — Pre-provisioned credentials

If `uuid` and `auth_key` are set in config, the device skips the activation flow entirely and connects directly to Tuya cloud on boot. The device still needs to appear in your SmartLife home — add it via **Add Device → Enter Device ID** or the Tuya developer console's virtual device panel.

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
| `app_cfg`  | `config.c`           | WiFi SSID/pass, MQTT host/port/creds, Tuya PID, channel config |
| `tuya_kv`  | Tuya SDK (via `platform/esp32/storage_wrapper.c`) | UUID, AuthKey, session secrets — written automatically during Tuya pairing |

The `tuya_kv` namespace is written by the Tuya SDK internally. You never need to touch it directly; the SDK reads it on boot to skip re-pairing. Factory reset erases it.

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
