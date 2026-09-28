/**
 * ha_mqtt.c — Home Assistant MQTT client, built on TuyaOpen's portable
 * mqtt_client_interface.h (libmqtt) rather than ESP-IDF's esp_mqtt_client,
 * since app code here only sees TuyaOpen's tal_ and libmqtt headers, not raw
 * ESP-IDF ones (see HISTORY.md). This is the same MQTT client TuyaOpen uses
 * internally for its own cloud connection.
 *
 * Runs its own connect/yield loop on a dedicated TAL thread, since the main
 * loop in app_main.c only pumps tuya_iot_yield() for the Tuya cloud link.
 *
 * Known limitation: mqtt_client_interface.h has no last-will/testament
 * option, so unlike the TuyaLink-era ESP-IDF version, the broker won't
 * auto-publish "offline" on an unclean disconnect — only ha_mqtt_stop()
 * publishes it explicitly.
 */

#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include "tal_api.h"
#include "mqtt_client_interface.h"
#include "config.h"
#include "ha_mqtt.h"

#define HA_MQTT_KEEPALIVE_S   60
#define HA_MQTT_TIMEOUT_MS    5000
#define HA_MQTT_RETRY_MS      5000
#define HA_MQTT_YIELD_MS      100

/* ------------------------------------------------------------------ */
/* Internal state                                                       */
/* ------------------------------------------------------------------ */
static void                    *s_client    = NULL;
static ha_mqtt_state_t          s_state     = HA_MQTT_STATE_DISCONNECTED;
static ha_mqtt_msg_cb_t         s_msg_cb    = NULL;
static ha_mqtt_state_cb_t       s_state_cb  = NULL;
static void                    *s_user_data = NULL;
static char                     s_prefix[CFG_MAX_STR];
static char                     s_host[CFG_MAX_STR];
static char                     s_user[CFG_MAX_STR];
static char                     s_pass[CFG_MAX_STR];
static char                     s_clientid[CFG_MAX_STR];
static uint16_t                 s_port;

static THREAD_HANDLE             s_thread    = NULL;
static volatile bool             s_running   = false;

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */
static void set_state(ha_mqtt_state_t new_state)
{
    if (s_state == new_state) return;
    s_state = new_state;
    if (s_state_cb) s_state_cb(new_state, s_user_data);
}

/** Build topic: {prefix}/{suffix} -> out_buf (caller ensures space) */
static void build_topic(const char *suffix, char *out_buf, size_t out_size)
{
    snprintf(out_buf, out_size, "%s/%s", s_prefix, suffix);
}

/* ------------------------------------------------------------------ */
/* Subscribe on connect                                                  */
/* ------------------------------------------------------------------ */
static void subscribe_all(void *client)
{
    char topic[256];

    /* Switch commands from HA: ph4/bridge/switch/+/set */
    build_topic("switch/+/set", topic, sizeof(topic));
    mqtt_client_subscribe(client, topic, 1);
    PR_INFO("Subscribed: %s", topic);

    /* Socket overrides from HA (optional): ph4/bridge/socket/+/set */
    build_topic("socket/+/set", topic, sizeof(topic));
    mqtt_client_subscribe(client, topic, 1);
    PR_INFO("Subscribed: %s", topic);

    /* Control commands: ph4/bridge/cmd */
    build_topic("cmd", topic, sizeof(topic));
    mqtt_client_subscribe(client, topic, 1);
    PR_INFO("Subscribed: %s", topic);
}

/* ------------------------------------------------------------------ */
/* MQTT client callbacks                                                */
/* ------------------------------------------------------------------ */
static void on_connected(void *client, void *userdata)
{
    PR_INFO("MQTT connected to broker");
    set_state(HA_MQTT_STATE_CONNECTED);
    subscribe_all(client);
    ha_mqtt_publish_status("{\"status\":\"online\"}");
}

static void on_disconnected(void *client, void *userdata)
{
    PR_WARN("MQTT disconnected");
    set_state(HA_MQTT_STATE_DISCONNECTED);
}

static void on_message(void *client, uint16_t msgid, const mqtt_client_message_t *msg, void *userdata)
{
    if (!msg || !msg->topic || !s_msg_cb) return;

    /* topic is a NUL-terminated string; payload is length-based, needs a copy */
    char *data = malloc(msg->length + 1);
    if (!data) return;
    memcpy(data, msg->payload, msg->length);
    data[msg->length] = '\0';

    PR_DEBUG("MQTT msg: %s = %s", msg->topic, data);
    s_msg_cb(msg->topic, data, s_user_data);
    free(data);
}

/* ------------------------------------------------------------------ */
/* Connect/yield thread                                                 */
/* ------------------------------------------------------------------ */
static void ha_mqtt_thread(void *arg)
{
    while (s_running) {
        if (s_state != HA_MQTT_STATE_CONNECTED) {
            set_state(HA_MQTT_STATE_CONNECTING);
            mqtt_client_status_t st = mqtt_client_connect(s_client);
            if (st != MQTT_STATUS_SUCCESS) {
                PR_WARN("MQTT connect failed: %d, retrying in %d ms", (int)st, HA_MQTT_RETRY_MS);
                set_state(HA_MQTT_STATE_DISCONNECTED);
                tal_system_sleep(HA_MQTT_RETRY_MS);
                continue;
            }
        }
        mqtt_client_yield(s_client);
        tal_system_sleep(HA_MQTT_YIELD_MS);
    }
}

/* ------------------------------------------------------------------ */
/* Public API                                                           */
/* ------------------------------------------------------------------ */
OPERATE_RET ha_mqtt_start(const app_config_t *cfg,
                        ha_mqtt_msg_cb_t    msg_cb,
                        ha_mqtt_state_cb_t  state_cb,
                        void               *user_data)
{
    s_msg_cb    = msg_cb;
    s_state_cb  = state_cb;
    s_user_data = user_data;

    if (strlen(cfg->mqtt_host) == 0) {
        PR_ERR("MQTT host not configured");
        return OPRT_INVALID_PARM;
    }

    strncpy(s_prefix,   cfg->mqtt_topic_prefix, sizeof(s_prefix) - 1);
    strncpy(s_host,     cfg->mqtt_host,         sizeof(s_host) - 1);
    strncpy(s_user,     cfg->mqtt_user,         sizeof(s_user) - 1);
    strncpy(s_pass,     cfg->mqtt_pass,         sizeof(s_pass) - 1);
    strncpy(s_clientid, cfg->device_name,       sizeof(s_clientid) - 1);
    s_port = cfg->mqtt_port;

    s_client = mqtt_client_new();
    if (!s_client) {
        PR_ERR("Failed to allocate MQTT client");
        return OPRT_MALLOC_FAILED;
    }

    const mqtt_client_config_t mcfg = {
        .host           = s_host,
        .port           = s_port,
        .keepalive      = HA_MQTT_KEEPALIVE_S,
        .timeout_ms     = HA_MQTT_TIMEOUT_MS,
        .clientid       = s_clientid,
        /* TuyaOpen's mqtt_client_wrapper.c calls strlen(username/password)
         * unconditionally in mqtt_client_connect() with no NULL check -- it
         * crashes (Guru Meditation, Load access fault) if these are NULL.
         * Empty strings are safe (strlen("") == 0) for an anonymous broker. */
        .username       = s_user,
        .password       = s_pass,
        .userdata       = NULL,
        .on_connected   = on_connected,
        .on_disconnected = on_disconnected,
        .on_message     = on_message,
    };

    mqtt_client_status_t st = mqtt_client_init(s_client, &mcfg);
    if (st != MQTT_STATUS_SUCCESS) {
        PR_ERR("mqtt_client_init failed: %d", (int)st);
        mqtt_client_free(s_client);
        s_client = NULL;
        return OPRT_COM_ERROR;
    }

    s_running = true;
    THREAD_CFG_T thread_cfg = {
        .stackDepth = 1024 * 4,
        .priority   = THREAD_PRIO_2,
        .thrdname   = "ha_mqtt",
    };
    OPERATE_RET rt = tal_thread_create_and_start(&s_thread, NULL, NULL,
                                                  ha_mqtt_thread, NULL, &thread_cfg);
    if (rt != OPRT_OK) {
        PR_ERR("Failed to start HA MQTT thread: %d", rt);
        s_running = false;
        mqtt_client_free(s_client);
        s_client = NULL;
        return rt;
    }

    PR_INFO("MQTT client starting, broker: %s:%d", s_host, s_port);
    return OPRT_OK;
}

OPERATE_RET ha_mqtt_publish_bool(const char *suffix, bool value)
{
    return ha_mqtt_publish(suffix, value ? "ON" : "OFF", 1, false);
}

OPERATE_RET ha_mqtt_publish(const char *suffix, const char *payload, int qos, bool retain)
{
    if (!s_client || s_state != HA_MQTT_STATE_CONNECTED) {
        PR_WARN("MQTT publish skipped (not connected): %s", suffix);
        return OPRT_COM_ERROR;
    }

    char topic[256];
    build_topic(suffix, topic, sizeof(topic));

    /* retain is not exposed by mqtt_client_interface.h; ignored for now */
    (void)retain;
    mqtt_client_publish(s_client, topic, (const uint8_t *)payload, strlen(payload), (uint8_t)qos);

    PR_DEBUG("Published %s = %s", topic, payload);
    return OPRT_OK;
}

OPERATE_RET ha_mqtt_publish_switch_state(uint8_t channel, bool value)
{
    char suffix[64];
    snprintf(suffix, sizeof(suffix), "switch/%d/state", channel);
    return ha_mqtt_publish_bool(suffix, value);
}

OPERATE_RET ha_mqtt_publish_socket_state(uint8_t channel, bool value)
{
    char suffix[64];
    snprintf(suffix, sizeof(suffix), "socket/%d/state", channel);
    return ha_mqtt_publish_bool(suffix, value);
}

OPERATE_RET ha_mqtt_publish_status(const char *json)
{
    return ha_mqtt_publish("status", json, 1, true);
}

ha_mqtt_state_t ha_mqtt_get_state(void)
{
    return s_state;
}

void ha_mqtt_stop(void)
{
    if (s_client) {
        ha_mqtt_publish_status("{\"status\":\"offline\"}");
        s_running = false;
        if (s_thread) {
            tal_thread_delete(s_thread);
            s_thread = NULL;
        }
        mqtt_client_disconnect(s_client);
        mqtt_client_deinit(s_client);
        mqtt_client_free(s_client);
        s_client = NULL;
    }
    s_state = HA_MQTT_STATE_DISCONNECTED;
}
