# localtuya Config Generator — Session Notes

## Goal

Convert the Tuya cloud export (produced by `export.ipynb`) into a ready-to-use
[localtuya](https://github.com/rospogrigio/localtuya) configuration for Home Assistant.

Primary challenge: the Tuya cloud API **does not expose numeric dp_ids** for Smart Home
devices. localtuya needs numeric dp_ids. The solution is local LAN polling with tinytuya.

---

## File

**`localtuya_config.ipynb`** — single notebook, run top-to-bottom.
Input: `tuya_export/tuya_export_*.json` (newest file auto-selected).
Output: `tuya_export/localtuya_YYYYMMDD_HHMMSS.{json,yaml,md}`.

---

## Cell-by-cell walkthrough

### Cell 1 — pip install pyyaml

Installs PyYAML. Nothing else.

### Cell 2 — Load export

Loads the newest `tuya_export_*.json`. Extracts these top-level dicts (all used later):

| Variable | Source key | Contains |
|----------|-----------|---------|
| `devices_detail` | `devices.detail` | Full device records (name, ip, sub, product_id, …) |
| `devices_factory` | `devices.factory` | MAC, SN, `local_key` |
| `devices_spec` | `devices.spec` | iot-03 per-device spec; **has dp_id + custom_name** |
| `devices_functions` | `devices.functions` | v1 functions; **no dp_id**, best user-visible names |
| `devices_status` | `devices.status` | Live DP values as `[{code, value}]` |
| `devices_model` | `devices.model` | v2 thing model JSON |
| `products_funcs` | `products_funcs` | product_id → functions (per-product, may have dp_id) |

Also prints a quick coverage table: WiFi devices vs. devices that already have dp_ids
from the cloud (usually 0 for Smart Home accounts).

### Cell 3 — DP_TABLE

A dict of 61+ known Tuya DP codes → entity metadata:

```python
DP_TABLE = {
    "switch_1": {"platform": "switch", "group": "sw_1", "role": "id", "default_name": "Switch 1"},
    "bright_value": {"platform": "light", "group": "light", "role": "brightness",
                     "brightness_lower": 25, "brightness_upper": 255},
    "cur_power":    {"platform": "sensor", "group": "sen_pow", "role": "id",
                     "unit_of_measurement": "W", "device_class": "power",
                     "_switch_role": "current_consumption", "_scale_divisor": 10},
    ...
}
```

Key design concepts:

- **`platform`** — localtuya entity type: `switch`, `light`, `sensor`, `binary_sensor`,
  `climate`, `cover`, `fan`
- **`group`** — DPs with the same group key collapse into **one HA entity**.
  e.g. `switch_led`, `bright_value`, `colour_data`, `temp_value` all share group `"light"` → one `light` entity.
  Switch groups are unique per code (`sw_1`, `sw_2`, …) → one entity each.
- **`role`** — which localtuya config field this DP fills.
  `role="id"` → primary dp_id. Other roles: `"brightness"`, `"color_temp"`, `"color"`, etc.
- **`_switch_role`** — power-monitoring DPs (cur_power, cur_current, cur_voltage) have this.
  Their dp_id gets injected into the main switch entity under this field name.
- **`_scale_divisor`** — fixed divisor for sensor scaling (e.g. power ÷ 10 = W).
- **`COMPOUND_PLATFORMS = {"light", "climate", "cover", "fan"}`** — all DPs in same group → one entity.
- **`_META_KEYS`** — keys not passed through to localtuya output.

To add a new device type: add entries to `DP_TABLE` with the right platform/group/role.

### Cell 4 — Helper functions

**`parse_values(v)`** — Tuya `values` field is a JSON string inside JSON; this parses it.

**`humanize(code)`** — `"switch_1"` → `"Switch 1"`.

**`_apply_dp_list(dp_map, dp_list, source, prefer_name)`** — merges a list of DP dicts
into the running dp_map. Only backfills `dp_id` if still None; enriches name if `prefer_name`.

**`get_dp_map(device_id)`** — the core lookup function. Returns `{code: {dp_id, type, name, values, source}}`.

Priority (highest → lowest):

| Priority | Source | Notes |
|----------|--------|-------|
| 0 | `LOCAL_DP_IDS[device_id]` | tinytuya LAN poll — ground truth, overrides everything |
| 1 | `devices_spec[device_id]` | iot-03 spec — has dp_id + custom_name |
| 2 | `products_funcs[product_id]` | product-level functions |
| 3 | `devices_functions[device_id]` | v1 functions — no dp_id but best names |
| 4 | `devices_model[device_id]` | v2 thing model |
| 5 | `devices_status[device_id]` | live status — ensures code is present, no dp_id |

Priority 0 is applied **after** building from cloud sources (override at the end).
`globals().get("LOCAL_DP_IDS", {})` is used so this cell can run before the polling cell.

**`get_local_key(device_id)`** — reads from `devices_factory` first, falls back to `devices_detail`.

**`scaling_for_dp()`** — computes localtuya `scaling` multiplier from Tuya `scale` field
plus `_scale_divisor`. Formula: `1 / (10^tuya_scale × fixed_div)`.

Cell ends with a **dp_id coverage diagnostic table** (re-run this after polling to verify).

### Cell 5 — `LOCAL_DP_IDS = {}`

Initialises the dict so helper cell can run without error before polling. The polling cell
overwrites it.

### Cell 6 — Local IP discovery (3 cells)

The cloud export stores the **external/NAT IP** — useless for LAN control.
This section discovers real local IPs. It is split into three cells intentionally:

#### Cell 6a — Init (`LOCAL_IP_MAP = {}`)

Run **once** at the start of a session to reset the map. Do **not** re-run between
passes — it wipes already-found IPs.

#### Cell 6b — Config knobs

```python
LAN_SUBNET       = "10.0.1.0/24"  # ← set to your network
UDP_SCAN_RETRIES = 20             # broadcast rounds; raise to 60+ for stubborn devices
PING_TIMEOUT     = 1.0
PING_WORKERS     = 200
TCP_TIMEOUT      = 1.0
TCP_WORKERS      = 128
PROBE_VERSIONS   = ["3.3", "3.1", "3.4"]  # tried in order
PROBE_TIMEOUT    = 3
```

Tweak these freely between passes without touching the discovery logic.

#### Cell 6c — Discovery logic (re-run as many times as needed)

At the top, prints which devices are already resolved and which are still missing.
Only processes the **missing** ones — already-resolved devices are never touched again.

**Step 1 — tinytuya UDP broadcast**
`tinytuya.deviceScan(maxretry=UDP_SCAN_RETRIES)` listens on UDP 6666/6667. Tuya devices
broadcast periodically (every 10–30 s) with their `gwId` + local IP.
Gives `device_id → ip` directly with no guessing.

**Step 2 — Ping sweep** (only if devices still missing after step 1)
Pings all hosts in the subnet in parallel. OS-agnostic (Darwin/Linux/Windows).
Purpose: find all live IPs cheaply before expensive port probing.

**Step 3 — TCP port 6668 scan** (on live hosts only)
Tuya local control port. Skips hosts already claimed by resolved devices.

**Step 4 — Handshake probe**
For each unresolved device × each unclaimed candidate IP × each version in `PROBE_VERSIONS`:
tries `tinytuya.Device.status()`. A valid `dps` response confirms identity.
Marks IP as claimed on first match.

**Re-run workflow:**
```
Pass 1: run 6c  →  resolves 60% of devices
         adjust UDP_SCAN_RETRIES = 60 in 6b
Pass 2: run 6b then 6c again  →  catches more slow broadcasters
         adjust PROBE_VERSIONS = ["3.4", "3.3"] for a stubborn device
Pass 3: run 6b then 6c again  →  ...
```

Result: `LOCAL_IP_MAP = {device_id: "10.0.1.x"}`.

### Cell 7 — tinytuya dp_id polling (markdown + code)

Only runs on devices present in `LOCAL_IP_MAP` — devices not found on LAN are skipped entirely.

For each device:
1. Calls `tinytuya.Device(id, local_ip, local_key).status()` → `{"dps": {"1": true, "2": 100, …}}`
2. Cross-references with cloud `devices_status[device_id]` → `[{code, value}]`

**Cross-reference algorithm** (`_map_codes_to_dpids`):

- **Pass 1 (unique value match)**: if exactly one local dp_id and exactly one cloud code
  share the same `repr(value)` → direct match. Works perfectly for unique readings
  like `cur_power=2300`.
- **Pass 2 (ordered match)**: for ambiguous groups (e.g. five switches all currently `True`),
  sort dp_ids numerically and zip with cloud codes in their status-list order.
  Tuya guarantees cloud status order matches hardware order (switch_1, switch_2, …).

Result: `LOCAL_DP_IDS = {device_id: {code: dp_id_int}}`.

After running, **re-run the helpers cell** to refresh the dp_id coverage table,
then re-run the main loop.

### Cell 8 — Entity builder (`build_entities`)

Takes `(device_name, dp_map)`, returns `(entities, warnings)`.

**Logic:**

1. Filter dp_map to codes present in `DP_TABLE`. Group by `(platform, group_key)`.
2. Collect power-monitoring dp_ids for switch injection (`pm_switch_fields`).
3. Find the "main switch" group (`sw_1` → `sw_main` → `sw_relay`) for PM injection.
4. Per group:
   - **Compound** (light/climate/cover/fan): one entity; primary DP (`role="id"`) sets `id`;
     other roles fill named fields; extra DP_TABLE fields injected; brightness range
     read from spec values.
   - **Switch**: one entity per group; PM fields injected into main switch.
   - **Sensor**: `unit_of_measurement`, `device_class`, `state_class` from DP_TABLE;
     `scaling` computed from `scaling_for_dp()`.
   - **Binary sensor**: `device_class`, `state_on`, `state_off` from DP_TABLE.

Missing dp_ids produce `"# FILL_DP_ID"` placeholder + warning string.

### Cell 9 — Main conversion loop

Iterates WiFi devices (non-sub, has local key). Uses `LOCAL_IP_MAP.get(device_id) or cloud_ip`
for the `host` field. Builds entity list, collects warnings, assembles `localtuya_devices` list.

### Cell 10 — Summary table

Prints device-by-entity breakdown with dp_ids and any warnings.

### Cell 11 — Patch cell

Empty cell with commented examples for manual overrides before saving:
rename entities, fix protocol version, fill missing dp_ids.

### Cell 12 — Save output

Writes three files:
- **`.json`** — exact format localtuya stores in HA config entries
- **`.yaml`** — `localtuya:` YAML block (v3 era format, still useful for documentation)
- **`.md`** — Markdown table per device for quick reference

---

## Applying the config to Home Assistant / localtuya

### localtuya version matters

| Version | Configuration method |
|---------|---------------------|
| < 4.0   | `configuration.yaml` under `localtuya:` key — YAML supported |
| 4.0+    | UI-only (config flow). YAML support **dropped entirely** |
| 5.0+ (current) | UI-only. Generated YAML is for reference only, **not loaded by HA** |

The notebook generates a YAML file anyway — useful as a reference cheat sheet while
clicking through the UI, but HA will not read it.

---

### Option A — Template import (recommended for v5+)

localtuya v5 has a built-in template mechanism:

1. **Generate template files** from the notebook (see "Save output" cell — it writes
   one YAML per device into `tuya_export/localtuya_templates/`).

2. **Copy the template files** to your HA instance:
   ```
   custom_components/localtuya/templates/<Device Name>.yaml
   ```
   No HA restart needed — localtuya reads templates at add-device time.

3. **Add each device** through the UI:
   - Settings → Integrations → LocalTuya → **Configure** → Add device
   - When prompted, choose **"Use saved template"** and pick the device by name
   - HA pre-fills all fields from the template
   - Review, confirm, done

**Template YAML format** (one file per device):
```yaml
friendly_name: "Living Room Socket"
host: "10.0.1.42"
device_id: "abc123..."
local_key: "xyz789..."
protocol_version: "3.3"
entities:
  - platform: switch
    friendly_name: "Living Room Socket Switch 1"
    id: 1
  - platform: switch
    friendly_name: "Living Room Socket Switch 2"
    id: 2
  - platform: sensor
    friendly_name: "Living Room Socket Power"
    id: 5
    unit_of_measurement: "W"
    device_class: power
    state_class: measurement
    scaling: 0.1
  - platform: sensor
    friendly_name: "Living Room Socket Voltage"
    id: 6
    unit_of_measurement: "V"
    device_class: voltage
    state_class: measurement
    scaling: 0.1
```

---

### Option B — Manual UI entry

Use the generated `.md` file (`tuya_export/localtuya_*.md`) as a reference:

1. Settings → Integrations → + Add Integration → **LocalTuya**
2. Enter device details (host, device_id, local_key, protocol version)
3. Add entities one by one, entering the dp_id and platform for each
4. Use the Markdown table to copy values without switching windows

Best for small numbers of devices or when the template approach fails.

---

### Option C — Direct storage editing (advanced, risky)

localtuya v5+ stores its config in:
```
/config/.storage/core.config_entries
```

You can add entries manually, but **this is not recommended**:
- Entries are cross-referenced with `core.device_registry` and `core.entity_registry`
- A JSON syntax error breaks HA on startup
- Entry IDs must be unique UUIDs

If you attempt it:
1. Stop Home Assistant first
2. Make a full backup of `.storage/`
3. Validate your JSON before saving
4. Restart HA and check logs immediately

The `unique_id` field for a localtuya entry should be the `device_id`.

---

### Generating template files from the notebook

The save cell (Cell 12) already writes `localtuya_*.json` and `localtuya_*.yaml`.
To also generate per-device template files, add a cell after the save cell:

```python
import re

template_dir = EXPORT_DIR / "localtuya_templates"
template_dir.mkdir(exist_ok=True)

for dev in localtuya_devices:
    # Sanitise device name for use as filename
    safe_name = re.sub(r'[^\w\s\-]', '', dev["friendly_name"]).strip()
    template = {
        "friendly_name":    dev["friendly_name"],
        "host":             dev["host"],
        "device_id":        dev["device_id"],
        "local_key":        dev["local_key"],
        "protocol_version": dev["protocol_version"],
        "entities":         dev["entities"],
    }
    path = template_dir / f"{safe_name}.yaml"
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(template, fh, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, indent=2)
    print(f"  {path.name}")

print(f"\n{len(localtuya_devices)} template(s) written to {template_dir}/")
print(f"Copy to: custom_components/localtuya/templates/")
```

---

## Known issues / gotchas

### dp_id discovery fails for some devices

Cloud API never returns dp_ids for Smart Home consumer devices (it returns the code
list but with `dp_id: null`). LAN polling is the only reliable source.

Devices that can't be found on LAN:
- Currently offline (no ping response, no port 6668)
- On a different VLAN/segment from the machine running Jupyter
- Zigbee/BLE sub-devices — these don't speak Tuya LAN protocol directly;
  their gateway does. Sub-devices are skipped by the `sub=True` filter anyway.

### Protocol version 3.4

Very new devices (2023+) use v3.4 with stronger encryption. tinytuya supports it
but the handshake is sometimes flaky. If a device is found by ping but fails the
handshake probe, try adding it to `PROTOCOL_OVERRIDES = {"<device_id>": "3.4"}` in
the main loop cell and re-run the polling cell with only that version.

### All switches have the same current value

Five sockets all `switch_N=True` → pass 2 uses sorted dp_id order (1,2,3,4,5)
zipped with cloud status list order (switch_1, switch_2, …). This is correct as long
as Tuya assigned dp_ids in the same order as the switch numbering — which is always
true for standard multi-gang sockets.

### Power-monitoring scaling

`cur_power` reports in units of 0.1 W (÷10), `cur_voltage` in 0.1 V (÷10),
`add_ele` in 0.001 kWh (÷1000). These divisors are in `_scale_divisor` in DP_TABLE.
If the spec also has a `scale` field (e.g. `scale: 1`), that stacks.
The combined `scaling` value in the sensor entity = `1 / (10^spec_scale × _scale_divisor)`.
If readings look 10× off, check and adjust in the patch cell.

### UDP broadcast misses half the devices

Tuya devices broadcast every 10–30 s; with 20 retries (~6 s window) some might be missed.
The ping + TCP sweep catches them. If still missing:
- Increase `UDP_SCAN_RETRIES` to 60–100 (20–30 s window)
- Check if Jupyter is on the same broadcast domain as the devices
- Some managed switches block UDP broadcasts between VLANs

### localtuya version compatibility

The output JSON matches what localtuya v5+ stores in HA config entries.
Field names come from localtuya's `const.py`. If a new localtuya version renames fields,
update `DP_TABLE` entries and `build_entities()` accordingly.

---

## Extending DP_TABLE

To add support for an unknown device category:

1. Check `data['devices']['spec']['<device_id>']` in the export to see the DP codes.
2. Look up the code in Tuya's [dp code documentation](https://developer.tuya.com/en/docs/iot/standarddescription) or the tinytuya device database.
3. Add an entry to `DP_TABLE`:
   ```python
   "new_code": {
       "platform": "sensor",       # or switch/light/binary_sensor/climate/cover/fan
       "group":    "sen_newcode",  # unique key for simple entities; shared for compound
       "role":     "id",           # "id" for primary; named role for compound secondaries
       "default_name": "New Sensor",
       "unit_of_measurement": "ppm",
       "device_class": "carbon_monoxide",
       "state_class": "measurement",
   },
   ```
4. Re-run DP_TABLE cell → helpers cell → main loop.

---

## Typical run order

```
1.  pip install pyyaml
2.  Load export
3.  DP_TABLE
4.  Helpers              ← dp_id coverage (all 0 first time — expected)
5.  LOCAL_DP_IDS = {}
6a. LOCAL_IP_MAP = {}    ← reset once per session
6b. Config knobs         ← set LAN_SUBNET here
6c. Discovery logic      ← re-run as many times as needed until all resolved
      [adjust knobs in 6b, re-run 6b+6c for each pass]
7.  tinytuya polling     ← only polls devices in LOCAL_IP_MAP
8.  Helpers (re-run)     ← coverage now shows "local_lan" sources
9.  Entity builders
10. Main loop
11. Summary
12. Patch (edit if needed)
13. Save                 ← writes .json / .yaml / .md
14. Export templates     ← writes tuya_export/localtuya_templates/*.yaml
15. Print YAML
```

**Between sessions:** `LOCAL_IP_MAP` and `LOCAL_DP_IDS` are lost when the kernel restarts.
Re-run from step 6a (or manually rebuild `LOCAL_IP_MAP` from a saved JSON if desired).
