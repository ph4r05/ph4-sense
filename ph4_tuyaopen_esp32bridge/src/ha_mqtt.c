#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_err.h"
#include "mqtt_client.h"
#include "config.h"
#include "ha_mqtt.h"

static const char *TAG = "ha_mqtt";

/* ------------------------------------------------------------------ */
/* Internal state                                                       */
/* ------------------------------------------------------------------ */
static esp_mqtt_client_handle_t s_client    = NULL;
static ha_mqtt_state_t          s_state     = HA_MQTT_STATE_DISCONNECTED;
static ha_mqtt_msg_cb_t         s_msg_cb    = NULL;
static ha_mqtt_state_cb_t       s_state_cb  = NULL;
static void                    *s_user_data = NULL;
static char                     s_prefix[CFG_MAX_STR];

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
static void subscribe_all(esp_mqtt_client_handle_t client)
{
    char topic[256];

    /* Switch commands from HA: ph4/bridge/switch/+/set */
    build_topic("switch/+/set", topic, sizeof(topic));
    esp_mqtt_client_subscribe(client, topic, 1);
    ESP_LOGI(TAG, "Subscribed: %s", topic);

    /* Socket overrides from HA (optional): ph4/bridge/socket/+/set */
    build_topic("socket/+/set", topic, sizeof(topic));
    esp_mqtt_client_subscribe(client, topic, 1);
    ESP_LOGI(TAG, "Subscribed: %s", topic);

    /* Control commands: ph4/bridge/cmd */
    build_topic("cmd", topic, sizeof(topic));
    esp_mqtt_client_subscribe(client, topic, 1);
    ESP_LOGI(TAG, "Subscribed: %s", topic);
}

/* ------------------------------------------------------------------ */
/* MQTT event handler                                                   */
/* ------------------------------------------------------------------ */
static void mqtt_event_handler(void *arg, esp_event_base_t base,
                               int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;

    switch (event->event_id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "MQTT connected to broker");
        set_state(HA_MQTT_STATE_CONNECTED);
        subscribe_all(event->client);

        /* Publish online status */
        ha_mqtt_publish_status("{\"status\":\"online\"}");
        break;

    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "MQTT disconnected");
        set_state(HA_MQTT_STATE_DISCONNECTED);
        break;

    case MQTT_EVENT_SUBSCRIBED:
        ESP_LOGD(TAG, "MQTT subscribed, msg_id=%d", event->msg_id);
        break;

    case MQTT_EVENT_DATA:
        if (event->topic && event->data && s_msg_cb) {
            /* Make NUL-terminated copies (event data is not NUL-terminated) */
            char *topic = strndup(event->topic, event->topic_len);
            char *data  = strndup(event->data,  event->data_len);
            if (topic && data) {
                ESP_LOGD(TAG, "MQTT msg: %s = %s", topic, data);
                s_msg_cb(topic, data, s_user_data);
            }
            free(topic);
            free(data);
        }
        break;

    case MQTT_EVENT_ERROR:
        ESP_LOGE(TAG, "MQTT error");
        set_state(HA_MQTT_STATE_ERROR);
        break;

    case MQTT_EVENT_BEFORE_CONNECT:
        set_state(HA_MQTT_STATE_CONNECTING);
        break;

    default:
        break;
    }
}

/* ------------------------------------------------------------------ */
/* Public API                                                           */
/* ------------------------------------------------------------------ */
esp_err_t ha_mqtt_start(const app_config_t *cfg,
                        ha_mqtt_msg_cb_t    msg_cb,
                        ha_mqtt_state_cb_t  state_cb,
                        void               *user_data)
{
    s_msg_cb    = msg_cb;
    s_state_cb  = state_cb;
    s_user_data = user_data;
    strlcpy(s_prefix, cfg->mqtt_topic_prefix, sizeof(s_prefix));

    if (strlen(cfg->mqtt_host) == 0) {
        ESP_LOGE(TAG, "MQTT host not configured");
        return ESP_ERR_INVALID_ARG;
    }

    char broker_uri[256];
    snprintf(broker_uri, sizeof(broker_uri), "mqtt://%s:%d",
             cfg->mqtt_host, cfg->mqtt_port);

    /* Build LWT topic: {prefix}/status */
    char lwt_topic[256];
    build_topic("status", lwt_topic, sizeof(lwt_topic));

    const esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri         = broker_uri,
        .credentials.username       = cfg->mqtt_user[0] ? cfg->mqtt_user : NULL,
        .credentials.authentication.password =
                                      cfg->mqtt_pass[0] ? cfg->mqtt_pass : NULL,
        .credentials.client_id      = cfg->device_name,
        .session.keepalive          = CONFIG_HA_MQTT_KEEPALIVE_S,
        .session.last_will.topic    = lwt_topic,
        .session.last_will.msg      = "{\"status\":\"offline\"}",
        .session.last_will.msg_len  = 20,
        .session.last_will.qos      = 1,
        .session.last_will.retain   = 1,
        .network.reconnect_timeout_ms = 5000,
    };

    s_client = esp_mqtt_client_init(&mqtt_cfg);
    if (!s_client) {
        ESP_LOGE(TAG, "Failed to init MQTT client");
        return ESP_FAIL;
    }

    ESP_ERROR_CHECK(esp_mqtt_client_register_event(
        s_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL));

    esp_err_t err = esp_mqtt_client_start(s_client);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_mqtt_client_start failed: %s", esp_err_to_name(err));
        esp_mqtt_client_destroy(s_client);
        s_client = NULL;
        return err;
    }

    ESP_LOGI(TAG, "MQTT client started, broker: %s", broker_uri);
    return ESP_OK;
}

esp_err_t ha_mqtt_publish_bool(const char *suffix, bool value)
{
    return ha_mqtt_publish(suffix, value ? "ON" : "OFF", 1, false);
}

esp_err_t ha_mqtt_publish(const char *suffix, const char *payload, int qos, bool retain)
{
    if (!s_client || s_state != HA_MQTT_STATE_CONNECTED) {
        ESP_LOGW(TAG, "MQTT publish skipped (not connected): %s", suffix);
        return ESP_ERR_INVALID_STATE;
    }

    char topic[256];
    build_topic(suffix, topic, sizeof(topic));

    int msg_id = esp_mqtt_client_publish(s_client, topic, payload,
                                         strlen(payload), qos, retain);
    if (msg_id < 0) {
        ESP_LOGE(TAG, "Publish failed: %s", topic);
        return ESP_FAIL;
    }

    ESP_LOGD(TAG, "Published %s = %s", topic, payload);
    return ESP_OK;
}

esp_err_t ha_mqtt_publish_switch_state(uint8_t channel, bool value)
{
    char suffix[64];
    snprintf(suffix, sizeof(suffix), "switch/%d/state", channel);
    return ha_mqtt_publish_bool(suffix, value);
}

esp_err_t ha_mqtt_publish_socket_state(uint8_t channel, bool value)
{
    char suffix[64];
    snprintf(suffix, sizeof(suffix), "socket/%d/state", channel);
    return ha_mqtt_publish_bool(suffix, value);
}

esp_err_t ha_mqtt_publish_status(const char *json)
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
        esp_mqtt_client_stop(s_client);
        esp_mqtt_client_destroy(s_client);
        s_client = NULL;
    }
    s_state = HA_MQTT_STATE_DISCONNECTED;
}
