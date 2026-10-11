#!/usr/bin/env python3
"""Read and print the live status of every device in the local LocalTuya
export that has a resolved LAN IP (10.0.1.x). Skips devices still on a
stale cloud/NAT host -- see tuya/MIGRATION.md for which ones those are and
why.

Credentials are loaded at runtime from tuya_export/ via tuya_local.py --
nothing sensitive is hardcoded here.

Connection uses tuya_local.connect(), which tries both protocol versions
3.3 and 3.4 (not just whatever's recorded for the device) with retries --
see that module's docstring and MIGRATION.md for why a single fixed
version is unreliable in this household.
"""
from tuya_local import connect, load_devices, local_devices

devices = local_devices(load_devices())
print(f"{len(devices)} device(s) with a resolved LAN IP\n")

for dev in devices:
    name = dev["friendly_name"]
    host = dev["host"]
    print(f"=== {name} ({host}) ===")

    try:
        _, dps, version = connect(dev)
    except RuntimeError as e:
        print(f"  {e}")
        print()
        continue

    print(f"  (connected at protocol {version})")

    # Map dp_id -> known entity name where we have one, else just show raw.
    id_to_name = {}
    for ent in dev["entities"]:
        if isinstance(ent["id"], int):
            id_to_name[str(ent["id"])] = ent["friendly_name"]

    for dp_id, value in sorted(dps.items(), key=lambda kv: int(kv[0])):
        label = id_to_name.get(dp_id, f"dp {dp_id}")
        print(f"  {dp_id:>3s}  {label:35s} = {value}")
    print()
