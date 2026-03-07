#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "config.h"

/**
 * MQTT connection states.
 */
typedef enum {
    HA_MQTT_STATE_DISCONNECTED,
    HA_MQTT_STATE_CONNECTING,
    HA_MQTT_STATE_CONNECTED,
    HA_MQTT_STATE_ERROR,
} ha_mqtt_state_t;

/**
 * Called when a message arrives on a subscribed MQTT topic.
 *
 * topic: full topic string (NUL-terminated)
 * data:  payload (NUL-terminated)
 */
typedef void (*ha_mqtt_msg_cb_t)(const char *topic, const char *data, void *user_data);

/**
 * Called when MQTT connection state changes.
 */
typedef void (*ha_mqtt_state_cb_t)(ha_mqtt_state_t state, void *user_data);

/**
 * Initialize and start the HA MQTT client.
 *
 * Subscribes to:
 *   {prefix}/switch/+/set  — switch commands from HA (HA -> ESP32 -> Tuya)
 *   {prefix}/socket/+/set  — socket overrides from HA (rare, mostly informational)
 *   {prefix}/cmd           — control commands (e.g. "reset", "status")
 *
 * Publishes:
 *   {prefix}/switch/{n}/state  — current switch state (for HA feedback)
 *   {prefix}/socket/{n}/state  — socket trigger received from Tuya
 *   {prefix}/status            — JSON status blob
 *
 * @param cfg       App config
 * @param msg_cb    Callback for incoming messages
 * @param state_cb  Callback for connection state changes
 * @param user_data Passed to both callbacks
 */
esp_err_t ha_mqtt_start(const app_config_t *cfg,
                        ha_mqtt_msg_cb_t    msg_cb,
                        ha_mqtt_state_cb_t  state_cb,
                        void               *user_data);

/**
 * Publish a boolean state to a specific topic suffix.
 * Full topic = {prefix}/{suffix}
 * value is sent as "ON" or "OFF" (HA convention).
 * Thread-safe, non-blocking (queued internally by ESP-MQTT).
 */
esp_err_t ha_mqtt_publish_bool(const char *suffix, bool value);

/**
 * Publish a raw string payload.
 */
esp_err_t ha_mqtt_publish(const char *suffix, const char *payload, int qos, bool retain);

/**
 * Publish the switch state for channel n (1-based).
 */
esp_err_t ha_mqtt_publish_switch_state(uint8_t channel, bool value);

/**
 * Publish the socket trigger state for channel n (1-based).
 */
esp_err_t ha_mqtt_publish_socket_state(uint8_t channel, bool value);

/**
 * Publish a JSON status message to {prefix}/status.
 */
esp_err_t ha_mqtt_publish_status(const char *json);

/**
 * Returns current MQTT connection state.
 */
ha_mqtt_state_t ha_mqtt_get_state(void);

/**
 * Stop the MQTT client cleanly.
 */
void ha_mqtt_stop(void);
