#!/usr/bin/env python3
"""Back up every Tuya cloud scene as native HA config (scene:/script:),
independent of Tuya staying alive -- see LIMITS.md's Tuya Cloud IoT Core
subscription risk and MIGRATION.md. The live scene.<slug> entities HA's
Tuya integration exposes are proxies to Tuya's cloud; if that subscription
lapses, those entities and everything they do disappear with no local
record unless captured here.

DP-code -> HA attribute conversions, confirmed against real scene data
and live entity attributes (not guessed):
  switch_1..N   -> switch entity (number-suffix matched), on/off
  switch_led    -> light entity, on/off
  mode          -> climate entity's preset_mode (manual/auto/holiday --
                   confirmed via climate.heat_study's preset_modes list,
                   NOT hvac_mode)
  temp_set      -> climate entity's temperature, raw/10 (200->20.0C,
                   confirmed: scene "Heat 20" sets temp_set=200)
  bright_value_v2 -> light entity's brightness (0-255), raw/10 = percent
                   (confirmed: "Desk light full"/"full max" use 1000 =
                   100%; "Desk light dim" uses 40 = 4%)
  colour_data   -> light entity's hs_color + brightness, parsed from
                   '{"h":,"s":,"v":}' JSON string (h 0-360 direct,
                   s raw/10 = percent, v raw/1000*255 = brightness 0-255)
  work_mode     -> dropped (white/colour is implied by which other
                   attributes are set, no separate HA field needed)
  alarm_volume  -> select entity's state, used as-is (confirmed
                   select.siren_volume options include 'middle'/'mute'
                   matching Tuya's raw strings exactly, no translation)

Scenes using only dpIssue -> native `scene:` entry.
Scenes using 'toggle' or 'armedState' -> `script:` entry (scene: can't
express a relative toggle or a non-entity concept like Tuya's home-level
Security arm/disarm). armedState actions are dropped with a comment --
no HA equivalent, see MIGRATION.md's note on recreating it natively.
Scenes with empty actions (IR-remote scenes) can't be backed up at all --
listed separately, not silently skipped.
"""
import json
import re
from pathlib import Path

import yaml
from ha_resolve import find_device_entities

EXPORT = sorted(Path("tuya_export").glob("tuya_export_*.json"))[-1]
data = json.loads(EXPORT.read_text(encoding="utf-8"))
detail = data["devices"]["detail"]
scenes = data["scenes"]["by_home"]["77375906"]

UNRESOLVED = []
NOT_BACKED_UP = []
ARMED_STATE_DROPPED = []


def device_name(device_id):
    return detail.get(device_id, {}).get("name", device_id)


def find_entity_for_code(name, code):
    candidates = find_device_entities(name)
    if not candidates:
        return None
    if code.startswith("switch_") and code[7:].isdigit():
        num = code[7:]
        for eid, domain, _integ in sorted(candidates, key=lambda c: 0 if c[2] == "localtuya" else 1):
            if domain == "switch" and (eid.endswith(f"_{num}") or eid.endswith(f"_switch_{num}")):
                return eid, domain
        # single-switch devices (e.g. a plain socket) often have just one
        # switch entity with no number suffix at all
        sw = [c for c in candidates if c[1] == "switch"]
        if len(sw) == 1:
            return sw[0][0], "switch"
        return None
    if code == "switch_led":
        li = [c for c in candidates if c[1] == "light"]
        if li:
            li.sort(key=lambda c: 0 if c[2] == "localtuya" else 1)
            return li[0][0], "light"
        return None
    if code in ("mode", "temp_set"):
        cl = [c for c in candidates if c[1] == "climate"]
        return (cl[0][0], "climate") if cl else None
    if code in ("bright_value_v2", "colour_data", "work_mode"):
        li = [c for c in candidates if c[1] == "light"]
        if li:
            li.sort(key=lambda c: 0 if c[2] == "localtuya" else 1)
            return li[0][0], "light"
        return None
    if code == "alarm_volume":
        se = [c for c in candidates if c[1] == "select"]
        return (se[0][0], "select") if se else None
    return None


def build_entity_attrs(device_name_, code, value):
    resolved = find_entity_for_code(device_name_, code)
    if not resolved:
        if code != "work_mode":  # work_mode is intentionally droppable
            UNRESOLVED.append(f"{device_name_} / {code}={value!r}")
        return None, {}
    entity_id, domain = resolved

    if code.startswith("switch_") or code == "switch_led":
        return entity_id, {"state": "on" if value else "off"}
    if code == "mode":
        return entity_id, {"preset_mode": value}
    if code == "temp_set":
        return entity_id, {"temperature": value / 10}
    if code == "bright_value_v2":
        return entity_id, {"brightness": round(value / 10 / 100 * 255)}
    if code == "colour_data":
        hsv = json.loads(value)
        return entity_id, {
            "hs_color": [hsv["h"], round(hsv["s"] / 10)],
            "brightness": round(hsv["v"] / 1000 * 255),
        }
    if code == "alarm_volume":
        return entity_id, {"state": value}
    if code == "work_mode":
        return None, {}
    UNRESOLVED.append(f"{device_name_} / unhandled code {code}={value!r}")
    return None, {}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


hass_scenes = []
hass_scripts = []

for s in scenes:
    name = s["name"]
    actions = s.get("actions", [])
    executors = {a["action_executor"] for a in actions}

    if not actions:
        NOT_BACKED_UP.append(f"{name} -- empty actions (IR-remote scene, content not visible via API at all)")
        continue

    if executors <= {"dpIssue"}:
        entities = {}
        for a in actions:
            dn = device_name(a["entity_id"])
            for code, value in (a.get("executor_property") or {}).items():
                eid, attrs = build_entity_attrs(dn, code, value)
                if eid:
                    entities.setdefault(eid, {}).update(attrs)
        if entities:
            hass_scenes.append({"id": slug(name), "name": name, "entities": entities})
        continue

    # toggle / armedState present -> script, not scene
    seq = []
    dropped_armed_state = False
    for a in actions:
        ex = a["action_executor"]
        if ex == "armedState":
            dropped_armed_state = True
            continue
        dn = device_name(a["entity_id"])
        if ex == "toggle":
            code = next(iter((a.get("executor_property") or {}).keys()), None)
            resolved = find_entity_for_code(dn, code) if code else None
            if not resolved:
                UNRESOLVED.append(f"{dn} / toggle {code}")
                continue
            eid, domain = resolved
            seq.append({"action": f"{domain}.toggle", "target": {"entity_id": eid}})
        elif ex == "dpIssue":
            for code, value in (a.get("executor_property") or {}).items():
                eid, attrs = build_entity_attrs(dn, code, value)
                if not eid:
                    continue
                domain = eid.split(".")[0]
                if "state" in attrs and attrs["state"] in ("on", "off"):
                    seq.append({"action": f"{domain}.turn_{attrs['state']}", "target": {"entity_id": eid}})
                else:
                    seq.append({"action": f"{domain}.turn_on", "target": {"entity_id": eid}, "data": attrs})
    if seq:
        hass_scripts.append({slug(name): {"alias": name, "sequence": seq}})
        if dropped_armed_state:
            ARMED_STATE_DROPPED.append(name)

ha_dir = Path(__file__).parent / "tuya_export" / "ha"
(ha_dir / "scenes_backup.yaml").write_text(
    yaml.dump(hass_scenes, allow_unicode=True, sort_keys=False, default_flow_style=False),
    encoding="utf-8",
)
scripts_merged = {}
for s in hass_scripts:
    scripts_merged.update(s)
scripts_header = (
    "# Backed up from Tuya cloud scenes (gen_scenes_backup.py). Scenes "
    "using 'toggle' or 'armedState' can't be plain HA scene: entries, so\n"
    "# they're scripts instead.\n"
)
if ARMED_STATE_DROPPED:
    scripts_header += (
        f"# NOTE: {', '.join(ARMED_STATE_DROPPED)} originally also toggled "
        "Tuya's home-level Security arm/disarm state -- dropped here, no\n"
        "# HA equivalent exists. See MIGRATION.md's armed-state note if you "
        "want to recreate it natively (e.g. Manual Alarm Control Panel).\n"
    )
(ha_dir / "scripts_backup.yaml").write_text(
    scripts_header + yaml.dump(scripts_merged, allow_unicode=True, sort_keys=False, default_flow_style=False),
    encoding="utf-8",
)

print(f"Wrote {len(hass_scenes)} scene(s) -> {ha_dir / 'scenes_backup.yaml'}")
print(f"Wrote {len(scripts_merged)} script(s) -> {ha_dir / 'scripts_backup.yaml'}")
print(f"\n{len(NOT_BACKED_UP)} scene(s) NOT backed up at all:")
for w in NOT_BACKED_UP:
    print("  -", w)
if UNRESOLVED:
    print(f"\n{len(UNRESOLVED)} unresolved dp(s) (skipped, not included):")
    for w in UNRESOLVED:
        print("  -", w)
