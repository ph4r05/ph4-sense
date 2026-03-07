/*
 * ESP32 native TLS network wrapper for tuya-iot-core-sdk.
 *
 * Replaces platform/posix/network_wrapper.c which directly uses mbedtls 2.x
 * APIs (mbedtls_ssl_conf_rng, ssl.state struct member access, etc.) that are
 * incompatible with ESP-IDF 5.x / 6.x (mbedtls 3.x).
 *
 * This implementation uses esp_tls — the stable ESP-IDF TLS abstraction that
 * works regardless of the underlying mbedtls version. No mbedtls headers are
 * included directly.
 *
 * Implements: network_interface.h
 *   network_tls_init / network_tls_connect / network_tls_read /
 *   network_tls_write / network_tls_disconnect / network_tls_destroy
 */

#include <string.h>
#include <stdlib.h>

#include "esp_tls.h"
#include "esp_log.h"

#include "network_interface.h"
#include "tuya_error_code.h"

static const char *TAG = "tuya_net";

/* Concrete definition of the opaque tls_context_t declared in network_interface.h */
struct tls_context {
    esp_tls_t *tls;
};

/* -------------------------------------------------------------------------
 * helpers
 * ---------------------------------------------------------------------- */

/* PEM blobs from the SDK may have cacert_len == 0 meaning null-terminated. */
static size_t pem_len(const uint8_t *buf, size_t declared_len)
{
    if (declared_len > 0) {
        return declared_len;
    }
    return buf ? strlen((const char *)buf) + 1 : 0;
}

/* -------------------------------------------------------------------------
 * interface implementation
 * ---------------------------------------------------------------------- */

int network_tls_init(NetworkContext_t *pNetwork, const TLSConnectParams *params)
{
    if (!pNetwork) {
        return OPRT_INVALID_PARM;
    }

    pNetwork->connect    = network_tls_connect;
    pNetwork->read       = network_tls_read;
    pNetwork->write      = network_tls_write;
    pNetwork->disconnect = network_tls_disconnect;
    pNetwork->destroy    = network_tls_destroy;
    pNetwork->tlsConnectParams = *params;

    tls_context_t *ctx = calloc(1, sizeof(tls_context_t));
    if (!ctx) {
        ESP_LOGE(TAG, "tls_ctx malloc failed");
        return OPRT_MALLOC_FAILED;
    }

    pNetwork->context = ctx;
    return OPRT_OK;
}

int network_tls_connect(NetworkContext_t *pNetwork, const TLSConnectParams *params)
{
    if (!pNetwork) {
        return OPRT_INVALID_PARM;
    }

    if (params) {
        pNetwork->tlsConnectParams = *params;
    }

    const TLSConnectParams *p = &pNetwork->tlsConnectParams;
    tls_context_t *ctx = pNetwork->context;

    /* Tear down any previous connection */
    if (ctx->tls) {
        esp_tls_conn_destroy(ctx->tls);
        ctx->tls = NULL;
    }

    esp_tls_cfg_t cfg = {
        .timeout_ms       = (int)p->timeout_ms,
        .skip_common_name = !p->cert_verify,
    };

    /* CA certificate for server verification */
    if (p->cacert) {
        cfg.cacert_buf   = p->cacert;
        cfg.cacert_bytes = pem_len(p->cacert, p->cacert_len);
    }

    /* Mutual TLS: client certificate + key */
    if (p->client_cert && p->client_key) {
        cfg.clientcert_buf   = p->client_cert;
        cfg.clientcert_bytes = pem_len(p->client_cert, p->client_cert_len);
        cfg.clientkey_buf    = p->client_key;
        cfg.clientkey_bytes  = pem_len(p->client_key, p->client_key_len);
    }

    ESP_LOGI(TAG, "Connecting TLS to %s:%d", p->host, p->port);

    ctx->tls = esp_tls_init();
    if (!ctx->tls) {
        ESP_LOGE(TAG, "esp_tls_init failed");
        return OPRT_MID_TLS_NET_SOCKET_ERROR;
    }

    int ret = esp_tls_conn_new_sync(p->host, strlen(p->host), p->port, &cfg, ctx->tls);
    if (ret != 1) {
        esp_tls_error_handle_t err_handle = NULL;
        if (esp_tls_get_error_handle(ctx->tls, &err_handle) == ESP_OK && err_handle) {
            int last_err = 0;
            esp_tls_get_and_clear_last_error(err_handle, &last_err, NULL);
            ESP_LOGE(TAG, "TLS connect failed, esp_err=0x%x", last_err);
        }
        esp_tls_conn_destroy(ctx->tls);
        ctx->tls = NULL;
        return OPRT_MID_TLS_NET_CONNECT_ERROR;
    }

    ESP_LOGI(TAG, "TLS connected to %s:%d", p->host, p->port);
    return OPRT_OK;
}

int network_tls_disconnect(NetworkContext_t *pNetwork)
{
    if (!pNetwork || !pNetwork->context) {
        return OPRT_OK;
    }

    tls_context_t *ctx = pNetwork->context;
    if (ctx->tls) {
        esp_tls_conn_destroy(ctx->tls);
        ctx->tls = NULL;
    }
    return OPRT_OK;
}

int network_tls_destroy(NetworkContext_t *pNetwork)
{
    if (!pNetwork || !pNetwork->context) {
        return OPRT_OK;
    }

    tls_context_t *ctx = pNetwork->context;
    if (ctx->tls) {
        esp_tls_conn_destroy(ctx->tls);
        ctx->tls = NULL;
    }
    free(ctx);
    pNetwork->context = NULL;
    return OPRT_OK;
}

int network_tls_write(NetworkContext_t *pNetwork, const unsigned char *pMsg, size_t len)
{
    tls_context_t *ctx = pNetwork->context;
    if (!ctx || !ctx->tls) {
        return OPRT_MID_TLS_NET_SOCKET_ERROR;
    }

    size_t written = 0;
    while (written < len) {
        int rv = esp_tls_conn_write(ctx->tls, pMsg + written, len - written);
        if (rv > 0) {
            written += (size_t)rv;
        } else if (rv == ESP_TLS_ERR_SSL_WANT_WRITE) {
            /* Would block — return what we have so far; caller retries */
            break;
        } else {
            ESP_LOGE(TAG, "esp_tls_conn_write error: %d", rv);
            return OPRT_MID_TLS_NET_SOCKET_ERROR;
        }
    }
    return (int)written;
}

int network_tls_read(NetworkContext_t *pNetwork, unsigned char *pMsg, size_t len)
{
    tls_context_t *ctx = pNetwork->context;
    if (!ctx || !ctx->tls) {
        return OPRT_MID_TLS_NET_SOCKET_ERROR;
    }

    int rv = esp_tls_conn_read(ctx->tls, pMsg, len);
    if (rv > 0) {
        return rv;
    } else if (rv == ESP_TLS_ERR_SSL_WANT_READ || rv == ESP_TLS_ERR_SSL_TIMEOUT) {
        /* No data yet / read timeout — return 0, caller retries */
        return 0;
    } else if (rv == 0) {
        /* Connection closed by peer */
        ESP_LOGW(TAG, "TLS connection closed by peer");
        return OPRT_MID_TLS_NET_SOCKET_ERROR;
    } else {
        ESP_LOGE(TAG, "esp_tls_conn_read error: %d", rv);
        return OPRT_MID_TLS_NET_SOCKET_ERROR;
    }
}
