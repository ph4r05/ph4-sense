#include <string.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_http_server.h"
#include "sdkconfig.h"
#include "config.h"
#include "wifi_manager.h"

static const char *TAG = "wifi_mgr";

#define WIFI_CONNECTED_BIT   BIT0
#define WIFI_FAIL_BIT        BIT1
#define WIFI_MAX_RETRY       3
#define AP_SSID_PREFIX       "ph4-bridge-"

static EventGroupHandle_t s_wifi_eg;
static wifi_state_cb_t    s_cb       = NULL;
static void              *s_cb_data  = NULL;
static app_config_t      *s_cfg      = NULL;
static int                s_retry    = 0;
static bool               s_ap_mode  = false;
static httpd_handle_t     s_httpd    = NULL;

/* ------------------------------------------------------------------ */
/* Forward declarations                                                 */
/* ------------------------------------------------------------------ */
static void start_sta_mode(void);
static void start_ap_mode(void);

/* ------------------------------------------------------------------ */
/* Callback helpers                                                     */
/* ------------------------------------------------------------------ */
static void notify(wifi_state_t state)
{
    if (s_cb) s_cb(state, s_cb_data);
}

/* ------------------------------------------------------------------ */
/* HTTP provisioning server (AP mode)                                   */
/* ------------------------------------------------------------------ */

/* POST /config — accepts JSON config blob */
static esp_err_t http_config_post(httpd_req_t *req)
{
    char buf[1024];
    int received = 0;
    int remaining = req->content_len;

    if (remaining >= (int)sizeof(buf)) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Payload too large");
        return ESP_FAIL;
    }

    while (remaining > 0) {
        int ret = httpd_req_recv(req, buf + received, remaining);
        if (ret <= 0) {
            if (ret == HTTPD_SOCK_ERR_TIMEOUT) continue;
            return ESP_FAIL;
        }
        received  += ret;
        remaining -= ret;
    }
    buf[received] = '\0';

    esp_err_t err = config_apply_json(s_cfg, buf);
    if (err != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid JSON");
        return ESP_FAIL;
    }

    config_save(s_cfg);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_sendstr(req, "{\"status\":\"ok\",\"message\":\"Config saved. Rebooting.\"}");

    /* Reboot after a short delay to let the HTTP response go out */
    vTaskDelay(pdMS_TO_TICKS(500));
    esp_restart();
    return ESP_OK;
}

/* GET /config — returns current config as JSON */
static esp_err_t http_config_get(httpd_req_t *req)
{
    char *json = config_to_json(s_cfg);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_sendstr(req, json ? json : "{}");
    free(json);
    return ESP_OK;
}

/* GET /status */
static esp_err_t http_status_get(httpd_req_t *req)
{
    httpd_resp_set_type(req, "application/json");
    httpd_resp_sendstr(req, "{\"mode\":\"ap_provisioning\",\"ready\":true}");
    return ESP_OK;
}

static void start_provisioning_server(void)
{
    if (s_httpd) return;

    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;

    if (httpd_start(&s_httpd, &config) != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start HTTP provisioning server");
        return;
    }

    static const httpd_uri_t uri_cfg_post = {
        .uri = "/config", .method = HTTP_POST, .handler = http_config_post
    };
    static const httpd_uri_t uri_cfg_get = {
        .uri = "/config", .method = HTTP_GET,  .handler = http_config_get
    };
    static const httpd_uri_t uri_status = {
        .uri = "/status", .method = HTTP_GET,  .handler = http_status_get
    };

    httpd_register_uri_handler(s_httpd, &uri_cfg_post);
    httpd_register_uri_handler(s_httpd, &uri_cfg_get);
    httpd_register_uri_handler(s_httpd, &uri_status);

    ESP_LOGI(TAG, "Provisioning HTTP server started on port 80");
}

static void stop_provisioning_server(void)
{
    if (s_httpd) {
        httpd_stop(s_httpd);
        s_httpd = NULL;
    }
}

/* ------------------------------------------------------------------ */
/* AP mode timeout task                                                 */
/* ------------------------------------------------------------------ */
static void ap_timeout_task(void *arg)
{
    int timeout_s = CONFIG_WIFI_AP_MODE_TIMEOUT_S;
    ESP_LOGW(TAG, "AP mode active, timeout in %d seconds", timeout_s);
    vTaskDelay(pdMS_TO_TICKS((uint32_t)timeout_s * 1000));
    ESP_LOGW(TAG, "AP mode timed out — rebooting");
    notify(WIFI_STATE_AP_MODE_TIMEOUT);
    esp_restart();
}

/* ------------------------------------------------------------------ */
/* WiFi event handler                                                   */
/* ------------------------------------------------------------------ */
static void wifi_event_handler(void *arg, esp_event_base_t base,
                               int32_t event_id, void *event_data)
{
    if (base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
        notify(WIFI_STATE_CONNECTING);
        return;
    }

    if (base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        if (!s_ap_mode) {
            if (s_retry < WIFI_MAX_RETRY) {
                s_retry++;
                ESP_LOGW(TAG, "WiFi disconnected, retrying (%d/%d)", s_retry, WIFI_MAX_RETRY);
                esp_wifi_connect();
                notify(WIFI_STATE_CONNECTING);
            } else {
                ESP_LOGE(TAG, "WiFi failed after %d attempts, starting AP mode", WIFI_MAX_RETRY);
                xEventGroupSetBits(s_wifi_eg, WIFI_FAIL_BIT);
                start_ap_mode();
            }
        }
        notify(WIFI_STATE_DISCONNECTED);
        return;
    }

    if (base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "Got IP: " IPSTR, IP2STR(&event->ip_info.ip));
        s_retry = 0;
        xEventGroupSetBits(s_wifi_eg, WIFI_CONNECTED_BIT);
        notify(WIFI_STATE_CONNECTED);
        return;
    }

    if (base == WIFI_EVENT && event_id == WIFI_EVENT_STA_CONNECTED) {
        ESP_LOGI(TAG, "WiFi associated");
        return;
    }
}

/* ------------------------------------------------------------------ */
/* STA mode                                                             */
/* ------------------------------------------------------------------ */
static void start_sta_mode(void)
{
    ESP_LOGI(TAG, "Starting STA mode, SSID: %s", s_cfg->wifi_ssid);

    wifi_config_t wifi_cfg = {0};
    strlcpy((char *)wifi_cfg.sta.ssid,     s_cfg->wifi_ssid, sizeof(wifi_cfg.sta.ssid));
    strlcpy((char *)wifi_cfg.sta.password, s_cfg->wifi_pass, sizeof(wifi_cfg.sta.password));
    wifi_cfg.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

    esp_wifi_set_mode(WIFI_MODE_STA);
    esp_wifi_set_config(WIFI_IF_STA, &wifi_cfg);
    esp_wifi_start();
}

/* ------------------------------------------------------------------ */
/* AP mode                                                              */
/* ------------------------------------------------------------------ */
static void start_ap_mode(void)
{
    s_ap_mode = true;

    /* Build SSID from chip MAC suffix */
    uint8_t mac[6];
    esp_wifi_get_mac(WIFI_IF_AP, mac);
    char ap_ssid[32];
    snprintf(ap_ssid, sizeof(ap_ssid), "%s%02X%02X%02X",
             AP_SSID_PREFIX, mac[3], mac[4], mac[5]);

    ESP_LOGI(TAG, "Starting AP mode: SSID=%s  IP=192.168.4.1", ap_ssid);

    wifi_config_t ap_cfg = {0};
    strlcpy((char *)ap_cfg.ap.ssid, ap_ssid, sizeof(ap_cfg.ap.ssid));
    ap_cfg.ap.ssid_len      = strlen(ap_ssid);
    ap_cfg.ap.channel       = 6;
    ap_cfg.ap.authmode      = WIFI_AUTH_OPEN;  /* open — easier for provisioning */
    ap_cfg.ap.max_connection = 2;

    esp_wifi_set_mode(WIFI_MODE_AP);
    esp_wifi_set_config(WIFI_IF_AP, &ap_cfg);
    esp_wifi_start();

    notify(WIFI_STATE_AP_MODE_STARTED);
    start_provisioning_server();

    xTaskCreate(ap_timeout_task, "ap_timeout", 2048, NULL, 5, NULL);
}

/* ------------------------------------------------------------------ */
/* Public API                                                           */
/* ------------------------------------------------------------------ */
esp_err_t wifi_manager_start(app_config_t *cfg, wifi_state_cb_t cb, void *user_data)
{
    s_cfg     = cfg;
    s_cb      = cb;
    s_cb_data = user_data;
    s_retry   = 0;
    s_ap_mode = false;

    s_wifi_eg = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    esp_netif_create_default_wifi_sta();
    esp_netif_create_default_wifi_ap();

    wifi_init_config_t init_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event_handler, NULL, NULL));

    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));

    /* If no SSID configured, jump straight to AP mode */
    if (strlen(cfg->wifi_ssid) == 0) {
        ESP_LOGW(TAG, "No SSID configured, starting provisioning AP");
        start_ap_mode();
    } else {
        start_sta_mode();
    }

    return ESP_OK;
}

esp_err_t wifi_manager_wait_connected(void)
{
    EventBits_t bits = xEventGroupWaitBits(
        s_wifi_eg,
        WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
        pdFALSE, pdFALSE,
        portMAX_DELAY);

    if (bits & WIFI_CONNECTED_BIT) return ESP_OK;
    return ESP_FAIL;
}

bool wifi_manager_is_connected(void)
{
    if (!s_wifi_eg) return false;
    return (xEventGroupGetBits(s_wifi_eg) & WIFI_CONNECTED_BIT) != 0;
}

void wifi_manager_reconnect(void)
{
    if (s_ap_mode) return;
    s_retry = 0;
    esp_wifi_disconnect();
    esp_wifi_connect();
}
