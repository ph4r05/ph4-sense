#include <string.h>
#include <stdlib.h>
#include "tal_api.h"
#include "cJSON.h"
#include "config.h"
#include "bridge_defaults.h"

/* strlcpy is a BSD/ESP-IDF extension; TuyaOpen's libc may not have it */
static size_t strlcpy_local(char *dst, const char *src, size_t dstsize)
{
    size_t srclen = strlen(src);
    if (dstsize == 0) return srclen;
    size_t n = (srclen < dstsize - 1) ? srclen : dstsize - 1;
    memcpy(dst, src, n);
    dst[n] = '\0';
    return srclen;
}
#define strlcpy strlcpy_local

/* Config is persisted as a single JSON blob under one TAL KV key */
OPERATE_RET config_load(app_config_t *cfg)
{
    /* Compile-time defaults */
    memset(cfg, 0, sizeof(*cfg));

    strlcpy(cfg->mqtt_host,          BRIDGE_DEFAULT_MQTT_HOST,         sizeof(cfg->mqtt_host));
    strlcpy(cfg->mqtt_topic_prefix,  BRIDGE_DEFAULT_MQTT_TOPIC_PREFIX, sizeof(cfg->mqtt_topic_prefix));
    strlcpy(cfg->device_name,        BRIDGE_DEFAULT_DEVICE_NAME,       sizeof(cfg->device_name));
    cfg->mqtt_port = BRIDGE_DEFAULT_MQTT_PORT;

    /* mqtt_user/mqtt_pass: no compile-time default -- broker allows
     * anonymous LAN clients; set via config_apply_json()+config_save() if
     * that ever changes. */

#ifdef CONFIG_BRIDGE_SWITCH_COUNT
    cfg->switch_count = CONFIG_BRIDGE_SWITCH_COUNT;
#else
    cfg->switch_count = 16;
#endif
#ifdef CONFIG_BRIDGE_SOCKET_COUNT
    cfg->socket_count = CONFIG_BRIDGE_SOCKET_COUNT;
#else
    cfg->socket_count = 16;
#endif
#ifdef CONFIG_BRIDGE_SOCKET_AUTO_RESET_MS
    cfg->socket_auto_reset_ms = CONFIG_BRIDGE_SOCKET_AUTO_RESET_MS;
#else
    cfg->socket_auto_reset_ms = 500;
#endif
    cfg->socket_auto_reset_mask = 0xFFFF; /* all channels auto-reset by default */

    /* Override with saved values, if any */
    uint8_t *buf = NULL;
    size_t len = 0;
    if (tal_kv_get(CFG_NVS_NAMESPACE, &buf, &len) != OPRT_OK || !buf) {
        PR_INFO("No saved config, using defaults");
        return OPRT_OK;
    }

    char *json = malloc(len + 1);
    if (!json) {
        tal_kv_free(buf);
        return OPRT_MALLOC_FAILED;
    }
    memcpy(json, buf, len);
    json[len] = '\0';
    tal_kv_free(buf);

    OPERATE_RET rt = config_apply_json(cfg, json);
    free(json);
    if (rt == OPRT_OK) {
        PR_INFO("Config loaded from KV");
    }
    return OPRT_OK;
}

OPERATE_RET config_save(const app_config_t *cfg)
{
    char *json = config_to_json(cfg);
    if (!json) return OPRT_MALLOC_FAILED;

    int ret = tal_kv_set(CFG_NVS_NAMESPACE, (const uint8_t *)json, strlen(json));
    free(json);

    if (ret == OPRT_OK) {
        PR_INFO("Config saved to KV");
    } else {
        PR_ERR("tal_kv_set failed: %d", ret);
    }
    return ret;
}

OPERATE_RET config_erase(void)
{
    int ret = tal_kv_del(CFG_NVS_NAMESPACE);
    PR_WARN("Config erased from KV");
    return ret;
}

OPERATE_RET config_apply_json(app_config_t *cfg, const char *json_str)
{
    cJSON *root = cJSON_Parse(json_str);
    if (!root) {
        PR_ERR("JSON parse error");
        return OPRT_CJSON_PARSE_ERR;
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

        /* switch_count/socket_count are used as array-index bounds
         * throughout dp_bridge.c and tuya_cloud.c (e.g.
         * tuya_cloud_report_all()'s stack-allocated dp_ids[]/values[]
         * arrays, sized CFG_*_COUNT_MAX). An unclamped value from a
         * malformed/corrupted saved config would cause out-of-bounds
         * reads/writes there -- clamp at the point external data enters. */
        if (cfg->switch_count > CFG_SWITCH_COUNT_MAX) cfg->switch_count = CFG_SWITCH_COUNT_MAX;
        if (cfg->socket_count > CFG_SOCKET_COUNT_MAX) cfg->socket_count = CFG_SOCKET_COUNT_MAX;

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

    cJSON_Delete(root);
    return OPRT_OK;
}

char *config_to_json(const app_config_t *cfg)
{
    cJSON *root = cJSON_CreateObject();

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
