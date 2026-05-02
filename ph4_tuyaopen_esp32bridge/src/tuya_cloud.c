/**
 * tuya_cloud.c — TuyaOpen SDK wrapper with SmartLife pairing
 *
 * Wraps TuyaOpen's tuya_iot_* API. The SDK handles WiFi provisioning
 * (AP/BLE pairing via SmartLife app) and Tuya cloud MQTT automatically.
 *
 * DP layout (numeric IDs):
 *   SWITCH_DP_BASE..+15  = switch channels (HA → Tuya)
 *   SOCKET_DP_BASE..+15  = relay/socket channels (Tuya → HA)
 */

#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "esp_log.h"
#include "esp_err.h"

#include "tuya_iot.h"
#include "tuya_iot_dp.h"
#include "dp_schema.h"
#include "cJSON.h"

#include "tuya_config.h"
#include "config.h"
#include "tuya_cloud.h"

static const char *TAG = "tuya_cloud";

#ifndef SWITCH_DP_BASE
#define SWITCH_DP_BASE   1
#endif
#ifndef SOCKET_DP_BASE
#define SOCKET_DP_BASE   17
#endif

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
/* Helpers                                                              */
/* ------------------------------------------------------------------ */
static void set_state(tuya_state_t new_state)
{
    if (s_state == new_state) return;
    s_state = new_state;
    if (s_state_cb) s_state_cb(new_state, s_user_data);
}

/* ------------------------------------------------------------------ */
/* TuyaOpen event callback                                              */
/* ------------------------------------------------------------------ */
static void iot_event_handler(tuya_iot_client_t *client, tuya_event_msg_t *event)
{
    ESP_LOGI(TAG, "TuyaOpen event: %d (%s)", event->id, EVENT_ID2STR(event->id));

    switch (event->id) {
    case TUYA_EVENT_BIND_START:
        ESP_LOGI(TAG, "Entering pairing mode — use SmartLife app to add device");
        set_state(TUYA_STATE_PAIRING);
        break;

    case TUYA_EVENT_ACTIVATE_SUCCESSED:
        ESP_LOGI(TAG, "Device activated! Bound to SmartLife account.");
        set_state(TUYA_STATE_ACTIVATING);
        break;

    case TUYA_EVENT_MQTT_CONNECTED:
        ESP_LOGI(TAG, "Connected to Tuya cloud (MQTT)");
        set_state(TUYA_STATE_CONNECTED);
        tuya_cloud_report_all();
        break;

    case TUYA_EVENT_MQTT_DISCONNECT:
        ESP_LOGW(TAG, "Disconnected from Tuya cloud");
        set_state(TUYA_STATE_DISCONNECTED);
        break;

    case TUYA_EVENT_TIMESTAMP_SYNC:
        ESP_LOGI(TAG, "Timestamp sync: %d", event->value.asInteger);
        break;

    case TUYA_EVENT_DP_RECEIVE_OBJ: {
        dp_obj_recv_t *dpobj = event->value.dpobj;
        if (!dpobj) break;

        ESP_LOGI(TAG, "DP receive OBJ: cnt=%u cmd=%d", dpobj->dpscnt, dpobj->cmd_tp);

        for (uint32_t i = 0; i < dpobj->dpscnt; i++) {
            dp_obj_t *dp = &dpobj->dps[i];

            if (dp->type != PROP_BOOL) {
                ESP_LOGW(TAG, "DP %d: expected BOOL, got type %d", dp->id, dp->type);
                continue;
            }
            bool value = dp->value.dp_bool;
            ESP_LOGI(TAG, "DP %d = %s (from cloud)", dp->id, value ? "true" : "false");

            /* Update shadow */
            int sw_idx = dp->id - SWITCH_DP_BASE;
            int sk_idx = dp->id - SOCKET_DP_BASE;
            if (sw_idx >= 0 && sw_idx < s_cfg->switch_count)
                s_switch_state[sw_idx] = value;
            else if (sk_idx >= 0 && sk_idx < s_cfg->socket_count)
                s_socket_state[sk_idx] = value;

            if (s_dp_cb) s_dp_cb(dp->id, value, s_user_data);
        }

        /* ACK: report received DPs back */
        tuya_iot_dp_obj_report(client, dpobj->devid, dpobj->dps, dpobj->dpscnt, 0);
        break;
    }

    case TUYA_EVENT_DP_RECEIVE_RAW:
        ESP_LOGW(TAG, "Raw DP received (not handled)");
        break;

    case TUYA_EVENT_RESET:
        ESP_LOGW(TAG, "Reset requested: %d", event->value.asInteger);
        set_state(TUYA_STATE_RESET);
        break;

    default:
        break;
    }
}

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

    ESP_LOGI(TAG, "Switch DPs: %d..%d   Socket DPs: %d..%d",
             SWITCH_DP_BASE, SWITCH_DP_BASE + cfg->switch_count - 1,
             SOCKET_DP_BASE, SOCKET_DP_BASE + cfg->socket_count - 1);

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
    int sw_idx = dp_id - SWITCH_DP_BASE;
    int sk_idx = dp_id - SOCKET_DP_BASE;
    if (sw_idx >= 0 && sw_idx < CFG_SWITCH_COUNT_MAX)
        s_switch_state[sw_idx] = value;
    else if (sk_idx >= 0 && sk_idx < CFG_SOCKET_COUNT_MAX)
        s_socket_state[sk_idx] = value;

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
        int sw_idx = dp_ids[i] - SWITCH_DP_BASE;
        int sk_idx = dp_ids[i] - SOCKET_DP_BASE;
        if (sw_idx >= 0 && sw_idx < CFG_SWITCH_COUNT_MAX)
            s_switch_state[sw_idx] = values[i];
        else if (sk_idx >= 0 && sk_idx < CFG_SOCKET_COUNT_MAX)
            s_socket_state[sk_idx] = values[i];

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
        dp_ids[n] = SWITCH_DP_BASE + i;
        values[n] = s_switch_state[i];
        n++;
    }
    for (uint8_t i = 0; i < s_cfg->socket_count; i++) {
        dp_ids[n] = SOCKET_DP_BASE + i;
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
