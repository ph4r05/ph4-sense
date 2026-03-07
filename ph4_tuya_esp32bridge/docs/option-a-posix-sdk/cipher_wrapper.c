/*
 * ESP32 cipher wrapper for tuya-iot-core-sdk — PSA Crypto backend.
 *
 * Replaces src/cipher_wrapper.c. All operations use the PSA Crypto API
 * (psa/crypto.h) which is stable across mbedtls versions in ESP-IDF.
 *
 * In mbedtls 4.x (ESP-IDF 6.x) the following were removed from public API:
 *   - mbedtls/cipher.h   (cipher context / AEAD functions)
 *   - mbedtls_md_hmac_starts / mbedtls_md_hmac_update / mbedtls_md_hmac_finish
 *
 * Replacements:
 *   AEAD encrypt/decrypt  → psa_aead_encrypt / psa_aead_decrypt
 *   SHA-256 hash          → psa_hash_compute
 *   HMAC-SHA-256          → psa_mac_compute  (import HMAC key + one-shot MAC)
 *
 * Implements: platform/esp32/cipher_wrapper.h
 *   mbedtls_cipher_auth_encrypt_wrapper
 *   mbedtls_cipher_auth_decrypt_wrapper
 *   mbedtls_message_digest
 *   mbedtls_message_digest_hmac
 */

#include <string.h>
#include <stdlib.h>

#include "psa/crypto.h"
#include "esp_log.h"

#include "cipher_wrapper.h"
#include "tuya_error_code.h"

static const char *TAG = "tuya_cipher";

/* -------------------------------------------------------------------------
 * Internal helpers
 * ---------------------------------------------------------------------- */

/* Map our MBEDTLS_MD_* compat constant to the PSA hash algorithm. */
static psa_algorithm_t md_to_psa_hash(mbedtls_md_type_t md_type)
{
    if (md_type == MBEDTLS_MD_SHA256) {
        return PSA_ALG_SHA_256;
    }
    ESP_LOGE(TAG, "Unsupported md_type %d", (int)md_type);
    return PSA_ALG_NONE;
}

/* -------------------------------------------------------------------------
 * AEAD (AES-GCM) via PSA Crypto
 *
 * psa_aead_encrypt() writes ciphertext || tag into a single buffer.
 * The old mbedtls API had separate output / tag buffers — bridge with malloc.
 * ---------------------------------------------------------------------- */

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
    psa_set_key_type(&attrs, PSA_KEY_TYPE_AES);

    psa_key_id_t key_id = PSA_KEY_ID_NULL;
    psa_status_t status = psa_import_key(&attrs, input->key, input->key_len, &key_id);
    if (status != PSA_SUCCESS) {
        ESP_LOGE(TAG, "psa_import_key (enc) failed: %d", (int)status);
        return OPRT_MID_TLS_NET_SOCKET_ERROR;
    }

    /* PSA output: ciphertext || tag in one buffer */
    size_t ct_buf_size = PSA_AEAD_ENCRYPT_OUTPUT_SIZE(PSA_KEY_TYPE_AES, alg, input->data_len);
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
    psa_set_key_type(&attrs, PSA_KEY_TYPE_AES);

    psa_key_id_t key_id = PSA_KEY_ID_NULL;
    psa_status_t status = psa_import_key(&attrs, input->key, input->key_len, &key_id);
    if (status != PSA_SUCCESS) {
        ESP_LOGE(TAG, "psa_import_key (dec) failed: %d", (int)status);
        return OPRT_MID_TLS_NET_SOCKET_ERROR;
    }

    /* PSA decrypt expects ciphertext || tag concatenated */
    size_t ct_with_tag_len = input->data_len + tag_len;
    uint8_t *ct_buf = malloc(ct_with_tag_len);
    if (!ct_buf) {
        psa_destroy_key(key_id);
        return OPRT_MALLOC_FAILED;
    }
    memcpy(ct_buf, input->data, input->data_len);
    memcpy(ct_buf + input->data_len, tag, tag_len);

    size_t pt_buf_size = PSA_AEAD_DECRYPT_OUTPUT_SIZE(PSA_KEY_TYPE_AES, alg, ct_with_tag_len);
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
 * Hash / HMAC — PSA one-shot API
 *
 * mbedtls_md_hmac_starts/update/finish were removed in mbedtls 4.x.
 * Use psa_hash_compute and psa_mac_compute instead.
 * ---------------------------------------------------------------------- */

int mbedtls_message_digest(mbedtls_md_type_t md_type,
                           const uint8_t *input, size_t ilen,
                           uint8_t *digest)
{
    if (!input || ilen == 0 || !digest) {
        return -1;
    }

    psa_algorithm_t alg = md_to_psa_hash(md_type);
    if (alg == PSA_ALG_NONE) {
        return -1;
    }

    size_t hash_len = 0;
    psa_status_t status = psa_hash_compute(alg, input, ilen,
                                           digest, PSA_HASH_MAX_SIZE, &hash_len);
    if (status != PSA_SUCCESS) {
        ESP_LOGE(TAG, "psa_hash_compute failed: %d", (int)status);
        return -1;
    }
    return 0;
}

int mbedtls_message_digest_hmac(mbedtls_md_type_t md_type,
                                const uint8_t *key, size_t keylen,
                                const uint8_t *input, size_t ilen,
                                uint8_t *digest)
{
    if (!key || keylen == 0 || !input || ilen == 0 || !digest) {
        return -1;
    }

    psa_algorithm_t hash_alg = md_to_psa_hash(md_type);
    if (hash_alg == PSA_ALG_NONE) {
        return -1;
    }
    psa_algorithm_t hmac_alg = PSA_ALG_HMAC(hash_alg);

    psa_key_attributes_t attrs = psa_key_attributes_init();
    psa_set_key_usage_flags(&attrs, PSA_KEY_USAGE_SIGN_MESSAGE);
    psa_set_key_algorithm(&attrs, hmac_alg);
    psa_set_key_type(&attrs, PSA_KEY_TYPE_HMAC);

    psa_key_id_t key_id = PSA_KEY_ID_NULL;
    psa_status_t status = psa_import_key(&attrs, key, keylen, &key_id);
    if (status != PSA_SUCCESS) {
        ESP_LOGE(TAG, "psa_import_key (hmac) failed: %d", (int)status);
        return -1;
    }

    size_t mac_len = 0;
    status = psa_mac_compute(key_id, hmac_alg,
                             input, ilen,
                             digest, PSA_MAC_MAX_SIZE, &mac_len);
    psa_destroy_key(key_id);

    if (status != PSA_SUCCESS) {
        ESP_LOGE(TAG, "psa_mac_compute failed: %d", (int)status);
        return -1;
    }
    return 0;
}
