#pragma once
#include <stdbool.h>
#include "config.h"

/**
 * WiFi connection states reported to callers via the registered callback.
 */
typedef enum {
    WIFI_STATE_CONNECTING,
    WIFI_STATE_CONNECTED,
    WIFI_STATE_DISCONNECTED,
    WIFI_STATE_AP_MODE_STARTED,    /* provisioning AP is up */
    WIFI_STATE_AP_MODE_TIMEOUT,    /* AP mode timed out, rebooting */
} wifi_state_t;

typedef void (*wifi_state_cb_t)(wifi_state_t state, void *user_data);

/**
 * Initialize WiFi subsystem and start connection.
 *
 * Algorithm:
 *   1. If saved SSID exists, try STA mode (up to 3 attempts).
 *   2. If all attempts fail, start AP mode for provisioning.
 *   3. In AP mode, listen for config via HTTP POST /config (JSON).
 *   4. On successful provisioning, save config + connect.
 *
 * @param cfg       App config (read: ssid/pass; write: updated on provision)
 * @param cb        Optional state change callback
 * @param user_data Passed verbatim to cb
 */
esp_err_t wifi_manager_start(app_config_t *cfg, wifi_state_cb_t cb, void *user_data);

/**
 * Block until WiFi is connected (or failed permanently).
 * Returns ESP_OK when IP is assigned, ESP_FAIL on permanent failure.
 */
esp_err_t wifi_manager_wait_connected(void);

/**
 * Returns true if currently connected and has an IP address.
 */
bool wifi_manager_is_connected(void);

/**
 * Trigger a WiFi reconnect (e.g., after config change).
 */
void wifi_manager_reconnect(void);
