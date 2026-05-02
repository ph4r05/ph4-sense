#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "config.h"

/**
 * tuya_cloud — TuyaOpen SDK wrapper with SmartLife app pairing.
 *
 * DP layout (numeric IDs):
 *   1..16  = switch channels (HA → Tuya)
 *   17..32 = relay/socket channels (Tuya → HA)
 */

typedef enum {
    TUYA_STATE_INIT,
    TUYA_STATE_PAIRING,
    TUYA_STATE_ACTIVATING,
    TUYA_STATE_CONNECTED,
    TUYA_STATE_DISCONNECTED,
    TUYA_STATE_RESET,
} tuya_state_t;

typedef void (*tuya_dp_recv_cb_t)(uint8_t dp_id, bool value, void *user_data);
typedef void (*tuya_state_cb_t)(tuya_state_t state, void *user_data);

esp_err_t tuya_cloud_init(const app_config_t *cfg,
                          tuya_dp_recv_cb_t dp_cb,
                          tuya_state_cb_t   state_cb,
                          void             *user_data);

esp_err_t tuya_cloud_start(void);
esp_err_t tuya_cloud_report_bool(uint8_t dp_id, bool value);
esp_err_t tuya_cloud_report_multi(const uint8_t *dp_ids, const bool *values, uint8_t count);
esp_err_t tuya_cloud_report_all(void);
tuya_state_t tuya_cloud_get_state(void);
void tuya_cloud_factory_reset(void);
void tuya_cloud_stop(void);
