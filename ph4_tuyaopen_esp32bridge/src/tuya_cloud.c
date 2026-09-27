/**
 * tuya_cloud.c — TuyaOpen SDK wrapper with SmartLife pairing
 *
 * Wraps TuyaOpen's tuya_iot_* API. The SDK handles WiFi provisioning
 * (AP/BLE pairing via SmartLife app) and Tuya cloud MQTT automatically.
 *
 * DP layout: see dp_map.h — not a linear range, so per-channel DP IDs are
 * looked up rather than computed from a base offset.
 *
 * Note: the actual tuya_iot_event_handler is registered in app_main.c
 * (user_main() -> tuya_iot_init()), not here. This file only reports DPs
 * and tracks shadow state; it does not receive events directly.
 */

#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "esp_log.h"
#include "esp_err.h"

#include "tuya_iot.h"
#include "tuya_iot_dp.h"
#include "cJSON.h"

#include "tuya_config.h"
#include "config.h"
#include "tuya_cloud.h"
#include "dp_map.h"

static const char *TAG = "tuya_cloud";

/* ------------------------------------------------------------------ */
/* Internal state                                                       */
/* ------------------------------------------------------------------ */
static tuya_state_t         s_state       = TUYA_STATE_INIT;
static tuya_dp_recv_cb_t    s_dp_cb       = NULL;
static tuya_state_cb_t      s_state_cb    = NULL;
static void                *s_user_data   = NULL;
static const app_config_t  *s_cfg         = NULL;

/* Shadow state for all DPs */
static bool s_switch_state[CFG_SWITCH_COUNT_MAX] = {false};
static bool s_socket_state[CFG_SOCKET_COUNT_MAX] = {false};

/* ------------------------------------------------------------------ */
/* Public API                                                           */
/* ------------------------------------------------------------------ */
esp_err_t tuya_cloud_init(const app_config_t *cfg,
                          tuya_dp_recv_cb_t dp_cb,
                          tuya_state_cb_t   state_cb,
                          void             *user_data)
{
    s_cfg       = cfg;
    s_dp_cb     = dp_cb;
    s_state_cb  = state_cb;
    s_user_data = user_data;

    for (uint8_t i = 1; i <= cfg->switch_count; i++)
        ESP_LOGI(TAG, "  switch ch%d -> DP %d", i, switch_channel_to_dp(i));
    for (uint8_t i = 1; i <= cfg->socket_count; i++)
        ESP_LOGI(TAG, "  socket ch%d -> DP %d", i, relay_channel_to_dp(i));

    /* Note: tuya_iot_init() is called from tuya_app_main / user_main,
     * not here. This function just stores the bridge callbacks. */
    return ESP_OK;
}

esp_err_t tuya_cloud_start(void)
{
    /* tuya_iot_start() is called from user_main after tuya_iot_init() */
    return ESP_OK;
}

esp_err_t tuya_cloud_report_bool(uint8_t dp_id, bool value)
{
    /* Update shadow */
    int sw_ch = dp_to_switch_channel(dp_id);
    int sk_ch = dp_to_relay_channel(dp_id);
    if (sw_ch >= 1 && sw_ch <= CFG_SWITCH_COUNT_MAX)
        s_switch_state[sw_ch - 1] = value;
    else if (sk_ch >= 1 && sk_ch <= CFG_SOCKET_COUNT_MAX)
        s_socket_state[sk_ch - 1] = value;

    /* Use JSON report — simplest and most portable approach */
    char json[32];
    snprintf(json, sizeof(json), "{\"%d\":%s}", dp_id, value ? "true" : "false");

    tuya_iot_client_t *client = tuya_iot_client_get();
    int ret = tuya_iot_dp_report_json(client, json);
    if (ret != 0) {
        ESP_LOGE(TAG, "dp_report_json(dp=%d) failed: %d", dp_id, ret);
        return ESP_FAIL;
    }

    ESP_LOGD(TAG, "Reported DP %d = %s", dp_id, value ? "true" : "false");
    return ESP_OK;
}

esp_err_t tuya_cloud_report_multi(const uint8_t *dp_ids,
                                  const bool    *values,
                                  uint8_t        count)
{
    if (count == 0) return ESP_OK;

    /* Build JSON: {"1":true,"2":false,...} */
    cJSON *root = cJSON_CreateObject();
    for (uint8_t i = 0; i < count; i++) {
        int sw_ch = dp_to_switch_channel(dp_ids[i]);
        int sk_ch = dp_to_relay_channel(dp_ids[i]);
        if (sw_ch >= 1 && sw_ch <= CFG_SWITCH_COUNT_MAX)
            s_switch_state[sw_ch - 1] = values[i];
        else if (sk_ch >= 1 && sk_ch <= CFG_SOCKET_COUNT_MAX)
            s_socket_state[sk_ch - 1] = values[i];

        char key[4];
        snprintf(key, sizeof(key), "%d", dp_ids[i]);
        cJSON_AddBoolToObject(root, key, values[i]);
    }

    char *json = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!json) return ESP_ERR_NO_MEM;

    tuya_iot_client_t *client = tuya_iot_client_get();
    int ret = tuya_iot_dp_report_json(client, json);
    free(json);

    return (ret == 0) ? ESP_OK : ESP_FAIL;
}

esp_err_t tuya_cloud_report_all(void)
{
    if (!s_cfg) return ESP_ERR_INVALID_STATE;

    uint8_t dp_ids[CFG_SWITCH_COUNT_MAX + CFG_SOCKET_COUNT_MAX];
    bool    values[CFG_SWITCH_COUNT_MAX + CFG_SOCKET_COUNT_MAX];
    uint8_t n = 0;

    for (uint8_t i = 0; i < s_cfg->switch_count; i++) {
        dp_ids[n] = switch_channel_to_dp(i + 1);
        values[n] = s_switch_state[i];
        n++;
    }
    for (uint8_t i = 0; i < s_cfg->socket_count; i++) {
        dp_ids[n] = relay_channel_to_dp(i + 1);
        values[n] = s_socket_state[i];
        n++;
    }

    return tuya_cloud_report_multi(dp_ids, values, n);
}

tuya_state_t tuya_cloud_get_state(void)
{
    return s_state;
}

void tuya_cloud_factory_reset(void)
{
    tuya_iot_client_t *client = tuya_iot_client_get();
    tuya_iot_reset(client);
}

void tuya_cloud_stop(void)
{
    tuya_iot_client_t *client = tuya_iot_client_get();
    tuya_iot_stop(client);
}
