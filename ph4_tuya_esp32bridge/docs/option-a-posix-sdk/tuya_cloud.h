#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "config.h"

/**
 * Tuya cloud connection states.
 */
typedef enum {
    TUYA_STATE_INIT,
    TUYA_STATE_ACTIVATING,      /* First pairing: sending token to Tuya cloud */
    TUYA_STATE_CONNECTED,       /* Authenticated and connected */
    TUYA_STATE_DISCONNECTED,
    TUYA_STATE_RESET,           /* Factory-reset requested via cloud */
} tuya_state_t;

/**
 * Called when Tuya cloud changes a DP (socket direction: cloud -> device).
 * dp_id: 1-based DP ID, value: the new boolean value.
 */
typedef void (*tuya_dp_recv_cb_t)(uint8_t dp_id, bool value, void *user_data);

/**
 * Called when connection state changes.
 */
typedef void (*tuya_state_cb_t)(tuya_state_t state, void *user_data);

/**
 * Initialize the Tuya IoT SDK and register DPs.
 *
 * Must be called after WiFi is connected.
 * Registers:
 *   - Switch DPs: 1..cfg->switch_count (boolean, R/W, cloud can read/write)
 *   - Socket DPs: 101..100+cfg->socket_count (boolean, R/W)
 *
 * @param cfg       App config with Tuya credentials
 * @param dp_cb     Called when cloud sets a DP value
 * @param state_cb  Called on connection state changes
 * @param user_data Passed to both callbacks
 */
esp_err_t tuya_cloud_init(const app_config_t *cfg,
                          tuya_dp_recv_cb_t dp_cb,
                          tuya_state_cb_t   state_cb,
                          void             *user_data);

/**
 * Start the Tuya cloud connection (non-blocking, runs in background task).
 * Handles device activation (first-time pairing) and reconnection automatically.
 */
esp_err_t tuya_cloud_start(void);

/**
 * Report a boolean DP value to Tuya cloud (switch direction: device -> cloud).
 * dp_id: 1-based DP ID.
 * Thread-safe, may be called from any task.
 */
esp_err_t tuya_cloud_report_bool(uint8_t dp_id, bool value);

/**
 * Report multiple DPs atomically.
 * dp_ids[] and values[] are parallel arrays of length count.
 */
esp_err_t tuya_cloud_report_multi(const uint8_t *dp_ids,
                                  const bool    *values,
                                  uint8_t        count);

/**
 * Report all current DP states (called after reconnect to sync Tuya).
 */
esp_err_t tuya_cloud_report_all(void);

/**
 * Returns current connection state.
 */
tuya_state_t tuya_cloud_get_state(void);

/**
 * Trigger factory reset (clears Tuya activation data from NVS).
 * Device will re-enter pairing mode on next boot.
 */
void tuya_cloud_factory_reset(void);

/**
 * Stop the Tuya cloud task (for clean shutdown).
 */
void tuya_cloud_stop(void);
