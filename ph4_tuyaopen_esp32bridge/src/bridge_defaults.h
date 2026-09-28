#pragma once

/**
 * Deployment-specific compile-time defaults for this bridge instance.
 *
 * Not credentials (see tuya_config.local.h for those) -- just kept out of
 * config.c's loading logic so they're easy to find and change without
 * reading through the config-loading code. These are overridden at runtime
 * by whatever gets saved to TAL KV via config_apply_json()/config_save().
 *
 * NOTE: TuyaOpen's CONFIG_* Kconfig mechanism can't reach this app directory
 * without patching the vendored SDK's Kconfig include chain -- this app is
 * linked into the "main" component as a plain CMake library, not registered
 * as its own idf_component, so it isn't in TuyaOpen's Kconfig-scan path.
 * Plain #defines here instead of a Kconfig.projbuild option. See HISTORY.md.
 */

#define BRIDGE_DEFAULT_DEVICE_NAME        "ph4bridge01"
#define BRIDGE_DEFAULT_MQTT_HOST          "10.0.1.103"   /* LAN IP, not a secret */
#define BRIDGE_DEFAULT_MQTT_PORT          1883
#define BRIDGE_DEFAULT_MQTT_TOPIC_PREFIX  "ph4/bridge01"
