# Tuya → Home Assistant migration plan

Goal: move as much of the household off Tuya cloud as possible, keeping
Alexa (via HA) working throughout. Tuya stays only for devices that
genuinely can't be moved (no local protocol, or not worth the hardware
swap yet).

## Device buckets

**1. Zigbee (behind a Tuya gateway today)** — re-pair directly to HA's own
Zigbee radio (already underway; several devices done). Fully local once
moved, no Tuya dependency at all. Includes: door/window contacts, PIR,
water leak sensors, TRVs/heaters, wall switches, dimmers, LED bulbs, the
`Siren`, several of the smoke detectors (the ones with `sub: true` in the
export), and the Zigbee repeaters/gateways themselves become obsolete once
their children are re-paired.

**2. WiFi/IP Tuya devices with local control (LocalTuya)** — stay
physically as-is, HA talks to them over LAN instead of Tuya's cloud. No
hardware change, removes cloud dependency for that device. This is where
`tuya/export.ipynb` + `tuya/localtuya_config.ipynb` do the heavy lifting:
cloud export → LAN discovery → dp_id resolution → ready-to-import
templates in `tuya_export/localtuya_templates/`.

**3. WiFi/IP Tuya devices, cloud-only** — no local port response, or the
handshake genuinely fails. Stay on HA's official Tuya cloud integration.
Minimize how much lives here, since that integration is the one you've
seen go unresponsive/stop-listening (known weak point: its pubsub
subscription to Tuya's message bus, not something worth chasing a fix
for per-device).

**4. The `ph4_tuyaopen_esp32bridge` relay board** — two distinct uses,
don't conflate them:
- *Physical relay replacement*: only for loads that can be rewired through
  its relay/momentary outputs. Doesn't apply to devices with a sealed
  Tuya WiFi module (e.g. the Hevolta sockets, the LED strip) — the bridge
  can't intercept those.
- *Cloud-event-to-local-HA relay*: confirmed viable — the existing Tuya
  account already has an automation of exactly this shape ("Motion
  Corridor PIR → `dpIssue` on PwC doorLight's `switch_1`", see
  `tuya_export/tuya_export_*.json`'s `automations.detail`). So: a Tuya-side
  automation on any bucket-3 device can `dpIssue` onto one of the bridge's
  spare switch channels, and the bridge's MQTT side turns that into a
  local HA binary_sensor — without depending on HA's flaky cloud
  integration for that signal. **The real bridge's Tuya identity is the
  device named "Ph4BridgeSwitch 2" (product `Ph4BridgeSwitch`) — 12
  `switch_N` DPs; look up its device_id in the local (gitignored)
  `tuya_export/` snapshot when needed, don't hardcode it here.**
  (Corrected below: the `*-vdevo` devices are
  unrelated leftovers, not this board.)

**LED strip**: stays in bucket 3. Don't try to proxy RGB through the
binary-only bridge. Build a couple of Tuya "favorite scenes" (presets) and
trigger them from HA via a `dpIssue`/`triggerScene` automation, same
mechanism as above.

**"Armed state" bridging**: not yet identified in the exported automations
— none of the 6 automations reference anything called "armed". Likely the
Tuya/SmartLife app's own Security/SOS panel rather than a DP on a specific
device. Needs the specific device/app screen pointed out before it can be
wired to a bridge channel.

## Advanced device settings (inching, timers, reports) — do we still need Tuya?

Short answer: for WiFi devices, yes for some things, and that's fine —
cloud and local control coexist on the same device rather than being
exclusive. For Zigbee, no, but it's a one-way door.

### WiFi/LocalTuya devices: cloud and local are not exclusive

Adding a device to LocalTuya does **not** unlink it from the Tuya
account. The device's firmware keeps running two independent control
channels at the same time against the same underlying DP state:

- a cloud MQTT session back to Tuya (app, scenes, cloud automations,
  remote access)
- a local TCP listener on port 6668 (LocalTuya, our scripts, anything
  else on the LAN)

This isn't theoretical — we've already observed it directly: `PwC
doorLight` / `PwB WashingMachine` / etc. are sitting in HA's LocalTuya
right now (holding a local session) *and* still show up live in the
Tuya cloud export and would still fire the existing `dpIssue`
automations found earlier in this doc. Nothing about adding LocalTuya
touched their cloud presence.

So for a device like `PwC doorLight`, here's what's actually reachable
where:

| Capability | LocalTuya-accessible? | Why |
|---|---|---|
| On/off, read current state | Yes | plain DP read/write (`switch_1`) |
| Power monitoring (`cur_power`/`cur_voltage`/`cur_current`/`add_ele`) | Yes | plain periodic DP reports, no cloud needed |
| `fault`, `child_lock`, `relay_status` (power-on behavior) | Yes | plain DP values — raw booleans/enum strings, no nice UI but functional |
| **Inching / auto-off timer** (`switch_inching`) | **No, not really** | value is an **opaque encoded binary blob** the app constructs from a "duration" field in its UI; LocalTuya only shows/sets the raw string, it doesn't know the encoding |
| **Cycle timer / random timer** (`cycle_time`/`random_time`) | **No** | same story — encoded schedule blob, app-only to configure |
| Scheduled "Timer" tab in the app (separate from the DP-level countdown) | No — cloud-only | these are cron jobs living in Tuya's cloud that fire a `dpIssue` at the scheduled time; if Tuya's cloud is down or the device is unlinked, they silently don't fire |
| Firmware OTA updates | No — cloud-only | always pushed over the cloud channel |

Practical rule: once an inching duration or a cycle/random timer is set
*through the app*, the device executes it locally from then on (its own
MCU/RTC, no live cloud dependency to *run* it) — but to *change* that
setting again later, the app/cloud is needed. Day-to-day switching is
fully local and cloud-independent either way.

**Maintenance caveat**: if a device is ever removed/factory-reset from
the Tuya app, its `local_key` rotates, breaking LocalTuya until the
export is re-run. So keeping a device in the app isn't entirely a
non-event — just don't tap "remove device" casually on anything also
wired into LocalTuya.

### Zigbee: this is the actual one-way door

This is the real asymmetry vs. WiFi. Once a Zigbee device is re-paired
from Tuya's gateway directly to HA's own Zigbee coordinator, there is
**no cloud, no app, and no dual-homing option** — it's a different
Zigbee network entirely than Tuya's gateway was running. No "one foot in
each" the way WiFi devices allow.

Tuya's Zigbee devices lean heavily on a manufacturer-specific cluster
(`0xEF00`, often called "the Tuya cluster") that carries DP-like raw data
over Zigbee, the same way the WiFi devices do over TCP. Whether a given
advanced feature (a TRV calibration offset, an LED effect, an uncommon
config bit) is reachable depends entirely on whether HA's Zigbee stack
has a **quirk** (ZHA) or **converter** (Zigbee2MQTT) written for that
exact feature on that exact device. If nobody's written it, it's just
not reachable — there's no cloud fallback to lean on, since the device
isn't Tuya's to talk to at all after re-pairing.

**Takeaway**: WiFi → LocalTuya migration is low-risk and effectively
reversible (cloud stays as a free, permanent config/advanced-feature
fallback). Zigbee migration is a one-time, more final decision — worth
checking a device's ZHA quirk or Z2M converter coverage *before*
re-pairing it if it has any non-obvious settings relied on, since
there's no "ask the cloud" fallback afterward (though the device can
always be re-paired back to Tuya's gateway if a feature turns out to be
missing).

## Zigbee scene switches (click/double-click/press mapping)

**Major update (2026-10-11), supersedes most of the "need to re-pair to
Zigbee" framing below**: once live HA API access was available, checking
the actual entity registry showed that **HA's Tuya cloud integration
already exposes a clean `event.<device>_button_<N>` entity per button**,
for all 10 switches, with `event_type` attribute values `click` /
`double_click` / `press` — i.e. a proper, triggerable button-press event,
*today*, with zero Zigbee re-pairing needed. This was found by querying
`config/entity_registry/list` over HA's WebSocket API (not visible via
plain REST `/api/states` domain counts, which is why it was missed
earlier) and cross-checking against a live Zigbee2MQTT instance's
`zigbee2mqtt/bridge/devices` retained MQTT message, which confirmed Z2M
only knows about *2 different, separately-named* devices
(`switch4corr`/`switch4StudyDesk`, via a totally separate coordinator) --
not these 10 at all. The event entities are a cloud-integration feature,
independent of Zigbee2MQTT/ZHA entirely.

Practical effect: `automations_buttons.yaml` (generated by
`gen_button_automations.py` from `switch_bindings.json`) is **real,
working automation config, usable immediately** — not a draft waiting on
migration. The "re-pair to get a usable trigger" tradeoff described below
still applies to *other* Zigbee features (advanced config, going fully
local), just not to basic button-press automation, which this cloud
feature already solves.

Also discovered while reconciling against Z2M: `switch4corr` and
`switch4StudyDesk` (Z2M device names) are almost certainly `SwC corridor`
and `SwLDesk` by location/button-count match — i.e. **two of these 10 are
already separately re-paired to a standalone Zigbee2MQTT instance** too,
alongside their still-working Tuya cloud event entities (dual presence,
same pattern as WiFi dual-homing). `SwLDesk`'s real Zigbee model is
`TS004F` (not the `TS0042`/`TS0044` family guessed below) — confirmed
Z2M-supported, needs its `operation_mode` select set correctly to emit
actions (already configured correctly, per its live `select.operation_mode`
entity).

The original (now partly superseded) research follows, kept for the
hardware/compatibility details which are still accurate:

The household has **10 battery Zigbee scene switches** (Tuya category
`wxkg`, 1/2/4-button), e.g. `SwB wall`, `SwL obyvacka`, `SwC corridor`.
Each button already reports its own gesture as a DP today
(`switch_mode1`/`switch_mode2`/... = `click` / `double_click` / `press`),
confirmed directly from the cloud export.

**Model/compatibility**: 8 of the 10 are `TSL-SWI-SCENEZG2` (2-button) or
`TSL-SWI-SCENEZG4` (4-button), and are very likely Tesla-Smart rebrands
of Tuya's well-supported Zigbee2MQTT/ZHA `TS0042`/`TS0044` scene
switches — confirmed by Tesla's own documented `TSL-SEN-BUTTON` = `TS0041`
(1-button) rebrand precedent (same naming pattern, same brand), both of
which expose exactly the `1_single`/`1_double`/`1_hold` style HA actions
already matching the single/double/press granularity these devices
report today. **Not yet verified by actually pairing one** — cheap and
reversible to check (join one to the HA coordinator; if it doesn't come
up as a proper multi-button device, re-pair back to Tuya's gateway, no
harm done). Two outliers don't fit this pattern and need individual
checking: `SwS Round` (1-button, no model string reported at all,
different product_id, battery at 40% — worth replacing before
migrating either way) and `SwLDesk` (1-button, model `07506L` — a
completely different naming scheme, not a Tesla TS0041/42/44 rebrand).

**The one unrecoverable piece, verified (not just inferred)**: the cloud
export's `scene_bindings` came back empty for all 10 switches, so this
was checked directly rather than assumed — called
`GET /v1.0/devices/{device_id}/scenes` (the real, documented endpoint,
already what the export notebook uses) against all 10 device_ids
individually: every one returns `success: true, result: {}` — a valid,
authenticated, genuinely-empty response, not a permission/subscription
error (compared against several wrong-endpoint guesses, which all came
back `success: false, code: 1108 "uri path invalid"` — a clearly
different, recognizable failure mode). Also checked whether button
bindings might secretly be modeled as regular Tuya **automations**
instead (condition on a switch's `switch_modeN` DP) — none of the 7
automations in this account reference any of these 10 device_ids at
all. So this isn't a cloud-export gap: **the button→scene mapping isn't
stored as a cloud object for these devices at all.** Most consistent
explanation: Tuya's Zigbee scene-switches are designed to keep working
without internet, which is only possible if the Zigbee gateway stores
and executes the binding itself, locally — a firmware/hardware
constraint, not a permissions or API-coverage gap. It cannot be
recovered once a switch is removed from Tuya, so **each switch's
current button→action mapping must be read out of the SmartLife/Tuya
app manually, per switch, before re-pairing it**.

**Two paths, same tradeoff as the general Zigbee case above**:
- Stay on Tuya, flip the switch's `mode` DP to `remote_control` (two of
  the ten — `SwL obyvacka`, `SwS pracovna` — are currently
  `wireless_switch`, meaning the gateway likely consumes button presses
  locally via its own scene-binding and won't surface them as DP changes
  at all), then read `switch_modeN` via HA's Tuya cloud integration.
  Zero re-pairing, but inherits the cloud reliability problem — a bad
  fit for something expected to respond instantly, physically.
- Re-pair to HA's own Zigbee coordinator (recommended, matches the
  stated "as local as possible" goal). Once paired, Z2M/ZHA expose these
  as proper **HA device triggers** (Automations UI → "Device" trigger →
  pick switch → pick e.g. "button 2 double pressed") — no manual
  YAML/entity-state wrestling, unlike the cloud route above.

**Worklist**: `scene_switches_worklist.py` generates `SCENE_SWITCHES.md`
— one section per switch with model/button-count/battery/mode and a
table to fill in (current trigger, from the app; desired HA action)
before migrating each one. Re-run it after a fresh cloud export to pick
up new switches or updated last-pressed state.

## Tooling already built (in this directory)

- `export.ipynb` — pulls a full Tuya cloud snapshot (devices, DPs, scenes,
  automations) via the OpenAPI. See `README-export.md`.
- `localtuya_config.ipynb` — turns that snapshot into LocalTuya entity
  configs, using LAN polling (tinytuya) to resolve numeric dp_ids that the
  cloud API never exposes for Smart Home accounts. See
  `README-localtuya.md`.
- Output: `tuya_export/localtuya_*.json` / `.yaml` / `.md`, and one
  ready-to-import template per device in
  `tuya_export/localtuya_templates/*.yaml`.

## Repeating this in N years (what's actually needed to re-run the export)

Everything below was verified against the real code (not assumed) on
2026-09-29 — `export.ipynb`'s and `tuya_bind_device.ipynb`'s exact
`os.environ[...]` reads were checked directly, and `.env.example` was
previously **wrong** (said `TUYA_ACCESS_SECRET`/`TUYA_BASE_URL`, but the
actual export code reads `TUYA_ACCESS_KEY`/`TUYA_API_ENDPOINT`) — now
fixed to match reality.

### 1. A Tuya IoT Platform developer account + Cloud Project

- Account at [iot.tuya.com](https://iot.tuya.com) (free).
- A Cloud Project under **Cloud → Development → Create Cloud Project**.
  **The project's Data Center/region must match the region the
  Smart Life/Tuya Smart app account is registered in** (EU, in this
  household) — picking the wrong one means the device-linking step below
  fails with a permission error, and there's no way to change a project's
  region after creation (have to make a new one).
- Industry: "Smart Home" — this determines which API products
  (IoT Core, Authorization, etc.) get auto-subscribed.

**This project's IoT Core subscription is very likely the same
free-trial-that-needs-manual-renewal documented in
`ph4_tuyaopen_esp32bridge/LIMITS.md`** (if the same Cloud Project is
reused for both the bridge and this export tooling — worth confirming
which project is which before assuming). If that trial has lapsed by the
time this is re-run, the API calls in `export.ipynb` will simply fail —
check **Cloud → Project Management** and renew first if so.

### 2. Link the real Tuya Smart/SmartLife app account to the project

The project's own API credentials can't see your devices until the app
account that actually owns them is linked:

- In the Cloud Project: **Devices → Link Tuya App Account** (exact label
  varies by console version) → shows a QR code → scan it with the
  Tuya Smart or SmartLife app (whichever one the real devices are in)
  while logged into the account that owns them.
- After linking, a **Users** tab appears showing that app account's real
  UID — this is `TUYA_APP_USER_UID`. Don't confuse it with the Cloud
  Project's own service-account `uid` (`connect()`'s return value, see
  `README-export.md`'s gotcha #2) — they look similar but are different
  things and are not interchangeable.

### 3. Credentials → `.env` at the **repo root** (not `tuya/.env`)

`export.ipynb` does `load_dotenv("../.env")`, i.e. one level up from this
directory. See the corrected `tuya/.env.example` for the exact variable
names (`TUYA_ACCESS_ID`, `TUYA_ACCESS_KEY`, `TUYA_APP_USER_UID`, etc.) --
`TUYA_ACCESS_ID`/`TUYA_ACCESS_KEY` come from the Cloud Project's own
**Overview** page (labelled "Access ID"/"Access Secret" there).

### 4. Software — pinned in `tuya/requirements.txt`

`tuya-connector-python` (cloud OpenAPI calls, `export.ipynb`) and
`tinytuya` + `PyYAML` (LAN polling / dp_id resolution / template
generation, `localtuya_config.ipynb`), plus `python-dotenv`. Versions
matter — both `tinytuya`'s local protocol handling and
`tuya-connector-python`'s request-signing scheme have changed across
versions before, so install from the pinned file rather than latest:
`pip install -r tuya/requirements.txt`.

### 5. Physical requirement: LAN presence

The cloud API **never** returns numeric `dp_id`s for Smart Home consumer
devices (see `README-localtuya.md`'s "Known issues" section) — this is
not a credentials/permissions problem, no API key fixes it. Resolving
dp_ids requires actually running `localtuya_config.ipynb`'s polling
cells (or `read_all_status.py`/the rescan scripts) **from a machine on
the same LAN subnet as the devices**. An API key alone gets you device
lists, names, and `local_key`s — not working LocalTuya configs.

### Summary: what you actually need

1. Tuya IoT Platform account + Cloud Project (right region).
2. That project's Access ID / Access Secret, in `.env` at the repo root.
3. The Smart Life/Tuya Smart app account linked to the project (one-time
   QR scan), giving `TUYA_APP_USER_UID`.
4. The project's IoT Core subscription currently active (check/renew
   first if it's been a while).
5. `pip install -r tuya/requirements.txt`.
6. Physical presence on the household LAN to resolve dp_ids — the API
   key alone is not sufficient for that step.

## Status snapshot (2026-09-28)

Of 28 WiFi devices in the last localtuya conversion run, only 1
(`LED top`) came out fully resolved. Re-running dp_id resolution today for
every device with a *known* LAN IP (`10.0.1.x`) found:

| Device | Result |
|---|---|
| Pw Bedroom | already fully resolved (protocol 3.3) |
| SwS plug hobby | already resolved (protocol 3.3) |
| PwL Corner R / Kettle L / Long R Microwave / short L / short R | resolved (protocol 3.3) — same product family, single switch + countdown |
| **PwB WashingMachine** | **fixed** — needed protocol **3.4**, not 3.3 |
| **PwC doorLight** | **fixed** — needed protocol **3.4** |
| **PwL Couch main** | **fixed** — needed protocol **3.4** |
| **Terrace socket** | **fixed** — needed protocol **3.4**; full dp map resolved and written back to the templates (see below) |
| Pw Study desk | **dropped** — this device physically burned down and has been replaced by a Shelly Matter power strip, already connected to HA directly. Remove from the Tuya migration tracking entirely. |

**Root cause of the "broken" devices**: not a network/reachability
problem — all of them answered on the LAN immediately. It was a **Tuya
protocol version mismatch**: `tinytuya`/localtuya defaults to `3.3`, but
this batch of devices (all sharing the same two product templates --
generic energy-monitoring-socket hardware, IDs in the local export)
speaks `3.4`. `3.3` doesn't just fail cleanly — it returns "Unexpected
Payload from Device" (Err 904), which looks like a broken/incompatible
device rather than a version mismatch unless you try the other versions.

**Still unresolved**: none with a known LAN IP, after this pass.

### Terrace socket — full DP map (protocol 3.4)

Resolved by cross-referencing raw LAN dp values against the cloud-known
DP codes (`devices_status`) for this device:

| dp_id | code | notes |
|---|---|---|
| 1 | switch_1 | |
| 9 | countdown_1 | |
| 17 | add_ele | cumulative energy, kWh, scaling from spec |
| 18 | cur_current | mA |
| 19 | cur_power | W — **scaling corrected 0.01 → 0.1** (see below) |
| 20 | cur_voltage | V — **scaling corrected 0.01 → 0.1** (see below) |
| 21 | *(unmapped)* | not in cloud DP list; likely an internal calibration/test bit, not user-relevant |
| 22–25 | voltage_coe / electric_coe / power_coe / electricity_coe | calibration constants, not useful in HA |
| 26 | fault | bitmask, 0 = no fault |
| 38 | relay_status | **enum string** (`off`/`on`/`memory`) — power-restore-after-outage behavior, **not** a live switch mirror. Mapped to a localtuya `switch` entity in the template for completeness, but that will likely misreport state since it's not boolean. Consider dropping this entity, or using a `select`/`sensor` platform instead. |
| 40 | light_mode | |
| 41 | child_lock | |
| 42 | cycle_time | |
| 43 | random_time | |
| 44 | switch_inching | |

**Scaling bug found and fixed**: the generator's power/voltage scaling for
this device came out as `0.01`, but the raw voltage reading (`2426`) only
makes physical sense as `242.6 V` (`× 0.1`) — `× 0.01` would be `24.26 V`,
impossible for EU mains. Corrected `cur_voltage` and `cur_power` scaling
to `0.1` in both `localtuya_20260308_000703.json` and
`localtuya_templates/Terrace socket.yaml`. **Power scaling was corrected
by analogy (same device, same coefficient convention) but wasn't verified
against a live nonzero reading** — worth confirming once something is
actually plugged in and drawing power.

Updated files: `tuya_export/localtuya_20260308_000703.json`,
`tuya_export/localtuya_templates/Terrace socket.yaml`.

## Second pass (2026-09-28, later same day): remaining 14 devices + fresh export

Ran a full LAN sweep (UDP broadcast listen, ping+port-6668 scan of the
whole `10.0.1.0/24`, handshake probe with each device's own local_key)
against the 14 devices that had never resolved to a LAN IP. Result:
**1 more resolved** — `PwL Kettle` at `10.0.1.243` (protocol 3.3, same
generic-socket DP layout as the others: switch=1, add_ele=17,
cur_current=18, cur_power=19, cur_voltage=20, relay_status=38,
child_lock=41). **13 still not found**, despite every live host with
Tuya's port 6668 open being accounted for by an already-known device —
ruling out "just needs a different subnet" or "needs more broadcast
retries".

Given the working export was 7 months old (2026-03-07) and one device had
already turned out to be physically destroyed and replaced
(`Pw Study desk`), pulled a **fresh cloud export**
(`tuya_export_20260928_182937.json`) before sinking more time into LAN
discovery against possibly-stale data. Findings:

- **No device_id was removed from the account** — all 13 still-missing
  devices are still registered and still have the *same* `local_key` as
  the March export, so the LAN handshake failures aren't a stale-key
  problem.
- **Two online-status flips**: `Obývačka P56500S 2` was online in March,
  now offline. `Smart Predlžovací prívod - WiFi` was offline in March, now
  **online** — worth a fresh targeted LAN attempt.
- **3 new device_ids** appeared that weren't in the March export:
  - `Portable Air Conditioner` — a genuinely new device, unrelated to this
    migration.
  - `Ph4BridgeSwitch 2` and a second `Ph4BridgeScene-vdevo` device — these
    `vdevo*`-prefixed entries are virtual-bridge
    artifacts left over from a previous (non-`ph4_tuyaopen_esp32bridge`)
    integration attempt, not our real ESP32 board. **Disregard entirely**
    — not something to clean up or migrate.

**Working theory for the 13 non-responders**: since they're confirmed
online-per-cloud (for at least 2 of them) with valid local_keys, yet
invisible to a full subnet+port scan from this machine, the most likely
explanation is **network segmentation** — e.g. these devices joined a
separate/guest/IoT SSID with AP client-isolation, rather than actually
being offline. This is a manual check (look at which SSID/VLAN each is
associated to in your AP's client list), not something more automated
LAN scanning will resolve.

**Retried once more** with the fresh local_keys and a longer (60s)
broadcast window: identical result, 0 new devices found (only the
already-known `PwL Kettle` matched again, same dps as before). Ruling out
"stale key" and "just needed more retries" — **further automated scanning
from this machine won't find these 13 without a network-side change**.
Next real step is the manual AP/VLAN check above, or physically
power-cycling/checking each device, not another scan.

## Tooling added (2026-09-28, later)

- `tuya_local.py` — shared helper, loads device credentials at runtime
  from the newest `tuya_export/localtuya_*.json`. Nothing sensitive is
  hardcoded in any script; `tuya_export/` itself is gitignored (contains
  local_keys, device_ids, MACs, GPS coordinates).
- `terrace_socket_poc.py` — flips Terrace socket on/off 10x with state
  readback each time, verifying LocalTuya control end-to-end. Ran clean,
  10/10.
- `read_all_status.py` — reads live status for every device with a
  resolved LAN IP, with retry-with-backoff for transient connection
  errors.

**Caveat found while testing `read_all_status.py`, root-caused**: several
of the `py9jvqxyay2l0tav`-family single-relay plugs (`PwL Corner R`/
`Kettle L`/`Long R Microwave`/`short L`/`short R`) plus `Pw Bedroom` — all
of which succeeded cleanly in the rescans above — started failing with
`901 Unable to Connect`, consistently, across all 3 protocol versions.
Raw TCP connects fine (`nc` succeeds), which initially looked like a
"defensive lockout" some cheap Tuya devices apply after repeated
connections in a short window -- **that theory was wrong**. The real
cause: **these devices are already added to HA's own LocalTuya
integration**, which holds an open local session to each of them
continuously. These modules only accept one local TCP session at a
time, so any external script (ours) probing the same device collides
with HA's own connection and gets refused -- confirmed directly by an HA
log line the user shared, showing `custom_components.localtuya.common`
repeatedly failing to reach `10.0.1.15` (`Pw Study desk`'s old, now-dead
IP -- a stale LocalTuya entry left over from before that device burned
down and was replaced by a Shelly; harmless but should be removed from
HA to stop the log spam). **This is likely also part of the original
"HA sometimes doesn't listen to Tuya devices" complaint** — not just the
cloud integration's pubsub flakiness, but LocalTuya's single-session
model getting starved when something else (our scripts, or even HA
itself reconnecting) contends for the same socket. Not a data or script
bug: device_id/local_key/protocol_version are all confirmed correct --
it's a "someone else already holds the connection" situation, and these
devices are working fine *for HA*.

**Protocol-version fallback added and confirmed working**: `tuya_local.py`
now has a `connect()` helper that tries `3.3` → `3.4` → `3.1` in order
(the device's own recorded version first) with retries, instead of
trusting a single stored version. Both `terrace_socket_poc.py` and
`read_all_status.py` now use it. Verified end-to-end: `PwB WashingMachine`,
`PwC doorLight`, and `PwL Couch main` — the three devices that previously
needed a manual JSON edit to force protocol 3.4 — now connect
automatically with zero manual patching.

**Final status of the full `read_all_status.py` run** (13 devices with a
resolved LAN IP): **6 succeeded** (`LED top`, `PwB WashingMachine`,
`PwC doorLight`, `PwL Couch main`, `SwS plug hobby`, `Terrace socket`),
**7 failed** — 6 with the HA-contention 901 described above (`Pw Bedroom`,
`PwL Corner R`, `PwL Kettle L`, `PwL Long R Microwave`, `PwL short L`,
`PwL short R`) plus `Pw Study desk` for the separate, expected reason
that it's physically gone. Worth confirming in HA (Settings → Devices &
Services → LocalTuya) that the six contention-failures are indeed
already configured there — if so, nothing is actually broken, they're
just busy serving HA.

**Confirmed by the user's actual HA LocalTuya device list (2026-09-28)**:
all 13 devices with a resolved LAN IP are already there — a 1:1 match,
fully confirming the contention theory above, no exceptions. Diffing
that list against every WiFi device in the export turned up exactly
**one ready-to-add gap: `PwL Kettle`** (distinct from `PwL Kettle L`,
already in HA). Its dp map was captured live in the earlier LAN rescan
(`10.0.1.243`, protocol 3.3) but never written back — now done: full
7-entity dp map resolved and written to
`tuya_export/localtuya_templates/PwL Kettle.yaml`, same voltage/power
scaling correction applied as Terrace socket (`0.01` → `0.1`), same
`relay_status`-is-an-enum caveat noted. Verified live via
`tuya_local.connect()` immediately after writing it back. Ready to
import. Everything else not yet in HA is exactly the "never found on
LAN" set from above (plus the `*-vdevo` leftovers, which stay
disregarded) — still blocked on the manual AP/VLAN check, not on
missing tooling.

## Next steps

1. **Import `Terrace socket` and `PwL Kettle` into LocalTuya now** —
   templates are ready (`tuya_export/localtuya_templates/`), full dp
   maps, live-verified. Consider dropping/reworking the `relay_status`
   entity on both (see caveat above) once imported.
2. **Apply the same protocol-3.4 fix to `PwB WashingMachine`, `PwC
   doorLight`, `PwL Couch main`** — LAN reachability and raw dps are
   already confirmed (see `tuya_export/rescan_results.json`); only the
   code-to-dp_id cross-reference + template regeneration is left, same
   process as Terrace socket above.
3. **Devices with only 1–2 dp_ids missing** (`PwL Corner R` / `Kettle L`
   / `Long R Microwave` / `short L` / `short R` — all missing just
   `relay_status`, non-essential) — usable in HA as-is today; fill in
   `relay_status`'s dp_id later if wanted (same enum caveat as above).
4. ~~`PwL Kettle`~~ — done, see above.
5. **13 devices still invisible on the LAN** despite valid local_keys and
   (for some) cloud-online status: `Garaz dym a CO senzor`, `Kuchyna
   detektor dymu`, `LED desk`, `Obývačka P56500S 2`, `PwC cam`, `PwL Cord
   Couch`, `PwL Gateway`, `PwL cam`, `PwS Study Cam`, `PwS deskLight`,
   `Smart Predlžovací prívod - WiFi`, `Study light`, `SwS heatmat`. **This
   needs a manual/physical check, not more automated scanning** — most
   likely they're on a separate/isolated SSID or VLAN. Check your AP's
   client list for which network each is actually joined to; re-run LAN
   discovery once that's confirmed (worth prioritizing `Smart
   Predlžovací prívod - WiFi` first, since it just flipped online).
6. **Bridge device identity, corrected** — the real physical
   `ph4_tuyaopen_esp32bridge` is the device named `Ph4BridgeSwitch 2`
   (product `Ph4BridgeSwitch`, 12 `switch_N` DPs — the values line up
   with the board's actual current relay state; device_id is in the
   local `tuya_export/` snapshot, not repeated here).
   `Ph4BridgeSwitch-vdevo` and `Ph4BridgeScene-vdevo` are confirmed
   leftover virtual-bridge artifacts from a previous integration attempt
   — **disregard both**, they are not this board and don't need LAN
   polling or DP mapping. Look up `Ph4BridgeSwitch 2`'s device_id from the
   export when wiring a future Tuya-scene → `dpIssue` automation.
8. Confirm the "armed state" device/DP before designing the bridge-relay
   pattern for it.
9. Check whether the Hevolta kitchen sockets are actually in the same two
   product families already proven to work over LocalTuya at protocol
   3.4 (IDs in the local export) — if so, they may not need to
   stay cloud-only after all.
