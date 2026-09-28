# Known limits and long-term risks

## Tuya Cloud dependency: this will not silently keep working for years

This bridge only pairs and syncs DPs through **Tuya's cloud** (SmartLife
app pairing → Tuya cloud MQTT). There is no local-only mode in this design.
Two separate things determine whether it keeps working, and only one is
under our control:

### 1. Per-device license (UUID + AuthKey) — probably fine

Tuya's own docs don't state an expiration for these. They're described as
"for development and debugging" (as opposed to a paid production/
mass-manufacturing license), but no time limit is documented. Constraint
that does apply: each UUID+AuthKey can only have **one device online at a
time** (matches this project's 2 free codes — one per physical unit).

### 2. The Tuya Cloud project's IoT Core subscription — the actual risk

This is tied to the Tuya IoT Platform *project* hosting the product
(`Ph4BridgeSwitch`), not to the device. Since the device always talks
through Tuya's MQTT broker, if this subscription lapses, the bridge stops
syncing even though the device is still powered on and paired.

- New Tuya Cloud projects get a free trial period **commonly reported as
  ~1 month**, after which cloud API access (and the device's own cloud
  connectivity) stops until renewed.
- Renewal can be free (**Cloud → Project Management → Upgrade IoT Core
  Plan → Trial edition ($0.00) → Buy now**, then **Extend trial period** →
  fill out a form → approved within 1-2 business days) — but it is a
  **manual, recurring chore**, not automatic.
- Real-world reports (GitHub issues on `tinytuya` and `tuya-home-assistant`)
  show this occasionally becomes a dead end: the free renewal option stops
  being offered, leaving a choice between paying (tiers users describe as
  steep — quoted figures like $25K/$50K for "Corporate"/"Flagship" editions)
  or losing cloud sync entirely.

**Action item:** set a recurring reminder to check
**Tuya IoT Platform → Cloud → Project Management** and renew before the
subscription lapses. If Tuya ever stops offering free renewal on this
project, the physical device/relays keep working locally, but the Tuya↔HA
bridge stops until the subscription question is resolved one way or another.

Sources:
- [What happens if the free trial period expires or the membership expires?](https://support.tuya.com/en/help/_detail/K9zsoru2a6r0y)
- [Can I continue to use IoT Core after the trial period expires?](https://support.tuya.com/en/help/_detail/Kbm9zue1v7vvu)
- [Instructions to Renew Tuya Trial Subscription (tinytuya #736)](https://github.com/jasonacox/tinytuya/issues/736)
- [IoT Core subscription expired (tuya-home-assistant #804)](https://github.com/tuya/tuya-home-assistant/issues/804)
- [Get a Developer License (Authorization Code) | TuyaOpen](https://tuyaopen.ai/docs/faqs/get-developer-license)
- [What is a cloud license (Include UUID, authkey)?](https://support.tuya.com/en/help/_detail/Ka9u6h09cn38u)

## HA MQTT client: no last-will/testament

`mqtt_client_interface.h` (TuyaOpen's portable MQTT client, used for the
HA-side connection — see `src/ha_mqtt.c`) has no LWT option, so unlike a
typical MQTT device, the broker won't auto-publish "offline" on an unclean
disconnect (power loss, crash, WiFi drop). Only a clean `ha_mqtt_stop()`
publishes it explicitly. If Home Assistant needs to reliably detect the
bridge going offline, this needs a different mechanism (e.g. HA polling
`{prefix}/status` liveness via a periodic heartbeat, once one exists).
