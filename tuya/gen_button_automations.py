#!/usr/bin/env python3
"""Generate HA automations for every (switch, button, gesture) binding in
switch_bindings.json, using the real event.<device>_button_<N> entities
HA's Tuya cloud integration already exposes for these scene switches --
no Zigbee re-pairing needed, see MIGRATION.md's "Zigbee scene switches"
section for how this was discovered.

Output: automations_buttons.yaml -- review before pasting into HA config
(automations: !include automations_buttons.yaml, or merge into your
existing automations.yaml).
"""
import json
import re
from pathlib import Path

import yaml
from ha_resolve import find_device_entities, resolve_control_entity, resolve_scene

GESTURE_TO_EVENT_TYPE = {"single": "click", "double": "double_click", "hold": "press"}

# Sub-channel entities that can't be told apart by device name alone --
# confirmed by hand against the live HA registry (see MIGRATION.md).
CHANNEL_OVERRIDES = {
    ("Pw Bedroom", "Cam"): "switch.pwsp_cam",
    ("Pw Bedroom", "lamp"): "switch.bedroom_lamp",
    ("Pw Bedroom", "charger"): "switch.pwsp_charger",
    ("Pw Bedroom", "usb"): "switch.bedroom_usb",
    # Unconfirmed guess (SwB Smart plug only exposes generic socket_1/2,
    # no custom names) -- ordered by first-mention in the dictation.
    ("SwB Smart plug", "feli"): "switch.swb_smart_plug_socket_1",
    ("SwB Smart plug", "clean"): "switch.swb_smart_plug_socket_2",
}

UNRESOLVED_WARNINGS = []


def find_button_event_entity(switch_name, button_num):
    for entity_id, domain, _integration in find_device_entities(switch_name):
        if domain == "event" and entity_id.endswith(f"_button_{button_num}"):
            return entity_id
    return None


def brightness_pct(v):
    return int(v.rstrip("%"))


def color_temp_kelvin(v):
    pct = int(v.rstrip("%")) / 100
    return round(2700 + pct * (6500 - 2700))


def build_light_service_data(attrs):
    data = {}
    if "brightness" in attrs:
        data["brightness_pct"] = brightness_pct(attrs["brightness"])
    if "color_temp" in attrs:
        data["color_temp_kelvin"] = color_temp_kelvin(attrs["color_temp"])
    if attrs.get("mode") == "color" and "color" in attrs:
        data["color_name"] = attrs["color"]
    return data


def resolve_action_target(action, switch_name_for_context):
    """Returns (service, entity_id, extra_data) or None (unresolved, logged)."""
    kind = action["type"]
    target = action["target"]
    act = action.get("action")

    if kind == "scene":
        eid = resolve_scene(target)
        if not eid:
            UNRESOLVED_WARNINGS.append(f"scene not found: {target!r}")
            return None
        return "scene.turn_on", eid, {}

    if kind == "device":
        channel = action.get("channel")
        if channel:
            eid = CHANNEL_OVERRIDES.get((target, channel))
            if not eid:
                UNRESOLVED_WARNINGS.append(f"unresolved channel: {target!r} / {channel!r}")
                return None
        else:
            dp = action.get("dp")
            candidates = find_device_entities(target)
            if dp and len(candidates) > 1:
                # dp like "switch_1" -> look for an entity ending in _1 etc.
                num = re.search(r"\d+", dp)
                num = num.group(0) if num else None
                matched = [c for c in candidates if c[1] == "switch" and num and c[0].endswith(f"_{num}")]
                eid = matched[0][0] if matched else None
            else:
                resolved = resolve_control_entity(target)
                eid = resolved[0] if resolved else None
            if not eid:
                UNRESOLVED_WARNINGS.append(f"unresolved device: {target!r} (dp={dp})")
                return None

        domain = eid.split(".")[0]
        if domain == "light":
            attrs = action.get("attributes")
            if attrs:
                return "light.turn_on", eid, build_light_service_data(attrs)
            if act == "toggle":
                return "light.toggle", eid, {}
            return (f"light.turn_{act}", eid, {})
        else:  # switch
            if act == "toggle":
                return "switch.toggle", eid, {}
            return (f"switch.turn_{act}", eid, {})

    UNRESOLVED_WARNINGS.append(f"unknown action type: {action}")
    return None


def main():
    ha_dir = Path(__file__).parent / "tuya_export" / "ha"
    bindings = json.loads((ha_dir / "switch_bindings.json").read_text(encoding="utf-8"))["switches"]
    automations = []

    for switch_name, sw in bindings.items():
        for button_num, gestures in sw["buttons"].items():
            event_entity = find_button_event_entity(switch_name, button_num)
            if not event_entity:
                UNRESOLVED_WARNINGS.append(
                    f"no event entity for {switch_name} button {button_num} "
                    f"(gestures defined: {[g for g,a in gestures.items() if a]})"
                )
                continue

            for gesture in ("single", "double", "hold"):
                actions = gestures.get(gesture)
                if not actions:
                    continue
                event_type = GESTURE_TO_EVENT_TYPE[gesture]

                ha_actions = []
                for action in actions:
                    resolved = resolve_action_target(action, switch_name)
                    if not resolved:
                        continue
                    service, entity_id, data = resolved
                    step = {"action": service, "target": {"entity_id": entity_id}}
                    if data:
                        step["data"] = data
                    ha_actions.append(step)

                if not ha_actions:
                    continue

                slug = re.sub(r"[^a-z0-9]+", "_", switch_name.lower()).strip("_")
                automations.append(
                    {
                        "id": f"{slug}_b{button_num}_{gesture}",
                        "alias": f"{switch_name} button {button_num} {gesture}",
                        "triggers": [
                            {
                                "trigger": "state",
                                "entity_id": event_entity,
                                "attribute": "event_type",
                                "to": event_type,
                            }
                        ],
                        "conditions": [],
                        "actions": ha_actions,
                        "mode": "single",
                    }
                )

    out_path = ha_dir / "automations_buttons.yaml"
    with open(out_path, "w", encoding="utf-8") as fh:
        yaml.dump(automations, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)

    print(f"Wrote {len(automations)} automation(s) to {out_path}")
    if UNRESOLVED_WARNINGS:
        print(f"\n{len(UNRESOLVED_WARNINGS)} unresolved item(s) -- NOT included in the output, review:")
        for w in UNRESOLVED_WARNINGS:
            print("  -", w)


if __name__ == "__main__":
    main()
