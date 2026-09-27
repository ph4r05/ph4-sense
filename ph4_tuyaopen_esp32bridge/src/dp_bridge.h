#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "config.h"

/**
 * dp_bridge — glue between Tuya DPs and Home Assistant MQTT.
 *
 * Same concept as the TuyaLink variant, but uses numeric DP IDs.
 * The actual DP ID per channel is NOT a linear range — see dp_map.h and
 * HISTORY.md for the real (non-contiguous) layout assigned in the Tuya console.
 */

OPERATE_RET dp_bridge_init(const app_config_t *cfg);

void dp_bridge_on_tuya_dp(uint8_t dp_id, bool value, void *user_data);
void dp_bridge_on_mqtt_msg(const char *topic, const char *data, void *user_data);
void dp_bridge_on_tuya_state(int tuya_state, void *user_data);
void dp_bridge_on_mqtt_state(int mqtt_state, void *user_data);

OPERATE_RET dp_bridge_set_switch(uint8_t channel, bool value);
