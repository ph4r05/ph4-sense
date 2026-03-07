#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/timers.h"
#include "esp_log.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "config.h"
#include "tuya_cloud.h"
#include "ha_mqtt.h"
#include "dp_bridge.h"

static const char *TAG = "dp_bridge";

/* ------------------------------------------------------------------ */
/* DP layout                                                            */
/* ------------------------------------------------------------------ */
#define SWITCH_DP(ch)   ((uint8_t)((ch)))                        /* ch 1-based -> DP 1..16  */
#define SOCKET_DP(ch)   ((uint8_t)(CONFIG_BRIDGE_SOCKET_DP_BASE + (ch) - 1))  /* ch 1-based -> DP 101..116 */
#define DP_TO_SWITCH(dp) ((int)(dp))                             /* 1-based channel or 0    */
#define DP_TO_SOCKET(dp) ((int)((dp) - CONFIG_BRIDGE_SOCKET_DP_BASE + 1))     /* 1-based channel or 0    */

/* ------------------------------------------------------------------ */
/* Auto-reset timer state per socket channel                           */
/* ------------------------------------------------------------------ */
typedef struct {
    esp_timer_handle_t timer;
    uint8_t            channel;  /* 1-based */
} socket_reset_ctx_t;

/* ------------------------------------------------------------------ */
/* Internal state                                                       */
/* ------------------------------------------------------------------ */
static const app_config_t  *s_cfg = NULL;
static bool s_switch_state[CFG_SWITCH_COUNT_MAX] = {false};
static bool s_socket_state[CFG_SOCKET_COUNT_MAX] = {false};

static socket_reset_ctx_t s_reset_ctx[CFG_SOCKET_COUNT_MAX];

/* ------------------------------------------------------------------ */
/* Auto-reset timer callback                                            */
/* ------------------------------------------------------------------ */
static void socket_auto_reset_cb(void *arg)
{
    socket_reset_ctx_t *ctx = (socket_reset_ctx_t *)arg;
    uint8_t ch = ctx->channel;

    ESP_LOGI(TAG, "Socket ch%d auto-reset -> OFF", ch);

    s_socket_state[ch - 1] = false;

    /* Report to Tuya: DP back to false */
    tuya_cloud_report_bool(SOCKET_DP(ch), false);

    /* Publish to HA */
    ha_mqtt_publish_socket_state(ch, false);
}

/* ------------------------------------------------------------------ */
/* Socket trigger handler                                               */
/* ------------------------------------------------------------------ */
static void handle_socket_trigger(uint8_t channel, bool value)
{
    if (channel < 1 || channel > s_cfg->socket_count) {
        ESP_LOGW(TAG, "Socket channel %d out of range", channel);
        return;
    }

    s_socket_state[channel - 1] = value;

    /* Publish trigger to HA */
    ha_mqtt_publish_socket_state(channel, value);

    if (!value) return; /* Only trigger on ON */

    /* Schedule auto-reset if enabled for this channel */
    bool auto_reset = (s_cfg->socket_auto_reset_mask >> (channel - 1)) & 1;
    uint32_t reset_ms = s_cfg->socket_auto_reset_ms;

    if (auto_reset && reset_ms > 0) {
        socket_reset_ctx_t *ctx = &s_reset_ctx[channel - 1];
        if (ctx->timer == NULL) {
            /* Create one-shot timer */
            ctx->channel = channel;
            const esp_timer_create_args_t ta = {
                .callback = socket_auto_reset_cb,
                .arg      = ctx,
                .name     = "sk_reset",
            };
            esp_timer_create(&ta, &ctx->timer);
        }
        /* (Re-)arm the timer: cancel existing if pending, then start */
        esp_timer_stop(ctx->timer);
        esp_timer_start_once(ctx->timer, (uint64_t)reset_ms * 1000 /* us */);
        ESP_LOGD(TAG, "Socket ch%d auto-reset in %d ms", channel, (int)reset_ms);
    }
}

/* ------------------------------------------------------------------ */
/* Switch channel: HA -> Tuya                                           */
/* ------------------------------------------------------------------ */
static void handle_switch_set(uint8_t channel, bool value)
{
    if (channel < 1 || channel > s_cfg->switch_count) {
        ESP_LOGW(TAG, "Switch channel %d out of range", channel);
        return;
    }

    ESP_LOGI(TAG, "Switch ch%d -> %s (from HA)", channel, value ? "ON" : "OFF");

    s_switch_state[channel - 1] = value;

    /* Report to Tuya cloud */
    tuya_cloud_report_bool(SWITCH_DP(channel), value);

    /* Echo state back to HA */
    ha_mqtt_publish_switch_state(channel, value);
}

/* ------------------------------------------------------------------ */
/* Control commands                                                     */
/* ------------------------------------------------------------------ */
static void handle_cmd(const char *cmd)
{
    ESP_LOGI(TAG, "Command: %s", cmd);

    if (strcmp(cmd, "reset") == 0) {
        ESP_LOGW(TAG, "Factory reset requested via MQTT");
        tuya_cloud_factory_reset();  /* clears Tuya NVS + reboots */
        return;
    }

    if (strcmp(cmd, "reboot") == 0) {
        ESP_LOGW(TAG, "Reboot requested via MQTT");
        esp_restart();
        return;
    }

    if (strcmp(cmd, "sync") == 0) {
        ESP_LOGI(TAG, "Syncing all DPs to Tuya cloud");
        tuya_cloud_report_all();
        return;
    }

    if (strcmp(cmd, "status") == 0) {
        /* Publish a status JSON */
        char buf[256];
        snprintf(buf, sizeof(buf),
            "{\"tuya_state\":%d,\"mqtt_state\":%d,"
            "\"switch_count\":%d,\"socket_count\":%d}",
            (int)tuya_cloud_get_state(),
            (int)ha_mqtt_get_state(),
            s_cfg->switch_count,
            s_cfg->socket_count);
        ha_mqtt_publish_status(buf);
        return;
    }

    ESP_LOGW(TAG, "Unknown command: %s", cmd);
}

/* ------------------------------------------------------------------ */
/* MQTT topic parser                                                    */
/*                                                                      */
/* Expected topic formats:                                              */
/*   {prefix}/switch/{n}/set                                            */
/*   {prefix}/socket/{n}/set                                            */
/*   {prefix}/cmd                                                       */
/* ------------------------------------------------------------------ */
static void parse_mqtt_topic(const char *topic, const char *data)
{
    const char *prefix = s_cfg->mqtt_topic_prefix;
    size_t plen = strlen(prefix);

    if (strncmp(topic, prefix, plen) != 0) return;
    const char *rest = topic + plen;

    /* {prefix}/cmd */
    if (strcmp(rest, "/cmd") == 0) {
        handle_cmd(data);
        return;
    }

    /* {prefix}/switch/{n}/set */
    int channel = 0;
    if (sscanf(rest, "/switch/%d/set", &channel) == 1 && channel > 0) {
        bool value = (strcmp(data, "ON") == 0 || strcmp(data, "1") == 0 ||
                      strcmp(data, "true") == 0);
        handle_switch_set((uint8_t)channel, value);
        return;
    }

    /* {prefix}/socket/{n}/set — allow HA to manually override socket state */
    if (sscanf(rest, "/socket/%d/set", &channel) == 1 && channel > 0) {
        bool value = (strcmp(data, "ON") == 0 || strcmp(data, "1") == 0 ||
                      strcmp(data, "true") == 0);
        ESP_LOGI(TAG, "Socket ch%d manually set to %s by HA", channel, value ? "ON" : "OFF");
        s_socket_state[channel - 1] = value;
        tuya_cloud_report_bool(SOCKET_DP(channel), value);
        ha_mqtt_publish_socket_state((uint8_t)channel, value);
        return;
    }

    ESP_LOGD(TAG, "Unhandled MQTT topic: %s", topic);
}

/* ------------------------------------------------------------------ */
/* Public callbacks (registered with tuya_cloud and ha_mqtt)            */
/* ------------------------------------------------------------------ */
void dp_bridge_on_tuya_dp(uint8_t dp_id, bool value, void *user_data)
{
    /* Determine which direction this DP belongs to */
    int sw_ch = DP_TO_SWITCH(dp_id);
    int sk_ch = DP_TO_SOCKET(dp_id);

    if (sw_ch >= 1 && sw_ch <= s_cfg->switch_count) {
        /* Switch DP changed by cloud (can happen if SmartLife user toggles it directly) */
        ESP_LOGI(TAG, "Tuya -> switch ch%d = %s", sw_ch, value ? "ON" : "OFF");
        s_switch_state[sw_ch - 1] = value;
        ha_mqtt_publish_switch_state((uint8_t)sw_ch, value);
        return;
    }

    if (sk_ch >= 1 && sk_ch <= s_cfg->socket_count) {
        /* Socket DP changed by cloud (SmartLife tapped socket) */
        ESP_LOGI(TAG, "Tuya -> socket ch%d = %s", sk_ch, value ? "ON" : "OFF");
        handle_socket_trigger((uint8_t)sk_ch, value);
        return;
    }

    ESP_LOGW(TAG, "Unhandled Tuya DP %d = %s", dp_id, value ? "true" : "false");
}

void dp_bridge_on_mqtt_msg(const char *topic, const char *data, void *user_data)
{
    parse_mqtt_topic(topic, data);
}

void dp_bridge_on_tuya_state(int tuya_state, void *user_data)
{
    ESP_LOGI(TAG, "Tuya state -> %d", tuya_state);
    /* Optionally publish status update */
    if (tuya_state == TUYA_STATE_CONNECTED) {
        handle_cmd("status");
    }
}

void dp_bridge_on_mqtt_state(int mqtt_state, void *user_data)
{
    ESP_LOGI(TAG, "MQTT state -> %d", mqtt_state);
    if (mqtt_state == HA_MQTT_STATE_CONNECTED) {
        /* Re-publish all current states so HA is in sync after reconnect */
        for (uint8_t i = 0; i < s_cfg->switch_count; i++) {
            ha_mqtt_publish_switch_state(i + 1, s_switch_state[i]);
        }
        for (uint8_t i = 0; i < s_cfg->socket_count; i++) {
            ha_mqtt_publish_socket_state(i + 1, s_socket_state[i]);
        }
    }
}

/* ------------------------------------------------------------------ */
/* Public API                                                           */
/* ------------------------------------------------------------------ */
esp_err_t dp_bridge_init(const app_config_t *cfg)
{
    s_cfg = cfg;
    memset(s_switch_state, 0, sizeof(s_switch_state));
    memset(s_socket_state, 0, sizeof(s_socket_state));
    memset(s_reset_ctx,    0, sizeof(s_reset_ctx));

    ESP_LOGI(TAG, "Bridge initialized: %d switch + %d socket channels",
             cfg->switch_count, cfg->socket_count);
    ESP_LOGI(TAG, "Switch DPs: 1..%d   Socket DPs: %d..%d",
             cfg->switch_count,
             CONFIG_BRIDGE_SOCKET_DP_BASE,
             CONFIG_BRIDGE_SOCKET_DP_BASE + cfg->socket_count - 1);
    ESP_LOGI(TAG, "Socket auto-reset: %d ms, mask=0x%04X",
             (int)cfg->socket_auto_reset_ms,
             cfg->socket_auto_reset_mask);
    return ESP_OK;
}

esp_err_t dp_bridge_set_switch(uint8_t channel, bool value)
{
    handle_switch_set(channel, value);
    return ESP_OK;
}
