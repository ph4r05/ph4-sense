/*
 * ESP32 NVS-backed storage wrapper for tuya-iot-core-sdk.
 *
 * Replaces platform/posix/storage_wrapper.c which uses fopen/fwrite and
 * requires a mounted filesystem. ESP32 uses NVS (Non-Volatile Storage)
 * instead. Credentials are stored in the "tuya_kv" NVS namespace.
 *
 * NVS key names are limited to 15 characters. Tuya SDK internal keys
 * (e.g. "devid", "seckey", "localkey") are all within this limit.
 */

#include <string.h>
#include <stdint.h>
#include <stdlib.h>

#include "nvs_flash.h"
#include "nvs.h"

#include "storage_interface.h"
#include "tuya_error_code.h"
#include "log.h"

#define TUYA_KV_NAMESPACE   "tuya_kv"
#define NVS_KEY_MAX         15   /* NVS_KEY_NAME_MAX_SIZE - 1 */

/* Truncate key to NVS maximum length. */
static void nvs_key(const char *key, char *out)
{
    strncpy(out, key, NVS_KEY_MAX);
    out[NVS_KEY_MAX] = '\0';
}

int local_storage_set(const char *key, const uint8_t *buffer, size_t length)
{
    if (!key || !buffer) {
        return OPRT_INVALID_PARM;
    }

    char k[NVS_KEY_MAX + 1];
    nvs_key(key, k);
    log_debug("storage_set key:%s len:%d", k, (int)length);

    nvs_handle_t h;
    if (nvs_open(TUYA_KV_NAMESPACE, NVS_READWRITE, &h) != ESP_OK) {
        log_error("nvs_open failed");
        return OPRT_COM_ERROR;
    }
    esp_err_t err = nvs_set_blob(h, k, buffer, length);
    nvs_commit(h);
    nvs_close(h);
    return (err == ESP_OK) ? OPRT_OK : OPRT_COM_ERROR;
}

int local_storage_get(const char *key, uint8_t *buffer, size_t *length)
{
    if (!key || !buffer || !length) {
        return OPRT_INVALID_PARM;
    }

    char k[NVS_KEY_MAX + 1];
    nvs_key(key, k);
    log_debug("storage_get key:%s len:%d", k, (int)*length);

    nvs_handle_t h;
    if (nvs_open(TUYA_KV_NAMESPACE, NVS_READONLY, &h) != ESP_OK) {
        log_warn("nvs_open failed (key not found yet?)");
        return OPRT_COM_ERROR;
    }
    esp_err_t err = nvs_get_blob(h, k, buffer, length);
    nvs_close(h);
    return (err == ESP_OK) ? OPRT_OK : OPRT_COM_ERROR;
}

int local_storage_del(const char *key)
{
    if (!key) {
        return OPRT_INVALID_PARM;
    }

    char k[NVS_KEY_MAX + 1];
    nvs_key(key, k);
    log_debug("storage_del key:%s", k);

    nvs_handle_t h;
    if (nvs_open(TUYA_KV_NAMESPACE, NVS_READWRITE, &h) != ESP_OK) {
        return OPRT_COM_ERROR;
    }
    esp_err_t err = nvs_erase_key(h, k);
    nvs_commit(h);
    nvs_close(h);
    return (err == ESP_OK) ? OPRT_OK : OPRT_COM_ERROR;
}
