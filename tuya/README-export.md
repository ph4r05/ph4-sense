# Tuya Cloud Export — Session Notes

## Goal

Export everything useful from a personal Tuya developer account via the Tuya OpenAPI:
- All devices with full metadata (IP, MAC, local_key, node_id, gateway hierarchy, category, online status)
- All scenes (tap-to-run) and automations, including their conditions and actions
- Cloud scene rules (v2 API)
- Device–scene bindings (physical buttons wired to scenes)
- Device function/instruction sets, DP status, product specs, scheduled timers

Primary use case is understanding the home automation topology — device addresses, how buttons are wired to scenes, what automations exist.

## What was built

**File:** `export.ipynb`

A single Jupyter notebook that connects to the Tuya OpenAPI, runs a multi-pronged discovery of homes/devices/scenes, and saves the result as a JSON dump + CSV.

**Dependency:** `tuya-connector-python` (PyPI). It handles HMAC signing and token refresh transparently.

**Credentials** are loaded from env vars (or a `.env` file via `python-dotenv`):

| Var | Required | Notes |
|-----|----------|-------|
| `TUYA_ACCESS_ID` | yes | Cloud project Access ID |
| `TUYA_ACCESS_KEY` | yes | Cloud project Access Secret |
| `TUYA_API_ENDPOINT` | no | Default: `https://openapi.tuyaeu.com` |
| `TUYA_APP_USER_UID` | no | Real app-user uid (see below) |
| `TUYA_HOME_IDS` | no | Comma-separated home IDs (manual override) |

## Key design decisions & gotchas

### 1. Do NOT call `/v1.0/token` manually after `connect()`

`openapi.connect()` internally fetches the token and stores it. If you call `openapi.get("/v1.0/token", ...)` afterwards, the SDK incorrectly includes the already-stored `access_token` in the HMAC signature. The `/v1.0/token` endpoint uses a simpler signing scheme (no access_token in the hash), so this produces `sign invalid` (code 1004).

**Fix:** Read the uid from the `connect()` response directly — `resp['result']['uid']`.

### 2. The uid from `connect()` is a service-account uid, not an app-user uid

`connect()` returns a `uid` like `bay16722271567169lwF`. This is the cloud project's service account. Passing it to `/v1.0/users/{uid}/homes` returns `permission deny` (code 1106) because that endpoint expects a real Tuya Smart/Life app user uid.

**How to get the real app-user uid:**
Tuya IoT console → your Cloud project → Devices → Link Devices → **Users** tab → copy the uid shown there.
Set it as `TUYA_APP_USER_UID` env var. Without it, home IDs are inferred from devices (see below).

### 3. Home IDs are inferred from `owner_id` on devices

Each device returned by the `iot-01/associated-users/devices` endpoint carries an `owner_id` field which is the home ID. This means homes can be discovered without a real app-user uid. The notebook collects all unique `owner_id` values after device enumeration, then calls `GET /v1.0/homes/{home_id}` for each. If that also returns permission denied (some account types), a stub `{home_id, name}` is stored so scenes/automations can still be queried by home ID.

### 4. Device enumeration uses three parallel approaches

The notebook tries all three and deduplicates by device_id:
1. `GET /v1.0/iot-01/associated-users/devices` — cursor-paged, most reliable for linked devices
2. `GET /v1.0/homes/{home_id}/devices` — home-level listing (needs homes to be known first)
3. `GET /v1.0/users/{app_user_uid}/devices` — only if `TUYA_APP_USER_UID` is set

### 5. Pagination

Two styles exist in the Tuya API:
- **page_no / page_size** — standard, used by most v1 endpoints
- **last_row_key** — cursor style, used by `iot-01` endpoints

Both are wrapped in helper functions `get_paged()` and `get_cursor_paged()`.

## Output format

### Files produced

Both saved under `tuya_export/` with a timestamp suffix:
- `tuya_export_YYYYMMDD_HHMMSS.json` — full nested JSON
- `devices_YYYYMMDD_HHMMSS.csv` — flat device table for quick reference

### JSON structure

```
{
  "exported_at": "20240307_143022",
  "api_endpoint": "https://openapi.tuyaeu.com",

  "homes": {
    "<home_id>": {
      "home_id": "...",
      "name": "My Home",
      "lon": 14.4,
      "lat": 50.1,
      "geo_name": "Prague, CZ",
      "role": "owner",
      "admin_user_count": 1,
      "member_count": 2,
      ...
    }
  },

  "rooms": {
    "<home_id>": [
      { "room_id": "...", "name": "Living Room" },
      ...
    ]
  },

  "devices": {

    "raw": {
      // device_id -> basic record from listing endpoint (may be incomplete)
    },

    "detail": {
      // device_id -> full GET /v1.0/devices/{id} response
      "<device_id>": {
        "id": "...",
        "name": "Smart Plug",
        "uid": "<owner_uid>",
        "owner_id": "<home_id>",
        "room_id": "...",
        "category": "cz",          // Tuya category code
        "product_id": "...",
        "product_name": "...",
        "model": "...",
        "sub": false,              // true = Zigbee/BLE sub-device
        "asset_id": "...",
        "gateway_id": "...",       // parent gateway device_id (if sub)
        "node_id": "...",          // hardware address within gateway (e.g. IEEE EUI-64 for Zigbee)
        "ip": "192.168.1.x",
        "time_zone": "+01:00",
        "active_time": 1700000000, // unix timestamp
        "create_time": 1700000000,
        "update_time": 1700000000,
        "online": true,
        "icon": "smart/icon/...",
        "local_key": "..."         // 16-byte local AES key for LAN control
      }
    },

    "status": {
      // device_id -> list of DP (datapoint) current values
      "<device_id>": [
        { "code": "switch_1", "value": true },
        { "code": "countdown_1", "value": 0 }
      ]
    },

    "functions": {
      // device_id -> instruction set (what DPs can be commanded)
      "<device_id>": {
        "category": "cz",
        "functions": [
          {
            "code": "switch_1",
            "desc": "...",
            "name": "Switch 1",
            "type": "Boolean",
            "values": "{}"
          }
        ]
      }
    },

    "factory": {
      // device_id -> factory info (most sensitive data lives here)
      "<device_id>": [
        {
          "id": "<device_id>",
          "uuid": "...",
          "sn": "...",
          "mac": "AA:BB:CC:DD:EE:FF",
          "local_key": "..."        // same as in detail
        }
      ]
    },

    "spec": {
      // device_id -> product data model specification
      "<device_id>": {
        "category": "cz",
        "functions": [ ... ],       // writable DPs with value constraints
        "status":    [ ... ]        // readable DPs with value constraints
      }
    },

    "shadow": {
      // device_id -> v2 IoT Core shadow (current property values)
      "<device_id>": {
        "properties": [
          { "code": "switch_1", "value": true, "time": 1700000000 }
        ]
      }
    },

    "timers": {
      // device_id -> scheduled tasks
      "<device_id>": [
        {
          "timer_id": "...",
          "device_id": "...",
          "alias_name": "Morning",
          "enable": true,
          "loops": "1111100",       // bitmask Mon–Sun
          "time": "07:00",
          "timezone_id": "Europe/Prague",
          "functions": [
            { "code": "switch_1", "value": true }
          ]
        }
      ]
    },

    "sub_devices": {
      // gateway_device_id -> list of sub-devices (Zigbee/BLE children)
      "<gateway_id>": [
        {
          "id": "...",
          "name": "...",
          "node_id": "...",         // hardware address within gateway
          "product_id": "...",
          "online": true
        }
      ]
    },

    "scene_bindings": {
      // device_id -> scenes bound to this device (e.g. physical button)
      "<device_id>": [
        {
          "scene_id": "...",
          "name": "Good night",
          ...
        }
      ]
    },

    // optional — only present if FETCH_LOGS=True
    "logs": {
      "<device_id>": {
        "log_list": [
          {
            "event_id": "...",
            "event_from": "...",
            "row_key": "...",
            "code": "switch_1",
            "value": "true",
            "event_time": 1700000000000  // milliseconds
          }
        ],
        "has_next": false,
        "last_row_key": ""
      }
    }
  },

  "scenes": {
    "by_home": {
      "<home_id>": [
        { "scene_id": "...", "name": "Good night", ... }
      ]
    },
    "detail": {
      // scene_id -> full scene object with actions
      "<scene_id>": {
        "scene_id": "...",
        "name": "Good night",
        "background": "...",
        "display_color": "#...",
        "status": "enable",
        "actions": [
          {
            "action_executor": "dpIssue",
            "entity_id": "<device_id>",
            "executor_property": {
              "switch_1": false
            }
          },
          {
            "action_executor": "triggerScene",
            "entity_id": "<scene_id>"
          },
          {
            "action_executor": "delay",
            "executor_property": { "delay_seconds": 30 }
          }
        ]
      }
    }
  },

  "automations": {
    "by_home": {
      "<home_id>": [
        { "automation_id": "...", "name": "Motion on", ... }
      ]
    },
    "detail": {
      // automation_id -> full automation object
      "<automation_id>": {
        "automation_id": "...",
        "name": "Motion on",
        "enabled": true,
        "match_type": 1,            // 1=AND, 2=OR between conditions
        "conditions": [
          {
            "entity_type": 1,       // 1=device, 2=weather, 3=timer
            "entity_id": "<device_id>",
            "order_num": 1,
            "expr": {
              "statusCode": "pir",
              "comparator": "==",
              "statusValue": "pir"
            }
          }
        ],
        "actions": [
          {
            "action_executor": "dpIssue",
            "entity_id": "<device_id>",
            "executor_property": { "switch_1": true }
          }
        ],
        "pre_conditions": []       // time-range constraints
      }
    }
  },

  "cloud_rules": {
    // v2 IoT Core scene/linkage rules (created via developer console or API)
    "list": [
      { "rule_id": "...", "name": "...", "rule_type": "automation" | "scene", ... }
    ],
    "detail": {
      "<rule_id>": { ... }         // same shape as list item but with full actions/conditions
    }
  }
}
```

### CSV columns (devices table)

`device_id, name, category, product_id, model, ip, online, sub, node_id, gateway_id, local_key, mac, sn, owner_id, room_id, active_time, update_time, create_time`

`local_key`, `mac`, `sn` are merged from the `factory` endpoint.

## What still needs work / next steps

- **Scenes & automations require homes.** If home IDs cannot be fetched (permission denied on both `/v1.0/homes/{id}` and the detail endpoint), scenes and automations will be empty. Getting a real app-user uid (`TUYA_APP_USER_UID`) is the reliable fix.
- **`iot-01/associated-users/devices` may not return devices** if none are linked to the cloud project. In that case, the user must link devices in the Tuya IoT console under the project's "Link Devices" tab, or provide home IDs / user uid directly.
- **Pagination on automations/scenes** — the current code does a single-page fetch. If a home has more than ~100 scenes/automations, `get_paged()` should be used instead of a direct `openapi.get()`.
- **Logs** are disabled by default (`FETCH_LOGS = False`). Enable per-device and consider saving each device's logs to a separate file for large fleets.
- **Sub-device detail** — sub-devices discovered under gateways are added to `all_device_ids` but the per-device deep-fetch loop runs only over `device_ids_list` which is built before gateway discovery. A second pass over newly found sub-device IDs may be needed.
