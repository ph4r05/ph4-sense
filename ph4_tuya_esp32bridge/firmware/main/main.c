/**
 * ph4_tuya_esp32bridge — main entry point
 *
 * Boot sequence:
 *   1. Initialize NVS and load app config
 *   2. Start WiFi (STA or AP-provisioning mode)
 *   3. Wait for IP address
 *   4. Initialize DP bridge layer
 *   5. Start HA MQTT client (local broker)
 *   6. Start Tuya cloud client (Tuya cloud)
 *   7. Both run in background; main task idles
 *
 * Factory reset:
 *   - Send "reset" to {prefix}/cmd via MQTT
 *   - OR: hold GPIO9 (BOOT button) for 5 seconds on boot
 */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_err.h"
#include "esp_system.h"
#include "nvs_flash.h"
#include "driver/gpio.h"
#include "esp_timer.h"

#include "config.h"
#include "wifi_manager.h"
#include "tuya_cloud.h"
#include "ha_mqtt.h"
#include "dp_bridge.h"

static const char *TAG = "main";

/* GPIO9 = BOOT button on most ESP32-C6 dev boards */
#define FACTORY_RESET_GPIO      GPIO_NUM_9
#define FACTORY_RESET_HOLD_MS   5000

/* ------------------------------------------------------------------ */
/* Factory reset via hardware button                                    */
/* ------------------------------------------------------------------ */
static void check_factory_reset_button(void)
{
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << FACTORY_RESET_GPIO),
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_config(&io_conf);

    if (gpio_get_level(FACTORY_RESET_GPIO) != 0) return; /* not pressed */

    ESP_LOGW(TAG, "BOOT button held at startup — hold for %d ms for factory reset",
             FACTORY_RESET_HOLD_MS);

    int held_ms = 0;
    while (gpio_get_level(FACTORY_RESET_GPIO) == 0 && held_ms < FACTORY_RESET_HOLD_MS) {
        vTaskDelay(pdMS_TO_TICKS(100));
        held_ms += 100;
    }

    if (held_ms >= FACTORY_RESET_HOLD_MS) {
        ESP_LOGW(TAG, "Factory reset triggered by button!");
        config_erase();
        tuya_cloud_factory_reset();  /* also calls esp_restart() */
    }
}

/* ------------------------------------------------------------------ */
/* WiFi state callback                                                  */
/* ------------------------------------------------------------------ */
static void on_wifi_state(wifi_state_t state, void *arg)
{
    switch (state) {
    case WIFI_STATE_CONNECTING:
        ESP_LOGI(TAG, "WiFi: connecting...");
        break;
    case WIFI_STATE_CONNECTED:
        ESP_LOGI(TAG, "WiFi: connected");
        break;
    case WIFI_STATE_DISCONNECTED:
        ESP_LOGW(TAG, "WiFi: disconnected");
        break;
    case WIFI_STATE_AP_MODE_STARTED:
        ESP_LOGW(TAG, "WiFi: AP provisioning mode active");
        ESP_LOGW(TAG, "Connect to the AP and POST JSON to http://192.168.4.1/config");
        break;
    case WIFI_STATE_AP_MODE_TIMEOUT:
        ESP_LOGW(TAG, "WiFi: AP mode timed out, rebooting");
        break;
    }
}

/* ------------------------------------------------------------------ */
/* Tuya state callback (wraps to dp_bridge)                             */
/* ------------------------------------------------------------------ */
static void on_tuya_state(tuya_state_t state, void *arg)
{
    dp_bridge_on_tuya_state((int)state, arg);
}

/* ------------------------------------------------------------------ */
/* MQTT state callback (wraps to dp_bridge)                             */
/* ------------------------------------------------------------------ */
static void on_mqtt_state(ha_mqtt_state_t state, void *arg)
{
    dp_bridge_on_mqtt_state((int)state, arg);
}

/* ------------------------------------------------------------------ */
/* app_main                                                             */
/* ------------------------------------------------------------------ */
void app_main(void)
{
    ESP_LOGI(TAG, "ph4_tuya_esp32bridge starting");

    /* -------------------------------------------------------------- */
    /* 1. NVS                                                          */
    /* -------------------------------------------------------------- */
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS partition truncated, erasing...");
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    /* -------------------------------------------------------------- */
    /* 2. Load config                                                  */
    /* -------------------------------------------------------------- */
    static app_config_t cfg;
    ESP_ERROR_CHECK(config_load(&cfg));

    ESP_LOGI(TAG, "Config: wifi=%s  mqtt=%s:%d  switch=%d  socket=%d",
             cfg.wifi_ssid, cfg.mqtt_host, cfg.mqtt_port,
             cfg.switch_count, cfg.socket_count);

    /* -------------------------------------------------------------- */
    /* 3. Check factory reset button                                   */
    /* -------------------------------------------------------------- */
    check_factory_reset_button();

    /* -------------------------------------------------------------- */
    /* 4. Initialize bridge layer (before MQTT and Tuya start)         */
    /* -------------------------------------------------------------- */
    ESP_ERROR_CHECK(dp_bridge_init(&cfg));

    /* -------------------------------------------------------------- */
    /* 5. Start WiFi                                                   */
    /* -------------------------------------------------------------- */
    ESP_ERROR_CHECK(wifi_manager_start(&cfg, on_wifi_state, NULL));

    /* Block until connected (AP mode timeout will reboot if needed) */
    err = wifi_manager_wait_connected();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "WiFi failed — should not reach here (AP mode reboots)");
        esp_restart();
    }

    ESP_LOGI(TAG, "WiFi connected — starting cloud clients");

    /* -------------------------------------------------------------- */
    /* 6. Start HA MQTT client                                         */
    /* -------------------------------------------------------------- */
    err = ha_mqtt_start(&cfg,
                        dp_bridge_on_mqtt_msg,
                        on_mqtt_state,
                        NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HA MQTT start failed: %s", esp_err_to_name(err));
        /* Non-fatal: Tuya can still work, but HA integration won't */
    }

    /* -------------------------------------------------------------- */
    /* 7. Start Tuya cloud client                                      */
    /* -------------------------------------------------------------- */
    err = tuya_cloud_init(&cfg,
                          dp_bridge_on_tuya_dp,
                          on_tuya_state,
                          NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Tuya cloud init failed: %s", esp_err_to_name(err));
        ESP_LOGE(TAG, "Check PID/UUID/AuthKey in config or Kconfig");
        /* Keep running so provisioning HTTP server still works */
    } else {
        err = tuya_cloud_start();
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Tuya cloud start failed: %s", esp_err_to_name(err));
        }
    }

    /* -------------------------------------------------------------- */
    /* 8. Main task: idle (all work done in background tasks)          */
    /* -------------------------------------------------------------- */
    ESP_LOGI(TAG, "All services started. Running.");

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(10000));

        /* Periodic health log */
        ESP_LOGI(TAG, "heartbeat | wifi=%s tuya=%d mqtt=%d",
                 wifi_manager_is_connected() ? "OK" : "DOWN",
                 (int)tuya_cloud_get_state(),
                 (int)ha_mqtt_get_state());
    }
}
