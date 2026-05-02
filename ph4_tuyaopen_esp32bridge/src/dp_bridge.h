#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "config.h"

/**
 * dp_bridge — glue between Tuya DPs and Home Assistant MQTT.
 *
 * Same concept as the TuyaLink variant, but uses numeric DP IDs:
 *   Switch DPs 1..16:   HA -> Tuya (HA controls SmartLife switches)
 *   Socket DPs 17..32:  Tuya -> HA (SmartLife triggers HA automations)
 */

esp_err_t dp_bridge_init(const app_config_t *cfg);

void dp_bridge_on_tuya_dp(uint8_t dp_id, bool value, void *user_data);
void dp_bridge_on_mqtt_msg(const char *topic, const char *data, void *user_data);
void dp_bridge_on_tuya_state(int tuya_state, void *user_data);
void dp_bridge_on_mqtt_state(int mqtt_state, void *user_data);

esp_err_t dp_bridge_set_switch(uint8_t channel, bool value);
