#!/usr/bin/env python3
"""PoC: flip Terrace socket on, read back state, wait 5s, flip off, read back
state -- repeat 10x. Verifies LocalTuya control end-to-end (see
tuya/MIGRATION.md for how its dp map / protocol version were resolved).

Credentials are loaded at runtime from the local tuya_export/ snapshot via
tuya_local.py -- nothing sensitive is hardcoded here.

Uses tuya_local.connect(), which tries both protocol versions 3.3 and 3.4
(not just whatever's recorded for the device), and reconnects/retries if a
call fails mid-run -- see tuya_local.py's docstring and MIGRATION.md for
why a single fixed-version connection is unreliable in this household.
"""
import time

from tuya_local import connect, entity_dp_id, get_device

DEVICE_NAME = "Terrace socket"
SWITCH_SUFFIX = "开关1"  # the primary switch entity, not child_lock/relay_status

dev = get_device(DEVICE_NAME)
switch_dp = entity_dp_id(dev, SWITCH_SUFFIX)
if switch_dp is None:
    raise SystemExit(f"{DEVICE_NAME}: switch dp_id not resolved in the local export")

d, _, version = connect(dev)
print(f"Connected to {DEVICE_NAME} at protocol {version}")


def reconnect():
    global d, version
    d, _, version = connect(dev)


def read_switch():
    try:
        st = d.status()
        return st.get("dps", {}).get(str(switch_dp))
    except Exception:
        reconnect()
        st = d.status()
        return st.get("dps", {}).get(str(switch_dp))


def set_switch(value):
    try:
        d.set_value(switch_dp, value)
    except Exception:
        reconnect()
        d.set_value(switch_dp, value)


for i in range(1, 11):
    print(f"--- iteration {i}/10 ---")

    set_switch(True)
    time.sleep(0.5)
    state = read_switch()
    print(f"  ON  requested -> read back: {state}")
    if state is not True:
        print("  WARNING: did not read back ON as expected")

    time.sleep(5)

    set_switch(False)
    time.sleep(0.5)
    state = read_switch()
    print(f"  OFF requested -> read back: {state}")
    if state is not False:
        print("  WARNING: did not read back OFF as expected")

print("\nDone: 10/10 iterations completed")
