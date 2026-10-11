"""Resolve our own device/scene names (from switch_bindings.json, Tuya
scenes, etc.) to real HA entity_ids, preferring local integrations over
cloud ones. Built on ha_state_snapshot.json (see ha_map_state.py)."""

import json
import re
from pathlib import Path

SNAPSHOT = Path(__file__).parent / "tuya_export" / "ha" / "ha_state_snapshot.json"

# integration -> priority (lower = preferred). Anything not listed is last.
INTEGRATION_PRIORITY = {"localtuya": 0, "mqtt": 1, "zha": 1, "tuya": 2}

_data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
_entity_platform = _data["entity_platform"]
_states = _data["states"]


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


# normalized device_name -> list of (entity_id, domain, integration)
_by_device = {}
for entity_id, info in _entity_platform.items():
    name = info.get("device_name")
    if not name:
        continue
    domain = entity_id.split(".")[0]
    _by_device.setdefault(_norm(name), []).append((entity_id, domain, info["integration"]))


def find_device_entities(name):
    """All (entity_id, domain, integration) tuples for devices matching
    `name` (exact normalized match only -- no fuzzy guessing)."""
    return _by_device.get(_norm(name), [])


def resolve_control_entity(name, preferred_domains=("switch", "light")):
    """Best single entity to call a service on for a given device name.
    Picks the matching domain first, then the best (lowest-priority-
    number) integration. Returns None if nothing matches."""
    candidates = find_device_entities(name)
    if not candidates:
        return None
    for domain in preferred_domains:
        in_domain = [c for c in candidates if c[1] == domain]
        if in_domain:
            in_domain.sort(key=lambda c: INTEGRATION_PRIORITY.get(c[2], 99))
            return in_domain[0]
    # fall back to any domain, best integration
    candidates = sorted(candidates, key=lambda c: INTEGRATION_PRIORITY.get(c[2], 99))
    return candidates[0]


def resolve_scene(name):
    """scene.<slug> entity_id for a Tuya scene name, or None."""
    for entity_id, domain, _integration in find_device_entities(name):
        if domain == "scene":
            return entity_id
    return None


if __name__ == "__main__":
    import sys

    for name in sys.argv[1:]:
        print(f"{name!r}: {find_device_entities(name)}")
