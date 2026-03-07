/**
 * tuya_cloud.c — Tuya IoT Core SDK wrapper
 *
 * SDK used: tuya-iot-core-sdk (https://github.com/tuya/tuya-iot-core-sdk)
 *
 * Setup: add the SDK as a component in components/tuya-iot-core-sdk
 *   git submodule add https://github.com/tuya/tuya-iot-core-sdk \
 *       firmware/components/tuya-iot-core-sdk
 *
 * The SDK handles:
 *   - Device activation (first pairing with SmartLife app via EZ/AP token)
 *   - MQTT connection to Tuya cloud (m1.tuyacn.com:8883 TLS)
 *   - DP registration, report, receive
 *   - Heartbeat / reconnect
 */
#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "esp_err.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

/*
 * Include the Tuya IoT Core SDK header.
 * If the component is properly set up, this path resolves via CMake REQUIRES.
 *
 * Typical header layout for tuya-iot-core-sdk:
 *   include/tuya_iot.h        — main API
 *   include/tuya_cloud_types.h — DP types
 *   include/cJSON.h           — bundled JSON lib
 */
#include "tuya_iot.h"
#include "tuya_cloud_types.h"

#include "config.h"
#include "tuya_cloud.h"

static const char *TAG = "tuya_cloud";

/* ------------------------------------------------------------------ */
/* Internal state                                                       */
/* ------------------------------------------------------------------ */
static tuya_iot_client_t    s_client;
static tuya_state_t         s_state       = TUYA_STATE_INIT;
static tuya_dp_recv_cb_t    s_dp_cb       = NULL;
static tuya_state_cb_t      s_state_cb    = NULL;
static void                *s_user_data   = NULL;
static SemaphoreHandle_t    s_report_mutex;
static TaskHandle_t         s_task_handle = NULL;
static const app_config_t  *s_cfg         = NULL;

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

/* ------------------------------------------------------------------ */
/* Tuya SDK callbacks                                                   */
/* ------------------------------------------------------------------ */

/**
 * Called by Tuya SDK when it successfully connects to the cloud.
 */
static void on_connected(tuya_iot_client_t *client)
{
    ESP_LOGI(TAG, "Connected to Tuya cloud");
    set_state(TUYA_STATE_CONNECTED);

    /* Re-sync all DP states after reconnect */
    tuya_cloud_report_all();
}

/**
 * Called when disconnected from Tuya cloud.
 */
static void on_disconnect(tuya_iot_client_t *client)
{
    ESP_LOGW(TAG, "Disconnected from Tuya cloud");
    set_state(TUYA_STATE_DISCONNECTED);
}

/**
 * Called when Tuya cloud sends a DP update to the device.
 *
 * dp_data: JSON string like:
 *   {"devId":"...","dps":{"1":true,"102":false}}
 *
 * We parse this and forward each DP to the registered callback.
 */
static void on_dp_receive(tuya_iot_client_t *client, const char *dp_data)
{
    ESP_LOGD(TAG, "DP received: %s", dp_data);

    cJSON *root = cJSON_Parse(dp_data);
    if (!root) {
        ESP_LOGW(TAG, "Failed to parse DP JSON");
        return;
    }

    cJSON *dps = cJSON_GetObjectItemCaseSensitive(root, "dps");
    if (!cJSON_IsObject(dps)) {
        cJSON_Delete(root);
        return;
    }

    cJSON *dp_item;
    cJSON_ArrayForEach(dp_item, dps) {
        int dp_id = atoi(dp_item->string);
        if (dp_id <= 0) continue;

        bool value = cJSON_IsTrue(dp_item);
        ESP_LOGI(TAG, "DP %d = %s", dp_id, value ? "true" : "false");

        /* Update shadow state */
        int switch_idx = dp_id - DP_SWITCH_BASE;
        int socket_idx = dp_id - DP_SOCKET_BASE;

        if (switch_idx >= 0 && switch_idx < s_cfg->switch_count) {
            s_switch_state[switch_idx] = value;
        } else if (socket_idx >= 0 && socket_idx < s_cfg->socket_count) {
            s_socket_state[socket_idx] = value;
        }

        /* Notify bridge layer */
        if (s_dp_cb) s_dp_cb((uint8_t)dp_id, value, s_user_data);
    }

    cJSON_Delete(root);
}

/**
 * Called when device needs to enter pairing mode (activation).
 * Tuya SDK handles the EZ/AP token exchange internally; we just log it.
 */
static void on_activate(tuya_iot_client_t *client)
{
    ESP_LOGI(TAG, "Device activation started — open SmartLife app to pair");
    set_state(TUYA_STATE_ACTIVATING);
}

/**
 * Called when Tuya cloud requests a factory reset.
 */
static void on_reset(tuya_iot_client_t *client)
{
    ESP_LOGW(TAG, "Factory reset requested by Tuya cloud");
    set_state(TUYA_STATE_RESET);
    tuya_cloud_factory_reset();
}

/* ------------------------------------------------------------------ */
/* Main Tuya loop task                                                  */
/* ------------------------------------------------------------------ */
static void tuya_loop_task(void *arg)
{
    ESP_LOGI(TAG, "Tuya cloud task started");

    while (1) {
        /* tuya_iot_yield drives the SDK state machine:
         * - reconnects on disconnect
         * - sends heartbeats
         * - processes incoming messages
         *
         * Returns immediately if no work to do.
         */
        tuya_iot_client_yield(&s_client);
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

    /* PID is always required */
    if (strlen(cfg->tuya_pid) == 0) {
        ESP_LOGE(TAG, "Tuya PID not configured");
        return ESP_ERR_INVALID_ARG;
    }

    /*
     * Auth mode selection:
     *
     *   Pre-provisioned (UUID + AuthKey present):
     *     Device connects directly to Tuya cloud on every boot.
     *     UUID/AuthKey are burned into the firmware or stored in NVS.
     *     Credentials obtained from Tuya developer console ->
     *       Product -> Hardware Development -> Batch Test Devices.
     *
     *   Activation flow (UUID and/or AuthKey empty):
     *     On first boot the SDK enters EZ/AP pairing mode.
     *     Open SmartLife app -> Add Device -> follow instructions.
     *     The app sends WiFi credentials + an activation token to the device.
     *     Tuya cloud exchanges the token for a permanent UUID + AuthKey
     *     which the SDK stores in the 'tuya_kv' NVS partition.
     *     On all subsequent boots the stored credentials are used automatically.
     *     This is the standard consumer flow and requires no pre-provisioning.
     */
    bool use_activation = (strlen(cfg->tuya_uuid) == 0 || strlen(cfg->tuya_auth_key) == 0);

    if (use_activation) {
        ESP_LOGI(TAG, "Tuya auth mode: ACTIVATION (SmartLife pairing required on first boot)");
        ESP_LOGI(TAG, "PID=%s  — open SmartLife app and add the device to pair", cfg->tuya_pid);
    } else {
        ESP_LOGI(TAG, "Tuya auth mode: PRE-PROVISIONED  PID=%s  UUID=%.8s...",
                 cfg->tuya_pid, cfg->tuya_uuid);
    }

    /* Initialize Tuya IoT client.
     * When uuid/authkey are NULL/empty the SDK automatically uses the
     * activation flow (EZ/AP token exchange via SmartLife app). */
    const tuya_iot_config_t tuya_cfg = {
        .productkey        = cfg->tuya_pid,
        .uuid              = use_activation ? NULL : cfg->tuya_uuid,
        .authkey           = use_activation ? NULL : cfg->tuya_auth_key,
        .software_ver      = CONFIG_TUYA_SW_VERSION,
        .modules           = NULL,
        .skill_param       = NULL,
        .storage_namespace = "tuya_kv",   /* must match partition label */
        .on_connected      = on_connected,
        .on_disconnect     = on_disconnect,
        .on_dp_receive     = on_dp_receive,
        .on_activate       = on_activate,
        .on_reset          = on_reset,
    };

    int ret = tuya_iot_client_init(&s_client, &tuya_cfg);
    if (ret != OPRT_OK) {
        ESP_LOGE(TAG, "tuya_iot_client_init failed: %d", ret);
        return ESP_FAIL;
    }
    return ESP_OK;
}

esp_err_t tuya_cloud_start(void)
{
    /* Start the Tuya connection (handles activation + cloud connect) */
    int ret = tuya_iot_client_connect(&s_client);
    if (ret != OPRT_OK) {
        ESP_LOGE(TAG, "tuya_iot_client_connect failed: %d", ret);
        return ESP_FAIL;
    }

    /* Start the yield loop task */
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
        ESP_LOGW(TAG, "tuya_cloud_report_bool: not connected, DP %d queued", dp_id);
        /* SDK may queue internally; proceed anyway */
    }

    /* Update shadow */
    int switch_idx = dp_id - DP_SWITCH_BASE;
    int socket_idx = dp_id - DP_SOCKET_BASE;
    if (switch_idx >= 0 && switch_idx < CFG_SWITCH_COUNT_MAX)
        s_switch_state[switch_idx] = value;
    else if (socket_idx >= 0 && socket_idx < CFG_SOCKET_COUNT_MAX)
        s_socket_state[socket_idx] = value;

    xSemaphoreTake(s_report_mutex, portMAX_DELAY);

    /* Build DP object for SDK
     * tuya_iot_dp_bool_report(client, dp_id, value) — reports a single boolean DP */
    int ret = tuya_iot_dp_bool_report(&s_client, dp_id, value);

    xSemaphoreGive(s_report_mutex);

    if (ret != OPRT_OK) {
        ESP_LOGE(TAG, "tuya_iot_dp_bool_report(dp=%d, val=%d) failed: %d", dp_id, value, ret);
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

    xSemaphoreTake(s_report_mutex, portMAX_DELAY);

    /* Build a JSON DP object: {"1":true,"2":false,...} */
    cJSON *dps = cJSON_CreateObject();
    for (uint8_t i = 0; i < count; i++) {
        char key[8];
        snprintf(key, sizeof(key), "%d", dp_ids[i]);
        cJSON_AddBoolToObject(dps, key, values[i]);

        /* Update shadow */
        int switch_idx = dp_ids[i] - DP_SWITCH_BASE;
        int socket_idx = dp_ids[i] - DP_SOCKET_BASE;
        if (switch_idx >= 0 && switch_idx < CFG_SWITCH_COUNT_MAX)
            s_switch_state[switch_idx] = values[i];
        else if (socket_idx >= 0 && socket_idx < CFG_SOCKET_COUNT_MAX)
            s_socket_state[socket_idx] = values[i];
    }

    /* tuya_iot_dp_obj_report sends a pre-built JSON DP object */
    char *json = cJSON_PrintUnformatted(dps);
    cJSON_Delete(dps);

    int ret = OPRT_OK;
    if (json) {
        ret = tuya_iot_dp_obj_report(&s_client, json);
        free(json);
    }

    xSemaphoreGive(s_report_mutex);
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
    /* Erase Tuya's NVS namespace so it re-activates on next boot */
    nvs_handle_t h;
    if (nvs_open("tuya_kv", NVS_READWRITE, &h) == ESP_OK) {
        nvs_erase_all(h);
        nvs_commit(h);
        nvs_close(h);
        ESP_LOGW(TAG, "Tuya KV store erased — will re-activate on next boot");
    }
    esp_restart();
}

void tuya_cloud_stop(void)
{
    if (s_task_handle) {
        vTaskDelete(s_task_handle);
        s_task_handle = NULL;
    }
    tuya_iot_client_disconnect(&s_client);
}
