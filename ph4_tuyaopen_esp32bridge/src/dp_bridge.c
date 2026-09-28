#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "tal_api.h"
#include "config.h"
#include "tuya_cloud.h"
#include "dp_bridge.h"
#include "dp_map.h"

#if __has_include("ha_mqtt.h")
#include "ha_mqtt.h"
#define HA_MQTT_ENABLED 1
#else
#define HA_MQTT_ENABLED 0
/* Stubs when HA MQTT is not available */
static inline OPERATE_RET ha_mqtt_publish_switch_state(uint8_t ch, bool v) { return OPRT_OK; }
static inline OPERATE_RET ha_mqtt_publish_socket_state(uint8_t ch, bool v) { return OPRT_OK; }
static inline OPERATE_RET ha_mqtt_publish_status(const char *j) { return OPRT_OK; }
typedef int ha_mqtt_state_t;
#define HA_MQTT_STATE_CONNECTED 2
static inline ha_mqtt_state_t ha_mqtt_get_state(void) { return 0; }
#endif

/* DP layout — see dp_map.h; DP IDs are NOT a linear base+offset range */

/* ------------------------------------------------------------------ */
/* Auto-reset timer state per socket channel                           */
/* ------------------------------------------------------------------ */
typedef struct {
    TIMER_ID timer;
    uint8_t  channel;  /* 1-based */
} socket_reset_ctx_t;

/* ------------------------------------------------------------------ */
/* Internal state                                                       */
/* ------------------------------------------------------------------ */
static const app_config_t  *s_cfg = NULL;
static bool s_switch_state[CFG_SWITCH_COUNT_MAX] = {false};
static bool s_socket_state[CFG_SOCKET_COUNT_MAX] = {false};

static socket_reset_ctx_t s_reset_ctx[CFG_SOCKET_COUNT_MAX];
static socket_reset_ctx_t s_switch_pulse_ctx[CFG_SWITCH_COUNT_MAX];

/* ------------------------------------------------------------------ */
/* Auto-reset timer callback                                            */
/* ------------------------------------------------------------------ */
static void socket_auto_reset_cb(TIMER_ID timer_id, void *arg)
{
    socket_reset_ctx_t *ctx = (socket_reset_ctx_t *)arg;
    uint8_t ch = ctx->channel;

    PR_INFO("Socket ch%d auto-reset -> OFF", ch);

    s_socket_state[ch - 1] = false;
    tuya_cloud_report_bool(relay_channel_to_dp(ch), false);
    ha_mqtt_publish_socket_state(ch, false);
}

static void switch_pulse_reset_cb(TIMER_ID timer_id, void *arg)
{
    socket_reset_ctx_t *ctx = (socket_reset_ctx_t *)arg;
    uint8_t ch = ctx->channel;

    PR_INFO("Switch ch%d pulse -> OFF", ch);

    s_switch_state[ch - 1] = false;
    tuya_cloud_report_bool(switch_channel_to_dp(ch), false);
    ha_mqtt_publish_switch_state(ch, false);
}

/* ------------------------------------------------------------------ */
/* Socket trigger handler                                               */
/* ------------------------------------------------------------------ */
static void handle_socket_trigger(uint8_t channel, bool value)
{
    if (channel < 1 || channel > s_cfg->socket_count) {
        PR_WARN("Socket channel %d out of range", channel);
        return;
    }

    s_socket_state[channel - 1] = value;
    ha_mqtt_publish_socket_state(channel, value);

    if (!value) return;

    bool auto_reset = (s_cfg->socket_auto_reset_mask >> (channel - 1)) & 1;
    uint32_t reset_ms = s_cfg->socket_auto_reset_ms;

    if (auto_reset && reset_ms > 0) {
        socket_reset_ctx_t *ctx = &s_reset_ctx[channel - 1];
        if (ctx->timer == NULL) {
            ctx->channel = channel;
            tal_sw_timer_create(socket_auto_reset_cb, ctx, &ctx->timer);
        }
        tal_sw_timer_stop(ctx->timer);
        tal_sw_timer_start(ctx->timer, reset_ms, TAL_TIMER_ONCE);
        PR_DEBUG("Socket ch%d auto-reset in %d ms", channel, (int)reset_ms);
    }
}

/* ------------------------------------------------------------------ */
/* Switch channel: HA -> Tuya                                           */
/* ------------------------------------------------------------------ */
static void handle_switch_set(uint8_t channel, bool value)
{
    if (channel < 1 || channel > s_cfg->switch_count) {
        PR_WARN("Switch channel %d out of range", channel);
        return;
    }

    PR_INFO("Switch ch%d -> %s (from HA)", channel, value ? "ON" : "OFF");
    s_switch_state[channel - 1] = value;
    tuya_cloud_report_bool(switch_channel_to_dp(channel), value);
    ha_mqtt_publish_switch_state(channel, value);
}

/* Direct socket set (no auto-reset) -- shared by the /set and /toggle
 * MQTT handlers. Caller must bounds-check channel first. */
static void set_socket_direct(uint8_t channel, bool value)
{
    PR_INFO("Socket ch%d manually set to %s by HA", channel, value ? "ON" : "OFF");
    s_socket_state[channel - 1] = value;
    tuya_cloud_report_bool(relay_channel_to_dp(channel), value);
    ha_mqtt_publish_socket_state(channel, value);
}

/* ------------------------------------------------------------------ */
/* HA-triggered momentary pulse (switch or socket)                      */
/*                                                                       */
/* Unlike handle_socket_trigger() (called when a DP change already came */
/* FROM Tuya, so the ON edge doesn't need reporting back), these report */
/* the ON edge to Tuya cloud too, since it's new information from HA.   */
/* ------------------------------------------------------------------ */
static void handle_switch_pulse(uint8_t channel)
{
    if (channel < 1 || channel > s_cfg->switch_count) {
        PR_WARN("Switch channel %d out of range (pulse)", channel);
        return;
    }
    uint32_t pulse_ms = s_cfg->socket_auto_reset_ms;
    if (pulse_ms == 0) {
        PR_WARN("Switch ch%d pulse requested but auto_reset_ms=0, ignoring", channel);
        return;
    }

    PR_INFO("Switch ch%d pulse -> ON (%d ms, from HA)", channel, (int)pulse_ms);
    s_switch_state[channel - 1] = true;
    tuya_cloud_report_bool(switch_channel_to_dp(channel), true);
    ha_mqtt_publish_switch_state(channel, true);

    socket_reset_ctx_t *ctx = &s_switch_pulse_ctx[channel - 1];
    if (ctx->timer == NULL) {
        ctx->channel = channel;
        tal_sw_timer_create(switch_pulse_reset_cb, ctx, &ctx->timer);
    }
    tal_sw_timer_stop(ctx->timer);
    tal_sw_timer_start(ctx->timer, pulse_ms, TAL_TIMER_ONCE);
}

static void handle_socket_pulse(uint8_t channel)
{
    if (channel < 1 || channel > s_cfg->socket_count) {
        PR_WARN("Socket channel %d out of range (pulse)", channel);
        return;
    }
    uint32_t pulse_ms = s_cfg->socket_auto_reset_ms;
    if (pulse_ms == 0) {
        PR_WARN("Socket ch%d pulse requested but auto_reset_ms=0, ignoring", channel);
        return;
    }

    PR_INFO("Socket ch%d pulse -> ON (%d ms, from HA)", channel, (int)pulse_ms);
    s_socket_state[channel - 1] = true;
    tuya_cloud_report_bool(relay_channel_to_dp(channel), true);
    ha_mqtt_publish_socket_state(channel, true);

    socket_reset_ctx_t *ctx = &s_reset_ctx[channel - 1];
    if (ctx->timer == NULL) {
        ctx->channel = channel;
        tal_sw_timer_create(socket_auto_reset_cb, ctx, &ctx->timer);
    }
    tal_sw_timer_stop(ctx->timer);
    tal_sw_timer_start(ctx->timer, pulse_ms, TAL_TIMER_ONCE);
}

/* ------------------------------------------------------------------ */
/* Control commands                                                     */
/* ------------------------------------------------------------------ */
static void handle_cmd(const char *cmd)
{
    PR_INFO("Command: %s", cmd);

    if (strcmp(cmd, "reset") == 0) {
        PR_WARN("Factory reset requested via MQTT");
        tuya_cloud_factory_reset();
        return;
    }
    if (strcmp(cmd, "reboot") == 0) {
        PR_WARN("Reboot requested via MQTT");
        tal_system_reset();
        return;
    }
    if (strcmp(cmd, "sync") == 0) {
        PR_INFO("Syncing all DPs to Tuya cloud");
        tuya_cloud_report_all();
        return;
    }
    if (strcmp(cmd, "status") == 0) {
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
    PR_WARN("Unknown command: %s", cmd);
}

/* ------------------------------------------------------------------ */
/* MQTT topic parser                                                    */
/* ------------------------------------------------------------------ */
static void parse_mqtt_topic(const char *topic, const char *data)
{
    const char *prefix = s_cfg->mqtt_topic_prefix;
    size_t plen = strlen(prefix);

    if (strncmp(topic, prefix, plen) != 0) return;
    const char *rest = topic + plen;

    if (strcmp(rest, "/cmd") == 0) {
        handle_cmd(data);
        return;
    }

    /* Parse "/switch/{n}/{leaf}" or "/socket/{n}/{leaf}" as three distinct
     * tokens and dispatch by exact strcmp on the leaf -- NOT by sscanf'ing
     * a literal suffix like "/switch/%d/set" and trusting a return value of
     * 1. That pattern is a footgun: sscanf() counts %d as matched and
     * returns 1 even when the *rest* of the literal text doesn't match
     * (e.g. "/switch/2/state" against format "/switch/%d/set" -- "2" gets
     * assigned before the "/set" vs "/state" literal mismatch is hit), so
     * it silently accepts topics it was never meant to. This bit in
     * production: after broadening the subscription (see subscribe_all()
     * in ha_mqtt.c) to also catch /toggle and /pulse, the device started
     * receiving its own .../switch/{n}/state publishes back and misfiring
     * them as "set" commands -- a feedback loop that rapidly cycled a
     * relay. Both the subscription and this parser needed fixing. */
    char kind[8] = {0};
    char leaf[8] = {0};
    int channel = 0;
    if (sscanf(rest, "/%7[a-z]/%d/%7s", kind, &channel, leaf) != 3 || channel <= 0) {
        PR_DEBUG("Unhandled MQTT topic: %s", topic);
        return;
    }

    bool is_switch = (strcmp(kind, "switch") == 0);
    bool is_socket = (!is_switch && strcmp(kind, "socket") == 0);
    if (!is_switch && !is_socket) {
        PR_DEBUG("Unhandled MQTT topic: %s", topic);
        return;
    }

    bool value = (strcmp(data, "ON") == 0 || strcmp(data, "1") == 0 ||
                  strcmp(data, "true") == 0);

    if (strcmp(leaf, "set") == 0) {
        if (is_switch) {
            handle_switch_set((uint8_t)channel, value);
        } else if (channel <= CFG_SOCKET_COUNT_MAX) {
            set_socket_direct((uint8_t)channel, value);
        } else {
            PR_WARN("Socket channel %d out of range", channel);
        }
        return;
    }

    /* Toggle: flip whatever the channel's current state is, so HA doesn't
     * need to read state first -- any payload triggers it. Sockets keep
     * their persistent state, same as /set: no auto-reset here. */
    if (strcmp(leaf, "toggle") == 0) {
        if (is_switch) {
            if (channel <= CFG_SWITCH_COUNT_MAX) {
                handle_switch_set((uint8_t)channel, !s_switch_state[channel - 1]);
            } else {
                PR_WARN("Switch channel %d out of range (toggle)", channel);
            }
        } else {
            if (channel <= CFG_SOCKET_COUNT_MAX) {
                set_socket_direct((uint8_t)channel, !s_socket_state[channel - 1]);
            } else {
                PR_WARN("Socket channel %d out of range (toggle)", channel);
            }
        }
        return;
    }

    /* Pulse: momentary ON then auto-reset OFF after socket_auto_reset_ms --
     * any payload triggers it. For switch channels this is a momentary
     * override of otherwise-persistent behavior. */
    if (strcmp(leaf, "pulse") == 0) {
        if (is_switch) {
            handle_switch_pulse((uint8_t)channel);
        } else {
            handle_socket_pulse((uint8_t)channel);
        }
        return;
    }

    PR_DEBUG("Unhandled MQTT topic: %s", topic);
}

/* ------------------------------------------------------------------ */
/* Public callbacks                                                     */
/* ------------------------------------------------------------------ */
void dp_bridge_on_tuya_dp(uint8_t dp_id, bool value, void *user_data)
{
    int sw_ch = dp_to_switch_channel(dp_id);
    int sk_ch = dp_to_relay_channel(dp_id);

    if (sw_ch >= 1 && sw_ch <= s_cfg->switch_count) {
        PR_INFO("Tuya -> switch ch%d = %s", sw_ch, value ? "ON" : "OFF");
        s_switch_state[sw_ch - 1] = value;
        ha_mqtt_publish_switch_state((uint8_t)sw_ch, value);
        return;
    }

    if (sk_ch >= 1 && sk_ch <= s_cfg->socket_count) {
        PR_INFO("Tuya -> socket ch%d = %s", sk_ch, value ? "ON" : "OFF");
        handle_socket_trigger((uint8_t)sk_ch, value);
        return;
    }

    PR_WARN("Unhandled Tuya DP %d = %s", dp_id, value ? "true" : "false");
}

void dp_bridge_on_mqtt_msg(const char *topic, const char *data, void *user_data)
{
    parse_mqtt_topic(topic, data);
}

void dp_bridge_on_tuya_state(int tuya_state, void *user_data)
{
    PR_INFO("Tuya state -> %d", tuya_state);
    if (tuya_state == TUYA_STATE_CONNECTED) {
        handle_cmd("status");
    }
}

void dp_bridge_on_mqtt_state(int mqtt_state, void *user_data)
{
    PR_INFO("MQTT state -> %d", mqtt_state);
    if (mqtt_state == HA_MQTT_STATE_CONNECTED) {
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
OPERATE_RET dp_bridge_init(const app_config_t *cfg)
{
    s_cfg = cfg;
    memset(s_switch_state, 0, sizeof(s_switch_state));
    memset(s_socket_state, 0, sizeof(s_socket_state));
    memset(s_reset_ctx,    0, sizeof(s_reset_ctx));
    memset(s_switch_pulse_ctx, 0, sizeof(s_switch_pulse_ctx));

    PR_INFO("Bridge initialized: %d switch + %d socket channels",
             cfg->switch_count, cfg->socket_count);
    for (uint8_t i = 1; i <= cfg->switch_count; i++) {
        PR_INFO("  switch ch%d -> DP %d", i, switch_channel_to_dp(i));
    }
    for (uint8_t i = 1; i <= cfg->socket_count; i++) {
        PR_INFO("  socket ch%d -> DP %d", i, relay_channel_to_dp(i));
    }
    PR_INFO("Socket auto-reset: %d ms, mask=0x%04X",
             (int)cfg->socket_auto_reset_ms,
             cfg->socket_auto_reset_mask);
    return OPRT_OK;
}

OPERATE_RET dp_bridge_set_switch(uint8_t channel, bool value)
{
    handle_switch_set(channel, value);
    return OPRT_OK;
}
