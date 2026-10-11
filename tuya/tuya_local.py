"""Shared helper for ad-hoc LocalTuya scripts in this directory.

Deliberately holds no credentials itself -- everything (device_id,
local_key, host, protocol_version) is loaded at runtime from the newest
`tuya_export/localtuya_*.json` file, which is gitignored (see
../.gitignore) because it contains local_keys, device_ids, MACs and GPS
coordinates. Generate/refresh it with `export.ipynb` +
`localtuya_config.ipynb` before using these scripts.

Protocol version instability (see MIGRATION.md): some devices in this
household need 3.3, some need 3.4, and the exported `protocol_version`
per device isn't fully reliable -- this is the same instability behind
HA's Tuya cloud integration "sometimes doesn't listen" symptom. `connect()`
below tries the device's stored version first, then falls back through
the other known versions, with a couple of retries per version to ride
out the transient "single local session" lockouts these devices exhibit
under repeated probing. Treat a single connection attempt at a fixed
version as unreliable; always go through `connect()` rather than calling
`tinytuya.Device(...)` directly with a hardcoded version.
"""

import json
import time
from pathlib import Path

import tinytuya

EXPORT_DIR = Path(__file__).parent / "tuya_export"

# Try the device's own recorded version first, then fall back through the
# rest of these (order matters: most to least common in this household).
PROTOCOL_VERSIONS = ["3.3", "3.4", "3.1"]
CONNECT_RETRIES_PER_VERSION = 2
CONNECT_RETRY_DELAY_S = 3


def load_devices():
    """Return the device list from the newest localtuya_*.json export."""
    files = sorted(EXPORT_DIR.glob("localtuya_*.json"))
    if not files:
        raise FileNotFoundError(
            f"No localtuya_*.json found in {EXPORT_DIR}. " "Run export.ipynb then localtuya_config.ipynb first."
        )
    with open(files[-1], encoding="utf-8") as fh:
        return json.load(fh)


def get_device(friendly_name):
    """Look up one device dict by exact friendly_name."""
    for dev in load_devices():
        if dev["friendly_name"] == friendly_name:
            return dev
    raise KeyError(f"No device named {friendly_name!r} in the local export")


def local_devices(devices=None):
    """Devices whose host is a resolved LAN IP (10.0.1.x), not a stale
    cloud/NAT address."""
    devices = devices if devices is not None else load_devices()
    return [d for d in devices if d["host"].startswith("10.0.1.")]


def entity_dp_id(dev, name_suffix):
    """Find an entity's numeric dp_id by matching the tail of its
    friendly_name (e.g. "开关1" for the primary switch). Returns None if
    not found or still unresolved (# FILL_DP_ID)."""
    for ent in dev["entities"]:
        if ent["friendly_name"].endswith(name_suffix) and isinstance(ent["id"], int):
            return ent["id"]
    return None


def _version_order(dev):
    """Recorded protocol_version first, then the rest of PROTOCOL_VERSIONS
    in order, without duplicates."""
    recorded = dev.get("protocol_version")
    order = [recorded] if recorded else []
    order += [v for v in PROTOCOL_VERSIONS if v != recorded]
    return order


def connect(dev, timeout=4):
    """Connect to a device and fetch its status, trying multiple protocol
    versions with retries. Returns (tinytuya.Device, dps_dict, version_used).
    Raises RuntimeError with the last error seen if every version/attempt
    fails.

    Use this instead of a bare `tinytuya.Device(...).status()` call -- see
    module docstring for why a single fixed-version attempt is unreliable
    here.
    """
    last_err = None
    for version in _version_order(dev):
        for attempt in range(1, CONNECT_RETRIES_PER_VERSION + 1):
            d = tinytuya.Device(dev["device_id"], dev["host"], dev["local_key"], version=float(version))
            d.set_socketTimeout(timeout)
            try:
                st = d.status()
                dps = st.get("dps") if isinstance(st, dict) else None
                if dps:
                    return d, dps, version
                last_err = st
            except Exception as e:
                last_err = e
            if attempt < CONNECT_RETRIES_PER_VERSION:
                time.sleep(CONNECT_RETRY_DELAY_S)
    raise RuntimeError(
        f"{dev['friendly_name']}: no protocol version worked " f"(tried {_version_order(dev)}): {last_err}"
    )
