#pragma once
#include <stdbool.h>
#include <stdint.h>

#define CFG_NVS_NAMESPACE        "app_cfg"
#define CFG_MAX_STR              128
#define CFG_MAX_SSID             33
#define CFG_MAX_PASSPHRASE       65
#define CFG_SWITCH_COUNT_MAX     16
#define CFG_SOCKET_COUNT_MAX     16

/* Socket channel per-channel auto-reset bitmask */
typedef uint16_t cfg_channel_mask_t;  /* bit N = channel N+1 enabled */

typedef struct {
    /* WiFi */
    char wifi_ssid[CFG_MAX_SSID];
    char wifi_pass[CFG_MAX_PASSPHRASE];
    bool wifi_ap_disabled;  /* when true: never start provisioning AP, even if STA fails */

    /* Tuya cloud credentials (can override Kconfig at runtime) */
    char tuya_pid[CFG_MAX_STR];
    char tuya_uuid[CFG_MAX_STR];
    char tuya_auth_key[CFG_MAX_STR];
    char tuya_host[CFG_MAX_STR];   /* MQTT broker host, e.g. m1.tuyacn.com / m1.tuyaeu.com / m1.tuyaus.com */

    /* Home Assistant MQTT */
    char mqtt_host[CFG_MAX_STR];
    uint16_t mqtt_port;
    char mqtt_user[CFG_MAX_STR];
    char mqtt_pass[CFG_MAX_STR];
    char mqtt_topic_prefix[CFG_MAX_STR];

    /* Bridge channel counts */
    uint8_t switch_count;   /* DPs 1..switch_count */
    uint8_t socket_count;   /* DPs 101..100+socket_count */

    /* Per-socket auto-reset mask: bit i = socket channel i+1 auto-resets */
    cfg_channel_mask_t socket_auto_reset_mask;
    uint32_t socket_auto_reset_ms;

    /* Device */
    char device_name[CFG_MAX_STR];
} app_config_t;

/**
 * Load config from NVS into *cfg.
 * Falls back to Kconfig defaults for any field not saved in NVS.
 * Returns ESP_OK on success.
 */
esp_err_t config_load(app_config_t *cfg);

/**
 * Save config to NVS.
 */
esp_err_t config_save(const app_config_t *cfg);

/**
 * Erase all saved config from NVS (factory reset helper).
 */
esp_err_t config_erase(void);

/**
 * Apply a JSON blob to an existing config struct.
 * Only keys present in the JSON are updated.
 * JSON format mirrors config-example.json.
 * Returns ESP_OK on success.
 */
esp_err_t config_apply_json(app_config_t *cfg, const char *json_str);

/**
 * Serialize config to a JSON string. Caller must free() the result.
 */
char *config_to_json(const app_config_t *cfg);
