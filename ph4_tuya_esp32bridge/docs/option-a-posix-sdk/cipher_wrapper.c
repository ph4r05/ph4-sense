/*
 * ESP32 cipher wrapper for tuya-iot-core-sdk — PSA Crypto backend.
 *
 * Replaces src/cipher_wrapper.c which uses the mbedtls cipher API
 * (mbedtls_cipher_context_t, mbedtls_cipher_auth_encrypt, etc.) that was
 * removed from the mbedtls 4.x public API (ESP-IDF 6.x). Those functions
 * have moved to the PSA Crypto API (psa_aead_encrypt / psa_aead_decrypt).
 *
 * The mbedtls MD API (mbedtls/md.h) is still public in mbedtls 4.x via the
 * tf-psa-crypto include path, so hash and HMAC functions are kept as-is.
 *
 * Implements:
 *   mbedtls_cipher_auth_encrypt_wrapper  — AES-GCM encrypt via PSA AEAD
 *   mbedtls_cipher_auth_decrypt_wrapper  — AES-GCM decrypt via PSA AEAD
 *   mbedtls_message_digest               — hash via mbedtls MD API
 *   mbedtls_message_digest_hmac          — HMAC via mbedtls MD API
 */

#include <string.h>
#include <stdlib.h>

#include "psa/crypto.h"
#include "mbedtls/md.h"
#include "esp_log.h"

#include "cipher_wrapper.h"
#include "tuya_error_code.h"

static const char *TAG = "tuya_cipher";

/* -------------------------------------------------------------------------
 * AEAD (AES-GCM) via PSA Crypto
 * ---------------------------------------------------------------------- */

/*
 * Map our internal cipher_type constant to a PSA key type.
 * Only AES is used by the Tuya SDK.
 */
static psa_key_type_t psa_key_type_from_cipher(mbedtls_cipher_type_t type)
{
    (void)type;
    return PSA_KEY_TYPE_AES;
}

/*
 * PSA AEAD encrypt.
 *
 * psa_aead_encrypt() writes ciphertext || tag into a single output buffer.
 * The old mbedtls API writes them into separate buffers, so we use a
 * temporary allocation to bridge the difference.
 */
int mbedtls_cipher_auth_encrypt_wrapper(const cipher_params_t *input,
                                        unsigned char *output, size_t *olen,
                                        unsigned char *tag, size_t tag_len)
{
    if (!input || !output || !olen || !tag) {
        return OPRT_INVALID_PARM;
    }

    psa_algorithm_t alg = PSA_ALG_AEAD_WITH_SHORTENED_TAG(PSA_ALG_GCM, tag_len);

    psa_key_attributes_t attrs = psa_key_attributes_init();
    psa_set_key_usage_flags(&attrs, PSA_KEY_USAGE_ENCRYPT);
    psa_set_key_algorithm(&attrs, alg);
    psa_set_key_type(&attrs, psa_key_type_from_cipher(input->cipher_type));

    psa_key_id_t key_id = PSA_KEY_ID_NULL;
    psa_status_t status = psa_import_key(&attrs, input->key, input->key_len, &key_id);
    if (status != PSA_SUCCESS) {
        ESP_LOGE(TAG, "psa_import_key failed: %d", (int)status);
        return OPRT_MID_TLS_NET_SOCKET_ERROR;
    }

    /* PSA output buffer: ciphertext || tag */
    size_t ct_buf_size = PSA_AEAD_ENCRYPT_OUTPUT_SIZE(psa_key_type_from_cipher(input->cipher_type),
                                                      alg, input->data_len);
    uint8_t *ct_buf = malloc(ct_buf_size);
    if (!ct_buf) {
        psa_destroy_key(key_id);
        return OPRT_MALLOC_FAILED;
    }

    size_t ct_len = 0;
    status = psa_aead_encrypt(key_id, alg,
                              input->nonce, input->nonce_len,
                              input->ad, input->ad_len,
                              input->data, input->data_len,
                              ct_buf, ct_buf_size, &ct_len);
    psa_destroy_key(key_id);

    if (status == PSA_SUCCESS) {
        /* ct_buf = ciphertext (data_len bytes) || tag (tag_len bytes) */
        size_t ciphertext_len = ct_len - tag_len;
        memcpy(output, ct_buf, ciphertext_len);
        memcpy(tag, ct_buf + ciphertext_len, tag_len);
        *olen = ciphertext_len;
    } else {
        ESP_LOGE(TAG, "psa_aead_encrypt failed: %d", (int)status);
    }

    free(ct_buf);
    return (status == PSA_SUCCESS) ? OPRT_OK : OPRT_MID_TLS_NET_SOCKET_ERROR;
}

/*
 * PSA AEAD decrypt.
 *
 * psa_aead_decrypt() expects ciphertext || tag concatenated as input.
 * The old mbedtls API receives them in separate buffers, so we assemble
 * a temporary buffer.
 */
int mbedtls_cipher_auth_decrypt_wrapper(const cipher_params_t *input,
                                        unsigned char *output, size_t *olen,
                                        unsigned char *tag, size_t tag_len)
{
    if (!input || !output || !olen || !tag) {
        return OPRT_INVALID_PARM;
    }

    psa_algorithm_t alg = PSA_ALG_AEAD_WITH_SHORTENED_TAG(PSA_ALG_GCM, tag_len);

    psa_key_attributes_t attrs = psa_key_attributes_init();
    psa_set_key_usage_flags(&attrs, PSA_KEY_USAGE_DECRYPT);
    psa_set_key_algorithm(&attrs, alg);
    psa_set_key_type(&attrs, psa_key_type_from_cipher(input->cipher_type));

    psa_key_id_t key_id = PSA_KEY_ID_NULL;
    psa_status_t status = psa_import_key(&attrs, input->key, input->key_len, &key_id);
    if (status != PSA_SUCCESS) {
        ESP_LOGE(TAG, "psa_import_key failed: %d", (int)status);
        return OPRT_MID_TLS_NET_SOCKET_ERROR;
    }

    /* Assemble ciphertext || tag for PSA */
    size_t ct_with_tag_len = input->data_len + tag_len;
    uint8_t *ct_buf = malloc(ct_with_tag_len);
    if (!ct_buf) {
        psa_destroy_key(key_id);
        return OPRT_MALLOC_FAILED;
    }
    memcpy(ct_buf, input->data, input->data_len);
    memcpy(ct_buf + input->data_len, tag, tag_len);

    size_t pt_buf_size = PSA_AEAD_DECRYPT_OUTPUT_SIZE(psa_key_type_from_cipher(input->cipher_type),
                                                      alg, ct_with_tag_len);
    size_t pt_len = 0;
    status = psa_aead_decrypt(key_id, alg,
                              input->nonce, input->nonce_len,
                              input->ad, input->ad_len,
                              ct_buf, ct_with_tag_len,
                              output, pt_buf_size, &pt_len);
    psa_destroy_key(key_id);
    free(ct_buf);

    if (status == PSA_SUCCESS) {
        *olen = pt_len;
    } else {
        ESP_LOGE(TAG, "psa_aead_decrypt failed: %d", (int)status);
    }

    return (status == PSA_SUCCESS) ? OPRT_OK : OPRT_MID_TLS_NET_SOCKET_ERROR;
}

/* -------------------------------------------------------------------------
 * Hash / HMAC — mbedtls MD API (still public in mbedtls 4.x)
 * ---------------------------------------------------------------------- */

int mbedtls_message_digest(mbedtls_md_type_t md_type,
                           const uint8_t *input, size_t ilen,
                           uint8_t *digest)
{
    if (!input || ilen == 0 || !digest) {
        return -1;
    }

    mbedtls_md_context_t md_ctx;
    mbedtls_md_init(&md_ctx);
    int ret = mbedtls_md_setup(&md_ctx, mbedtls_md_info_from_type(md_type), 0);
    if (ret != 0) {
        ESP_LOGE(TAG, "mbedtls_md_setup returned -0x%04x", -ret);
        goto exit;
    }

    mbedtls_md_starts(&md_ctx);
    mbedtls_md_update(&md_ctx, input, ilen);
    mbedtls_md_finish(&md_ctx, digest);

exit:
    mbedtls_md_free(&md_ctx);
    return ret;
}

int mbedtls_message_digest_hmac(mbedtls_md_type_t md_type,
                                const uint8_t *key, size_t keylen,
                                const uint8_t *input, size_t ilen,
                                uint8_t *digest)
{
    if (!key || keylen == 0 || !input || ilen == 0 || !digest) {
        return -1;
    }

    mbedtls_md_context_t md_ctx;
    mbedtls_md_init(&md_ctx);
    int ret = mbedtls_md_setup(&md_ctx, mbedtls_md_info_from_type(md_type), 1);
    if (ret != 0) {
        ESP_LOGE(TAG, "mbedtls_md_setup returned -0x%04x", -ret);
        goto exit;
    }

    mbedtls_md_hmac_starts(&md_ctx, key, keylen);
    mbedtls_md_hmac_update(&md_ctx, input, ilen);
    mbedtls_md_hmac_finish(&md_ctx, digest);

exit:
    mbedtls_md_free(&md_ctx);
    return ret;
}
