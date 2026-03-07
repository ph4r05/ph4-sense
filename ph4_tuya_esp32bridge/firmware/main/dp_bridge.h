#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "config.h"

/**
 * dp_bridge — the core glue between Tuya DPs and Home Assistant MQTT.
 *
 * Switch channels (HA -> Tuya, DPs 1..switch_count):
 *   - HA publishes: {prefix}/switch/{n}/set  = "ON" | "OFF"
 *   - ESP32 updates DP n in Tuya cloud
 *   - ESP32 echoes back: {prefix}/switch/{n}/state = "ON" | "OFF"
 *
 * Socket channels (Tuya -> HA, DPs 101..100+socket_count):
 *   - SmartLife sets DP (101 + n - 1) = true
 *   - ESP32 receives DP, publishes: {prefix}/socket/{n}/state = "ON"
 *   - If auto_reset is enabled for channel n:
 *       after socket_auto_reset_ms, ESP32 sets DP back to false
 *       and publishes: {prefix}/socket/{n}/state = "OFF"
 *   - This allows SmartLife to re-trigger the same socket again
 *
 * Control commands ({prefix}/cmd payload):
 *   "reset"   — factory reset (clears Tuya pairing, reboots)
 *   "reboot"  — reboot
 *   "status"  — publish full status JSON
 *   "sync"    — re-report all DPs to Tuya cloud
 */

/**
 * Initialize the bridge layer.
 * Must be called after ha_mqtt_start() and tuya_cloud_init().
 * Registers itself as the callback for both MQTT and Tuya DP events.
 */
esp_err_t dp_bridge_init(const app_config_t *cfg);

/**
 * Called by tuya_cloud.c when Tuya changes a DP (cloud -> device).
 * Routes to the correct channel handler.
 */
void dp_bridge_on_tuya_dp(uint8_t dp_id, bool value, void *user_data);

/**
 * Called by ha_mqtt.c when a message arrives on a subscribed topic.
 * Routes to the correct channel handler.
 */
void dp_bridge_on_mqtt_msg(const char *topic, const char *data, void *user_data);

/**
 * Called by tuya_cloud.c when Tuya connection state changes.
 */
void dp_bridge_on_tuya_state(int tuya_state, void *user_data);

/**
 * Called by ha_mqtt.c when MQTT connection state changes.
 */
void dp_bridge_on_mqtt_state(int mqtt_state, void *user_data);

/**
 * Set a switch channel state programmatically (e.g., for testing).
 * Reports to Tuya cloud and echoes state to MQTT.
 * channel: 1-based switch channel number.
 */
esp_err_t dp_bridge_set_switch(uint8_t channel, bool value);
