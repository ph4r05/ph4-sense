/**
 * tuya_cloud.c — Tuya IoT Core SDK wrapper
 *
 * SDK used: tuya-iot-core-sdk (https://github.com/tuya/tuya-iot-core-sdk)
 * Protocol: TuyaLink (tuyalink_core.h / tuya_mqtt_context_t)
 *
 * Setup: add the SDK as a component in components/tuya-iot-core-sdk
 *   git submodule add https://github.com/tuya/tuya-iot-core-sdk \
 *       firmware/components/tuya-iot-core-sdk
 *
 * Authentication:
 *   The TuyaLink SDK requires pre-provisioned credentials:
 *     device_id     = cfg->tuya_uuid    (from Tuya IoT Platform -> Device -> View)
 *     device_secret = cfg->tuya_auth_key
 *   cfg->tuya_pid (product ID) is used only for logging.
 *
 *   There is no EZ/AP activation flow in tuyalink_core — credentials must be
 *   obtained from the Tuya IoT Platform developer console before flashing.
 *
 * DP ↔ Property name mapping:
 *   Tuya DPs are exposed as TuyaLink properties with names "dp_N" where N is
 *   the numeric DP ID (e.g., dp_id=1 → property "dp_1", dp_id=101 → "dp_101").
 *   The device's data model on Tuya IoT Platform must define properties with
 *   these same names and type "Boolean".
 */
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "esp_err.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

#include "tuyalink_core.h"
#include "tuya_error_code.h"
#include "tuya_config_defaults.h"
#include "cJSON.h"

#include "tuya_cacert.h"
#include "config.h"
#include "tuya_cloud.h"

static const char *TAG = "tuya_cloud";

/* ------------------------------------------------------------------ */
/* Internal state                                                       */
/* ------------------------------------------------------------------ */
static tuya_mqtt_context_t  s_client;
static tuya_state_t         s_state       = TUYA_STATE_INIT;
static tuya_dp_recv_cb_t    s_dp_cb       = NULL;
static tuya_state_cb_t      s_state_cb    = NULL;
static void                *s_user_data   = NULL;
static SemaphoreHandle_t    s_report_mutex;
static TaskHandle_t         s_task_handle = NULL;
static const app_config_t  *s_cfg         = NULL;

/* device_id storage (tuya_mqtt_config_t points into this) */
static char s_device_id[CFG_MAX_STR];

/* Shadow state for all DPs — allows tuya_cloud_report_all() on reconnect */
#define DP_SWITCH_BASE   1
#define DP_SOCKET_BASE   CONFIG_BRIDGE_SOCKET_DP_BASE

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

/* Convert dp_id to TuyaLink property name: 1 → "dp_1", 101 → "dp_101" */
static void dp_id_to_prop(uint8_t dp_id, char *buf, size_t len)
{
    snprintf(buf, len, "dp_%d", (int)dp_id);
}

/* ------------------------------------------------------------------ */
/* Tuya SDK callbacks                                                   */
/* ------------------------------------------------------------------ */

static void on_connected(tuya_mqtt_context_t *context, void *user_data)
{
    ESP_LOGI(TAG, "Connected to Tuya cloud");
    set_state(TUYA_STATE_CONNECTED);

    /* Re-sync all DP states after reconnect */
    tuya_cloud_report_all();
}

static void on_disconnect(tuya_mqtt_context_t *context, void *user_data)
{
    ESP_LOGW(TAG, "Disconnected from Tuya cloud");
    set_state(TUYA_STATE_DISCONNECTED);
}

/**
 * Called when Tuya cloud sends a property-set command to the device.
 *
 * msg->data_json is a cJSON object: {"dp_1":{"value":true},"dp_2":{"value":false}}
 * We extract the numeric DP ID from the property name and forward to dp_cb.
 */
static void on_messages(tuya_mqtt_context_t *context, void *user_data,
                        const tuyalink_message_t *msg)
{
    if (msg->type != THING_TYPE_PROPERTY_SET) {
        return;
    }

    ESP_LOGD(TAG, "Property SET: %s", msg->data_string ? msg->data_string : "(null)");

    cJSON *root = msg->data_json;
    if (!root) return;

    cJSON *prop;
    cJSON_ArrayForEach(prop, root) {
        const char *key = prop->string;
        if (!key || strncmp(key, "dp_", 3) != 0) continue;

        int dp_id = atoi(key + 3);
        if (dp_id <= 0) continue;

        cJSON *val_obj = cJSON_GetObjectItemCaseSensitive(prop, "value");
        if (!val_obj) continue;
        bool value = cJSON_IsTrue(val_obj);

        ESP_LOGI(TAG, "DP %d = %s", dp_id, value ? "true" : "false");

        /* Update shadow */
        int switch_idx = dp_id - DP_SWITCH_BASE;
        int socket_idx = dp_id - DP_SOCKET_BASE;
        if (switch_idx >= 0 && switch_idx < s_cfg->switch_count)
            s_switch_state[switch_idx] = value;
        else if (socket_idx >= 0 && socket_idx < s_cfg->socket_count)
            s_socket_state[socket_idx] = value;

        if (s_dp_cb) s_dp_cb((uint8_t)dp_id, value, s_user_data);
    }
}

/* ------------------------------------------------------------------ */
/* Main Tuya loop task                                                  */
/* ------------------------------------------------------------------ */
static void tuya_loop_task(void *arg)
{
    ESP_LOGI(TAG, "Tuya cloud task started");

    for (;;) {
        /* tuya_mqtt_loop drives the MQTT state machine:
         * - reconnects on disconnect
         * - sends heartbeats
         * - processes incoming messages
         * Blocks up to MQTT_RECV_BLOCK_TIME_MS waiting for data. */
        tuya_mqtt_loop(&s_client);
        vTaskDelay(pdMS_TO_TICKS(10));
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

    s_report_mutex = xSemaphoreCreateMutex();
    if (!s_report_mutex) return ESP_ERR_NO_MEM;

    if (strlen(cfg->tuya_uuid) == 0 || strlen(cfg->tuya_auth_key) == 0) {
        ESP_LOGE(TAG, "tuya_uuid and tuya_auth_key must both be configured");
        ESP_LOGE(TAG, "Get them from Tuya IoT Platform: Cloud -> Device -> View Secret");
        return ESP_ERR_INVALID_ARG;
    }

    strncpy(s_device_id, cfg->tuya_uuid, sizeof(s_device_id) - 1);
    s_device_id[sizeof(s_device_id) - 1] = '\0';

    ESP_LOGI(TAG, "Tuya init: device_id=%.8s...  PID=%s", s_device_id, cfg->tuya_pid);

    int ret = tuya_mqtt_init(&s_client, &(const tuya_mqtt_config_t) {
        .host          = "m1.tuyacn.com",
        .port          = 8883,
        .cacert        = (const uint8_t *)tuya_cacert_pem,
        .cacert_len    = sizeof(tuya_cacert_pem),
        .device_id     = s_device_id,
        .device_secret = cfg->tuya_auth_key,
        .keepalive     = MQTT_KEEPALIVE_INTERVALIN,
        .timeout_ms    = MQTT_RECV_BLOCK_TIME_MS,
        .user_data     = NULL,
        .on_connected  = on_connected,
        .on_disconnect = on_disconnect,
        .on_messages   = on_messages,
    });

    if (ret != OPRT_OK) {
        ESP_LOGE(TAG, "tuya_mqtt_init failed: %d", ret);
        return ESP_FAIL;
    }
    return ESP_OK;
}

esp_err_t tuya_cloud_start(void)
{
    int ret = tuya_mqtt_connect(&s_client);
    if (ret != OPRT_OK) {
        ESP_LOGE(TAG, "tuya_mqtt_connect failed: %d", ret);
        return ESP_FAIL;
    }

    BaseType_t r = xTaskCreate(tuya_loop_task, "tuya_loop",
                               8192, NULL, 6, &s_task_handle);
    if (r != pdPASS) {
        ESP_LOGE(TAG, "Failed to create tuya_loop task");
        return ESP_ERR_NO_MEM;
    }

    ESP_LOGI(TAG, "Tuya cloud started");
    return ESP_OK;
}

esp_err_t tuya_cloud_report_bool(uint8_t dp_id, bool value)
{
    if (s_state != TUYA_STATE_CONNECTED) {
        ESP_LOGW(TAG, "tuya_cloud_report_bool: not connected, dp=%d", dp_id);
    }

    /* Update shadow */
    int switch_idx = dp_id - DP_SWITCH_BASE;
    int socket_idx = dp_id - DP_SOCKET_BASE;
    if (switch_idx >= 0 && switch_idx < CFG_SWITCH_COUNT_MAX)
        s_switch_state[switch_idx] = value;
    else if (socket_idx >= 0 && socket_idx < CFG_SOCKET_COUNT_MAX)
        s_socket_state[socket_idx] = value;

    char prop[16];
    dp_id_to_prop(dp_id, prop, sizeof(prop));

    /* {"dp_N":{"value":true,"time":0}} */
    char json[64];
    snprintf(json, sizeof(json), "{\"%s\":{\"value\":%s,\"time\":0}}",
             prop, value ? "true" : "false");

    xSemaphoreTake(s_report_mutex, portMAX_DELAY);
    int ret = tuyalink_thing_property_report(&s_client, s_device_id, json);
    xSemaphoreGive(s_report_mutex);

    if (ret != OPRT_OK) {
        ESP_LOGE(TAG, "property_report(dp=%d) failed: %d", dp_id, ret);
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

    /* Build: {"dp_1":{"value":true,"time":0},...} */
    cJSON *root = cJSON_CreateObject();
    for (uint8_t i = 0; i < count; i++) {
        /* Update shadow */
        int switch_idx = dp_ids[i] - DP_SWITCH_BASE;
        int socket_idx = dp_ids[i] - DP_SOCKET_BASE;
        if (switch_idx >= 0 && switch_idx < CFG_SWITCH_COUNT_MAX)
            s_switch_state[switch_idx] = values[i];
        else if (socket_idx >= 0 && socket_idx < CFG_SOCKET_COUNT_MAX)
            s_socket_state[socket_idx] = values[i];

        char prop[16];
        dp_id_to_prop(dp_ids[i], prop, sizeof(prop));

        cJSON *item = cJSON_CreateObject();
        cJSON_AddBoolToObject(item, "value", values[i]);
        cJSON_AddNumberToObject(item, "time", 0);
        cJSON_AddItemToObject(root, prop, item);
    }

    char *json = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!json) return ESP_ERR_NO_MEM;

    xSemaphoreTake(s_report_mutex, portMAX_DELAY);
    int ret = tuyalink_thing_property_report(&s_client, s_device_id, json);
    xSemaphoreGive(s_report_mutex);
    free(json);

    return (ret == OPRT_OK) ? ESP_OK : ESP_FAIL;
}

esp_err_t tuya_cloud_report_all(void)
{
    if (!s_cfg) return ESP_ERR_INVALID_STATE;

    uint8_t dp_ids[CFG_SWITCH_COUNT_MAX + CFG_SOCKET_COUNT_MAX];
    bool    values[CFG_SWITCH_COUNT_MAX + CFG_SOCKET_COUNT_MAX];
    uint8_t n = 0;

    for (uint8_t i = 0; i < s_cfg->switch_count; i++) {
        dp_ids[n] = DP_SWITCH_BASE + i;
        values[n] = s_switch_state[i];
        n++;
    }
    for (uint8_t i = 0; i < s_cfg->socket_count; i++) {
        dp_ids[n] = DP_SOCKET_BASE + i;
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
    /* Erase Tuya's NVS namespace so credentials are cleared on next boot */
    nvs_handle_t h;
    if (nvs_open("tuya_kv", NVS_READWRITE, &h) == ESP_OK) {
        nvs_erase_all(h);
        nvs_commit(h);
        nvs_close(h);
        ESP_LOGW(TAG, "Tuya KV store erased");
    }
    esp_restart();
}

void tuya_cloud_stop(void)
{
    if (s_task_handle) {
        vTaskDelete(s_task_handle);
        s_task_handle = NULL;
    }
    tuya_mqtt_disconnect(&s_client);
}
