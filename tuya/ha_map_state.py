#!/usr/bin/env python3
"""Map current HA state by integration/platform -- the first step of the
Tuya->HA migration plan (map state, prefer LocalTuya, eventually generate
scene/automation YAML). See MIGRATION.md.

Cross-references HA's entity_registry/device_registry/config_entries
(WebSocket-only, not in REST /api/states) against live states, so we know
not just "what entity_id exists" but "which integration actually owns it" --
needed to prefer a localtuya entity over a tuya-cloud one for the same
physical device.
"""
import json
from collections import Counter
from pathlib import Path

from ha_client import get_registries, get_states

HA_DIR = Path(__file__).parent / "tuya_export" / "ha"

states = {s["entity_id"]: s for s in get_states()}
reg = get_registries()

entries_by_id = {e["entry_id"]: e for e in reg["config_entries"]}
devices_by_id = {d["id"]: d for d in reg["devices"]}

# entity_id -> (domain/integration, device_name)
entity_platform = {}
for ent in reg["entities"]:
    entity_id = ent["entity_id"]
    config_entry_id = ent.get("config_entry_id")
    domain = entries_by_id.get(config_entry_id, {}).get("domain") if config_entry_id else None
    device = devices_by_id.get(ent.get("device_id"), {})
    entity_platform[entity_id] = {
        "integration": domain or ent.get("platform"),
        "device_name": device.get("name_by_user") or device.get("name"),
        "disabled": bool(ent.get("disabled_by")),
    }

counts = Counter(v["integration"] for v in entity_platform.values())
print("Entities by integration:")
for integration, n in counts.most_common():
    print(f"  {integration!s:25s} {n}")

print()
print(f"Total registry entities: {len(entity_platform)}, total live states: {len(states)}")

# Save for reuse by the next script (cross-referencing against tuya_export)
out = {
    "entity_platform": entity_platform,
    "states": {k: {"state": v["state"], "attributes": v.get("attributes", {})} for k, v in states.items()},
}
out_path = HA_DIR / "ha_state_snapshot.json"
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1, ensure_ascii=False)
print(f"\nWrote {out_path}")
