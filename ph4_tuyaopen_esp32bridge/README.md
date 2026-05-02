# ph4_tuyaopen_esp32bridge

ESP32 bridge firmware using **TuyaOpen SDK** for SmartLife app pairing.

Unlike the TuyaLink variant (`ph4_tuya_esp32bridge`), this version uses the standard
Tuya WiFi device protocol — the device pairs interactively with the SmartLife app
and is automatically bound to the user's home account.

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

### 2. Create Tuya Product

On [Tuya IoT Platform](https://iot.tuya.com):

1. **Create Product** → Custom Solution → Lighting / Electrical → **WiFi** (NOT TuyaLink!)
2. Set Data Center to **Central Europe**
3. Add DPs:
   - DP 1-16: `switch_1`..`switch_16` (Boolean, R/W)
   - DP 17-32: `relay_status_1`..`relay_status_16` (Boolean, R/W)
4. Go to **Device** → **Authorization** → get free development licenses (UUID + AUTH_KEY)
5. Note the **Product ID (PID)**

### 3. Configure

Edit `src/tuya_config.h` with your PID, UUID, and AUTH_KEY.

Edit Kconfig (or `sdkconfig`) for HA MQTT broker settings.

### 4. Build

```bash
# If using tuyaopen build system:
cd tuyaopen
source export.sh
tos build --project ../  --platform esp32

# Or if using ESP-IDF component approach:
cd firmware
idf.py build
```

### 5. Pair with SmartLife

1. Flash the firmware
2. On first boot, device enters **AP pairing mode** (LED blinks fast)
3. Open SmartLife app → Add Device → Auto-scan or Manual → select your product
4. Follow SmartLife prompts to provide WiFi credentials
5. Device activates and appears in your SmartLife home

### DP Layout

| DP ID | Name | Direction | Purpose |
|-------|------|-----------|---------|
| 1-16 | switch_1..switch_16 | HA → Tuya | Switch channels (HA controls SmartLife) |
| 17-32 | relay_status_1..relay_status_16 | Tuya → HA | Relay/socket channels (SmartLife triggers HA) |
