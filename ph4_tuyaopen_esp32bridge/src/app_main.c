/**
 * ph4_tuyaopen_esp32bridge — TuyaOpen application entry point
 *
 * Based on tuyaopen/apps/tuya_cloud/switch_demo, adapted for
 * the 16-switch + 16-relay bridge with HA MQTT integration.
 *
 * Boot flow:
 *   1. TuyaOpen SDK init (KV, timers, work queues, CLI, authorization)
 *   2. tuya_iot_init() with product key + license
 *   3. Network manager init (WiFi AP/BLE pairing on first boot)
 *   4. tuya_iot_start() — connects to Tuya cloud
 *   5. Once MQTT connected → start HA MQTT client
 *   6. Main loop: tuya_iot_yield()
 *
 * Pairing: on first boot, SmartLife app discovers device via AP/BLE.
 * Factory reset: reboot 3x within 5 seconds (reset_netcfg logic).
 */

#include <assert.h>
#include <string.h>
#include <stdlib.h>
#include "cJSON.h"
#include "netmgr.h"
#include "tal_api.h"
#include "tkl_output.h"
#include "tuya_config.h"
#include "tuya_iot.h"
#include "tuya_iot_dp.h"
#include "tuya_authorize.h"
#include "tal_cli.h"

#if defined(ENABLE_WIFI) && (ENABLE_WIFI == 1)
#include "netconn_wifi.h"
#endif
#if defined(ENABLE_LIBLWIP) && (ENABLE_LIBLWIP == 1)
#include "lwip_init.h"
#endif

#include "config.h"
#include "tuya_cloud.h"
#include "dp_bridge.h"

/* HA MQTT: if building with ESP-IDF mqtt component available */
#if __has_include("ha_mqtt.h")
#include "ha_mqtt.h"
#define HA_MQTT_ENABLED 1
#else
#define HA_MQTT_ENABLED 0
#endif

#ifndef PROJECT_VERSION
#define PROJECT_VERSION "1.0.0"
#endif

/* ------------------------------------------------------------------ */
/* Globals                                                              */
/* ------------------------------------------------------------------ */
static tuya_iot_client_t s_client;
static tuya_iot_license_t s_license;
static app_config_t s_cfg;
static bool s_ha_mqtt_started = false;

/* ------------------------------------------------------------------ */
/* Start HA MQTT (called once WiFi/cloud is up)                         */
/* ------------------------------------------------------------------ */
static void try_start_ha_mqtt(void)
{
#if HA_MQTT_ENABLED
    if (s_ha_mqtt_started) return;
    if (strlen(s_cfg.mqtt_host) == 0) {
        PR_WARN("HA MQTT host not configured — skipping");
        return;
    }

    PR_INFO("Starting HA MQTT client -> %s:%d", s_cfg.mqtt_host, s_cfg.mqtt_port);
    esp_err_t err = ha_mqtt_start(&s_cfg,
                                   dp_bridge_on_mqtt_msg,
                                   (ha_mqtt_state_cb_t)dp_bridge_on_mqtt_state,
                                   NULL);
    if (err == ESP_OK) {
        s_ha_mqtt_started = true;
    } else {
        PR_ERR("HA MQTT start failed: %d", err);
    }
#else
    PR_WARN("HA MQTT not available in this build (needs ESP-IDF mqtt component)");
#endif
}

/* ------------------------------------------------------------------ */
/* Network check callback                                               */
/* ------------------------------------------------------------------ */
static bool network_check_cb(void)
{
    netmgr_status_e status = NETMGR_LINK_DOWN;
    netmgr_conn_get(NETCONN_AUTO, NETCONN_CMD_STATUS, &status);
    return status != NETMGR_LINK_DOWN;
}

/* ------------------------------------------------------------------ */
/* TuyaOpen event handler                                               */
/* ------------------------------------------------------------------ */
static void event_handler(tuya_iot_client_t *client, tuya_event_msg_t *event)
{
    PR_DEBUG("Event: %d (%s)  free_heap=%d",
             event->id, EVENT_ID2STR(event->id),
             tal_system_get_free_heap_size());

    switch (event->id) {
    case TUYA_EVENT_BIND_START:
        PR_NOTICE("Device entering pairing mode — use SmartLife app to add");
        dp_bridge_on_tuya_state(TUYA_STATE_PAIRING, NULL);
        break;

    case TUYA_EVENT_ACTIVATE_SUCCESSED:
        PR_NOTICE("Device activated! Bound to SmartLife account.");
        dp_bridge_on_tuya_state(TUYA_STATE_ACTIVATING, NULL);
        break;

    case TUYA_EVENT_DIRECT_MQTT_CONNECTED:
        PR_INFO("Direct MQTT connected (pre-activation)");
        break;

    case TUYA_EVENT_MQTT_CONNECTED:
        PR_NOTICE("Tuya cloud MQTT connected");
        dp_bridge_on_tuya_state(TUYA_STATE_CONNECTED, NULL);
        try_start_ha_mqtt();
        tuya_cloud_report_all();
        break;

    case TUYA_EVENT_MQTT_DISCONNECT:
        PR_WARN("Tuya cloud MQTT disconnected");
        dp_bridge_on_tuya_state(TUYA_STATE_DISCONNECTED, NULL);
        break;

    case TUYA_EVENT_TIMESTAMP_SYNC:
        PR_INFO("Timestamp sync: %d", event->value.asInteger);
        tal_time_set_posix(event->value.asInteger, 1);
        break;

    case TUYA_EVENT_DP_RECEIVE_OBJ: {
        dp_obj_recv_t *dpobj = event->value.dpobj;
        if (!dpobj) break;

        PR_DEBUG("DP OBJ recv: cnt=%u cmd=%d", dpobj->dpscnt, dpobj->cmd_tp);

        for (uint32_t i = 0; i < dpobj->dpscnt; i++) {
            dp_obj_t *dp = &dpobj->dps[i];

            if (dp->type != PROP_BOOL) {
                PR_WARN("DP %d: expected BOOL, got type %d", dp->id, dp->type);
                continue;
            }

            bool value = dp->value.dp_bool;
            PR_INFO("DP %d = %s (from cloud)", dp->id, value ? "true" : "false");
            dp_bridge_on_tuya_dp(dp->id, value, NULL);
        }

        /* ACK */
        tuya_iot_dp_obj_report(client, dpobj->devid, dpobj->dps, dpobj->dpscnt, 0);
        break;
    }

    case TUYA_EVENT_DP_RECEIVE_RAW:
        PR_WARN("Raw DP received (not handled)");
        break;

    case TUYA_EVENT_UPGRADE_NOTIFY:
        PR_INFO("OTA upgrade notification (not implemented)");
        break;

    case TUYA_EVENT_RESET:
        PR_WARN("Reset event: %d", event->value.asInteger);
        dp_bridge_on_tuya_state(TUYA_STATE_RESET, NULL);
        break;

    default:
        break;
    }
}

/* ------------------------------------------------------------------ */
/* CLI commands                                                         */
/* ------------------------------------------------------------------ */
static void cli_switch_test(int argc, char *argv[])
{
    if (argc < 3) {
        PR_INFO("usage: switch <dp_id> <on/off>");
        return;
    }
    int dp_id = atoi(argv[1]);
    bool value = (strcmp(argv[2], "on") == 0);
    tuya_cloud_report_bool((uint8_t)dp_id, value);
}

static void cli_reset(int argc, char *argv[])
{
    tuya_cloud_factory_reset();
}

static void cli_mem(int argc, char *argv[])
{
    PR_NOTICE("Free heap: %d", tal_system_get_free_heap_size());
}

static cli_cmd_t s_cli_cmds[] = {
    {.name = "switch", .func = cli_switch_test, .help = "switch <dp_id> <on/off>"},
    {.name = "reset",  .func = cli_reset,       .help = "factory reset"},
    {.name = "mem",    .func = cli_mem,          .help = "show free heap"},
};

void tuya_app_cli_init(void)
{
    tal_cli_cmd_register(s_cli_cmds, sizeof(s_cli_cmds) / sizeof(s_cli_cmds[0]));
}

/* ------------------------------------------------------------------ */
/* Reset-on-reboot counter (3x reboot = factory reset)                  */
/* ------------------------------------------------------------------ */
#define RESET_NETCNT_NAME "rst_cnt"
#define RESET_NETCNT_MAX  3

static void reset_timer_cb(TIMER_ID timer_id, void *arg)
{
    tal_kv_set(RESET_NETCNT_NAME, (uint8_t[]){0}, 1);
    PR_DEBUG("Reset counter cleared");
}

static void reset_netconfig_start(void)
{
    uint8_t *buf = NULL;
    size_t len = 0;
    uint8_t cnt = 0;

    if (tal_kv_get(RESET_NETCNT_NAME, &buf, &len) == OPRT_OK && buf) {
        cnt = buf[0];
        tal_kv_free(buf);
    }
    cnt++;
    tal_kv_set(RESET_NETCNT_NAME, &cnt, 1);

    TIMER_ID timer;
    tal_sw_timer_create(reset_timer_cb, NULL, &timer);
    tal_sw_timer_start(timer, 5000, TAL_TIMER_ONCE);
}

static void reset_netconfig_check(void)
{
    uint8_t *buf = NULL;
    size_t len = 0;
    uint8_t cnt = 0;

    if (tal_kv_get(RESET_NETCNT_NAME, &buf, &len) == OPRT_OK && buf) {
        cnt = buf[0];
        tal_kv_free(buf);
    }

    if (cnt >= RESET_NETCNT_MAX) {
        PR_WARN("Reset counter reached %d — factory reset!", cnt);
        tal_kv_set(RESET_NETCNT_NAME, (uint8_t[]){0}, 1);
        tuya_iot_reset(&s_client);
    }
}

/* ------------------------------------------------------------------ */
/* user_main — application logic                                        */
/* ------------------------------------------------------------------ */
static void user_main(void)
{
    int rt = OPRT_OK;

    /* TuyaOpen runtime init */
    cJSON_InitHooks(&(cJSON_Hooks){.malloc_fn = tal_malloc, .free_fn = tal_free});
    tal_log_init(TAL_LOG_LEVEL_DEBUG, 1024, (TAL_LOG_OUTPUT_CB)tkl_log_output);

    PR_NOTICE("=== ph4_tuyaopen_esp32bridge ===");
    PR_NOTICE("Version:   %s", PROJECT_VERSION);
    PR_NOTICE("TuyaOpen:  %s", OPEN_VERSION);
    PR_NOTICE("Compiled:  %s %s", __DATE__, __TIME__);

    tal_kv_init(&(tal_kv_cfg_t){
        .seed = "vmlkasdh93dlvlcy",
        .key  = "dflfuap134ddlduq",
    });
    tal_sw_timer_init();
    tal_workq_init();

    tal_cli_init();
    tuya_authorize_init();
    tuya_app_cli_init();

    /* Load app config (HA MQTT settings) */
    config_load(&s_cfg);
    PR_INFO("Config: mqtt=%s:%d sw=%d sk=%d",
            s_cfg.mqtt_host, s_cfg.mqtt_port,
            s_cfg.switch_count, s_cfg.socket_count);

    /* Init bridge layer */
    dp_bridge_init(&s_cfg);

    /* Init tuya_cloud wrapper */
    tuya_cloud_init(&s_cfg, dp_bridge_on_tuya_dp, NULL, NULL);

    /* Reset counter */
    reset_netconfig_start();

    /* Read license from chip or fall back to tuya_config.h */
    if (OPRT_OK != tuya_authorize_read(&s_license)) {
        s_license.uuid    = TUYA_OPENSDK_UUID;
        s_license.authkey = TUYA_OPENSDK_AUTHKEY;
        PR_WARN("Using hardcoded UUID/AuthKey from tuya_config.h");
    }

    /* Initialize Tuya IoT client */
    rt = tuya_iot_init(&s_client, &(const tuya_iot_config_t){
        .software_ver  = PROJECT_VERSION,
        .productkey    = TUYA_PRODUCT_ID,
        .uuid          = s_license.uuid,
        .authkey       = s_license.authkey,
        .event_handler = event_handler,
        .network_check = network_check_cb,
    });
    assert(rt == OPRT_OK);

#if defined(ENABLE_LIBLWIP) && (ENABLE_LIBLWIP == 1)
    TUYA_LwIP_Init();
#endif

    /* Network init */
    netmgr_type_e type = 0;
#if defined(ENABLE_WIFI) && (ENABLE_WIFI == 1)
    type |= NETCONN_WIFI;
#endif
    netmgr_init(type);

#if defined(ENABLE_WIFI) && (ENABLE_WIFI == 1)
    netmgr_conn_set(NETCONN_WIFI, NETCONN_CMD_NETCFG,
                    &(netcfg_args_t){.type = NETCFG_TUYA_BLE | NETCFG_TUYA_WIFI_AP});
#endif

    PR_NOTICE("Starting Tuya IoT...");
    tuya_iot_start(&s_client);

    reset_netconfig_check();

    for (;;) {
        tuya_iot_yield(&s_client);
    }
}

/* ------------------------------------------------------------------ */
/* tuya_app_main — TuyaOpen entry point                                 */
/* ------------------------------------------------------------------ */
#if OPERATING_SYSTEM == SYSTEM_LINUX
void main(int argc, char *argv[])
{
    user_main();
}
#else

static THREAD_HANDLE s_app_thread = NULL;

static void app_thread(void *arg)
{
    user_main();
    tal_thread_delete(s_app_thread);
    s_app_thread = NULL;
}

void tuya_app_main(void)
{
    THREAD_CFG_T cfg = {
        .stackDepth = 1024 * 6,
        .priority   = THREAD_PRIO_1,
        .thrdname   = "ph4_bridge",
    };
    tal_thread_create_and_start(&s_app_thread, NULL, NULL, app_thread, NULL, &cfg);
}
#endif
