#include <string.h>
#include <stdlib.h>
#include "esp_log.h"
#include "esp_err.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "cJSON.h"
#include "config.h"

/* Kconfig defaults */
#include "sdkconfig.h"

static const char *TAG = "config";

/* NVS key names (max 15 chars each) */
#define K_WIFI_SSID         "wifi_ssid"
#define K_WIFI_PASS         "wifi_pass"
#define K_TUYA_PID          "tuya_pid"
#define K_TUYA_UUID         "tuya_uuid"
#define K_TUYA_AUTH         "tuya_auth"
#define K_MQTT_HOST         "mqtt_host"
#define K_MQTT_PORT         "mqtt_port"
#define K_MQTT_USER         "mqtt_user"
#define K_MQTT_PASS         "mqtt_pass"
#define K_MQTT_PREFIX       "mqtt_prefix"
#define K_SWITCH_COUNT      "sw_count"
#define K_SOCKET_COUNT      "sk_count"
#define K_SK_RESET_MASK     "sk_rst_mask"
#define K_SK_RESET_MS       "sk_rst_ms"
#define K_DEVICE_NAME       "dev_name"
#define K_WIFI_AP_DISABLED  "wifi_ap_dis"

/* Helper: read string from NVS, keep default if key missing */
static void nvs_read_str(nvs_handle_t h, const char *key, char *dst, size_t max_len)
{
    size_t len = max_len;
    esp_err_t err = nvs_get_str(h, key, dst, &len);
    if (err != ESP_OK && err != ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGW(TAG, "nvs_get_str(%s): %s", key, esp_err_to_name(err));
    }
}

static void nvs_write_str(nvs_handle_t h, const char *key, const char *val)
{
    esp_err_t err = nvs_set_str(h, key, val);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "nvs_set_str(%s): %s", key, esp_err_to_name(err));
    }
}

esp_err_t config_load(app_config_t *cfg)
{
    /* Apply Kconfig defaults first */
    memset(cfg, 0, sizeof(*cfg));

    strlcpy(cfg->wifi_ssid,          CONFIG_WIFI_SSID,           sizeof(cfg->wifi_ssid));
    strlcpy(cfg->wifi_pass,          CONFIG_WIFI_PASSWORD,        sizeof(cfg->wifi_pass));
    strlcpy(cfg->tuya_pid,           CONFIG_TUYA_PID,             sizeof(cfg->tuya_pid));
    strlcpy(cfg->tuya_uuid,          CONFIG_TUYA_UUID,            sizeof(cfg->tuya_uuid));
    strlcpy(cfg->tuya_auth_key,      CONFIG_TUYA_AUTH_KEY,        sizeof(cfg->tuya_auth_key));
    strlcpy(cfg->mqtt_host,          CONFIG_HA_MQTT_HOST,         sizeof(cfg->mqtt_host));
    strlcpy(cfg->mqtt_user,          CONFIG_HA_MQTT_USER,         sizeof(cfg->mqtt_user));
    strlcpy(cfg->mqtt_pass,          CONFIG_HA_MQTT_PASS,         sizeof(cfg->mqtt_pass));
    strlcpy(cfg->mqtt_topic_prefix,  CONFIG_HA_MQTT_TOPIC_PREFIX, sizeof(cfg->mqtt_topic_prefix));
    strlcpy(cfg->device_name,        "ph4-bridge",                sizeof(cfg->device_name));

    cfg->mqtt_port           = CONFIG_HA_MQTT_PORT;
    cfg->switch_count        = CONFIG_BRIDGE_SWITCH_COUNT;
    cfg->socket_count        = CONFIG_BRIDGE_SOCKET_COUNT;
    cfg->socket_auto_reset_ms = CONFIG_BRIDGE_SOCKET_AUTO_RESET_MS;
    cfg->socket_auto_reset_mask = 0xFFFF; /* all channels auto-reset by default */
    cfg->wifi_ap_disabled = CONFIG_WIFI_DISABLE_AP;

    /* Override with NVS values */
    nvs_handle_t h;
    esp_err_t err = nvs_open(CFG_NVS_NAMESPACE, NVS_READONLY, &h);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGI(TAG, "No saved config, using Kconfig defaults");
        return ESP_OK;
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs_open failed: %s", esp_err_to_name(err));
        return err;
    }

    nvs_read_str(h, K_WIFI_SSID,    cfg->wifi_ssid,         sizeof(cfg->wifi_ssid));
    nvs_read_str(h, K_WIFI_PASS,    cfg->wifi_pass,         sizeof(cfg->wifi_pass));
    nvs_read_str(h, K_TUYA_PID,     cfg->tuya_pid,          sizeof(cfg->tuya_pid));
    nvs_read_str(h, K_TUYA_UUID,    cfg->tuya_uuid,         sizeof(cfg->tuya_uuid));
    nvs_read_str(h, K_TUYA_AUTH,    cfg->tuya_auth_key,     sizeof(cfg->tuya_auth_key));
    nvs_read_str(h, K_MQTT_HOST,    cfg->mqtt_host,         sizeof(cfg->mqtt_host));
    nvs_read_str(h, K_MQTT_USER,    cfg->mqtt_user,         sizeof(cfg->mqtt_user));
    nvs_read_str(h, K_MQTT_PASS,    cfg->mqtt_pass,         sizeof(cfg->mqtt_pass));
    nvs_read_str(h, K_MQTT_PREFIX,  cfg->mqtt_topic_prefix, sizeof(cfg->mqtt_topic_prefix));
    nvs_read_str(h, K_DEVICE_NAME,  cfg->device_name,       sizeof(cfg->device_name));

    uint16_t u16 = 0;
    uint8_t  u8  = 0;
    uint32_t u32 = 0;

    if (nvs_get_u16(h, K_MQTT_PORT,    &u16) == ESP_OK) cfg->mqtt_port = u16;
    if (nvs_get_u8 (h, K_SWITCH_COUNT, &u8)  == ESP_OK) cfg->switch_count = u8;
    if (nvs_get_u8 (h, K_SOCKET_COUNT, &u8)  == ESP_OK) cfg->socket_count = u8;
    if (nvs_get_u16(h, K_SK_RESET_MASK,&u16) == ESP_OK) cfg->socket_auto_reset_mask = u16;
    if (nvs_get_u32(h, K_SK_RESET_MS,  &u32) == ESP_OK) cfg->socket_auto_reset_ms = u32;
    if (nvs_get_u8 (h, K_WIFI_AP_DISABLED, &u8) == ESP_OK) cfg->wifi_ap_disabled = (bool)u8;

    nvs_close(h);
    ESP_LOGI(TAG, "Config loaded from NVS");
    return ESP_OK;
}

esp_err_t config_save(const app_config_t *cfg)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(CFG_NVS_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs_open RW failed: %s", esp_err_to_name(err));
        return err;
    }

    nvs_write_str(h, K_WIFI_SSID,    cfg->wifi_ssid);
    nvs_write_str(h, K_WIFI_PASS,    cfg->wifi_pass);
    nvs_write_str(h, K_TUYA_PID,     cfg->tuya_pid);
    nvs_write_str(h, K_TUYA_UUID,    cfg->tuya_uuid);
    nvs_write_str(h, K_TUYA_AUTH,    cfg->tuya_auth_key);
    nvs_write_str(h, K_MQTT_HOST,    cfg->mqtt_host);
    nvs_write_str(h, K_MQTT_USER,    cfg->mqtt_user);
    nvs_write_str(h, K_MQTT_PASS,    cfg->mqtt_pass);
    nvs_write_str(h, K_MQTT_PREFIX,  cfg->mqtt_topic_prefix);
    nvs_write_str(h, K_DEVICE_NAME,  cfg->device_name);

    nvs_set_u16(h, K_MQTT_PORT,       cfg->mqtt_port);
    nvs_set_u8 (h, K_SWITCH_COUNT,    cfg->switch_count);
    nvs_set_u8 (h, K_SOCKET_COUNT,    cfg->socket_count);
    nvs_set_u16(h, K_SK_RESET_MASK,   cfg->socket_auto_reset_mask);
    nvs_set_u32(h, K_SK_RESET_MS,     cfg->socket_auto_reset_ms);
    nvs_set_u8 (h, K_WIFI_AP_DISABLED, (uint8_t)cfg->wifi_ap_disabled);

    err = nvs_commit(h);
    nvs_close(h);

    if (err == ESP_OK) {
        ESP_LOGI(TAG, "Config saved to NVS");
    } else {
        ESP_LOGE(TAG, "nvs_commit failed: %s", esp_err_to_name(err));
    }
    return err;
}

esp_err_t config_erase(void)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(CFG_NVS_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    err = nvs_erase_all(h);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    ESP_LOGW(TAG, "Config erased from NVS");
    return err;
}

esp_err_t config_apply_json(app_config_t *cfg, const char *json_str)
{
    cJSON *root = cJSON_Parse(json_str);
    if (!root) {
        ESP_LOGE(TAG, "JSON parse error");
        return ESP_ERR_INVALID_ARG;
    }

    cJSON *item;

#define JSON_STR(key, field) \
    item = cJSON_GetObjectItemCaseSensitive(root, key); \
    if (cJSON_IsString(item) && item->valuestring) { \
        strlcpy(cfg->field, item->valuestring, sizeof(cfg->field)); \
    }

#define JSON_INT(key, field, type) \
    item = cJSON_GetObjectItemCaseSensitive(root, key); \
    if (cJSON_IsNumber(item)) { cfg->field = (type)item->valuedouble; }

#define JSON_BOOL_BIT(key, mask_field, bit) \
    item = cJSON_GetObjectItemCaseSensitive(root, key); \
    if (cJSON_IsBool(item)) { \
        if (cJSON_IsTrue(item)) cfg->mask_field |= (1u << (bit)); \
        else cfg->mask_field &= ~(1u << (bit)); \
    }

    /* WiFi */
    cJSON *wifi = cJSON_GetObjectItemCaseSensitive(root, "wifi");
    if (wifi) {
        JSON_STR("ssid",       wifi_ssid);
        JSON_STR("passphrase", wifi_pass);
        item = cJSON_GetObjectItemCaseSensitive(wifi, "ap_disabled");
        if (cJSON_IsBool(item)) cfg->wifi_ap_disabled = cJSON_IsTrue(item);
    }

    /* Tuya */
    cJSON *tuya = cJSON_GetObjectItemCaseSensitive(root, "tuya");
    if (tuya) {
        JSON_STR("pid",      tuya_pid);
        JSON_STR("uuid",     tuya_uuid);
        JSON_STR("auth_key", tuya_auth_key);
    }

    /* MQTT */
    cJSON *mqtt = cJSON_GetObjectItemCaseSensitive(root, "mqtt");
    if (mqtt) {
        JSON_STR("host",         mqtt_host);
        JSON_STR("user",         mqtt_user);
        JSON_STR("pass",         mqtt_pass);
        JSON_STR("topic_prefix", mqtt_topic_prefix);
        JSON_INT("port",         mqtt_port, uint16_t);
    }

    /* Channels */
    cJSON *ch = cJSON_GetObjectItemCaseSensitive(root, "channels");
    if (ch) {
        JSON_INT("switch_count",      switch_count,          uint8_t);
        JSON_INT("socket_count",      socket_count,          uint8_t);
        JSON_INT("socket_auto_reset_ms", socket_auto_reset_ms, uint32_t);

        /* socket_auto_reset: array of booleans, index = channel 1-based */
        cJSON *arr = cJSON_GetObjectItemCaseSensitive(ch, "socket_auto_reset");
        if (cJSON_IsArray(arr)) {
            cfg->socket_auto_reset_mask = 0;
            int idx = 0;
            cJSON *el;
            cJSON_ArrayForEach(el, arr) {
                if (idx >= CFG_SOCKET_COUNT_MAX) break;
                if (cJSON_IsTrue(el))
                    cfg->socket_auto_reset_mask |= (1u << idx);
                idx++;
            }
        }
    }

    /* Device */
    JSON_STR("device_name", device_name);

#undef JSON_STR
#undef JSON_INT
#undef JSON_BOOL_BIT

    cJSON_Delete(root);
    return ESP_OK;
}

char *config_to_json(const app_config_t *cfg)
{
    cJSON *root = cJSON_CreateObject();

    cJSON *wifi = cJSON_CreateObject();
    cJSON_AddStringToObject(wifi, "ssid",        cfg->wifi_ssid);
    cJSON_AddStringToObject(wifi, "passphrase",  cfg->wifi_pass);
    cJSON_AddBoolToObject  (wifi, "ap_disabled", cfg->wifi_ap_disabled);
    cJSON_AddItemToObject(root, "wifi", wifi);

    cJSON *tuya = cJSON_CreateObject();
    cJSON_AddStringToObject(tuya, "pid",      cfg->tuya_pid);
    cJSON_AddStringToObject(tuya, "uuid",     cfg->tuya_uuid);
    cJSON_AddStringToObject(tuya, "auth_key", cfg->tuya_auth_key);
    cJSON_AddItemToObject(root, "tuya", tuya);

    cJSON *mqtt = cJSON_CreateObject();
    cJSON_AddStringToObject(mqtt, "host",         cfg->mqtt_host);
    cJSON_AddNumberToObject(mqtt, "port",         cfg->mqtt_port);
    cJSON_AddStringToObject(mqtt, "user",         cfg->mqtt_user);
    cJSON_AddStringToObject(mqtt, "topic_prefix", cfg->mqtt_topic_prefix);
    cJSON_AddItemToObject(root, "mqtt", mqtt);

    cJSON *ch = cJSON_CreateObject();
    cJSON_AddNumberToObject(ch, "switch_count",         cfg->switch_count);
    cJSON_AddNumberToObject(ch, "socket_count",         cfg->socket_count);
    cJSON_AddNumberToObject(ch, "socket_auto_reset_ms", cfg->socket_auto_reset_ms);

    cJSON *arr = cJSON_CreateArray();
    for (int i = 0; i < cfg->socket_count; i++) {
        cJSON_AddItemToArray(arr, cJSON_CreateBool(
            (cfg->socket_auto_reset_mask >> i) & 1));
    }
    cJSON_AddItemToObject(ch, "socket_auto_reset", arr);
    cJSON_AddItemToObject(root, "channels", ch);

    cJSON_AddStringToObject(root, "device_name", cfg->device_name);

    char *json = cJSON_Print(root);
    cJSON_Delete(root);
    return json;
}
