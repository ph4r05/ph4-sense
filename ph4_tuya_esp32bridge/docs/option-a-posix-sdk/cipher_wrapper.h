/*
 * ESP32 compatibility shim for cipher_wrapper.h — PSA Crypto backend.
 *
 * In mbedtls 4.x (ESP-IDF 6.x):
 *   - mbedtls/cipher.h removed from public API (moved to PSA Crypto)
 *   - mbedtls/md.h still exists but the HMAC sub-API
 *     (mbedtls_md_hmac_starts/update/finish) was removed; use PSA MAC instead
 *
 * This header replaces include/cipher_wrapper.h. platform/esp32/ is first in
 * INCLUDE_DIRS, so this file shadows the SDK's include/cipher_wrapper.h.
 *
 * Design decisions:
 *   - mbedtls/md.h IS included here: it defines mbedtls_md_type_t as an enum
 *     and is guarded by its own include-guard, so it's safe to include regardless
 *     of whether psa/crypto.h was included first (both pull in the same header).
 *   - mbedtls_cipher_type_t is NOT redefined here: psa/crypto.h pulls in
 *     private/cipher.h which defines it as an enum; our typedef would conflict.
 *     cipher_params_t.cipher_type uses plain int instead.
 *   - Only tuyalink_core.c uses this header (for mbedtls_message_digest_hmac);
 *     the AEAD wrappers are not called externally.
 */

#ifndef __CRYPTO_WRAPPER_H_
#define __CRYPTO_WRAPPER_H_

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stddef.h>

/* mbedtls/md.h provides mbedtls_md_type_t (enum) and MBEDTLS_MD_SHA256.
 * It is guarded by MBEDTLS_MD_H so safe to include multiple times.
 * psa/crypto.h also pulls it in transitively — no conflict. */
#include "mbedtls/md.h"

/* cipher_type: use int to avoid clash with the mbedtls_cipher_type_t enum
 * that psa/crypto.h pulls in via private/cipher.h. Only AES-GCM is used. */
#define MBEDTLS_CIPHER_AES_128_GCM  1
#define MBEDTLS_CIPHER_AES_256_GCM  2

typedef struct {
    unsigned char *key;
    unsigned char *nonce;
    unsigned char *ad;
    unsigned char *data;
    size_t key_len;
    size_t nonce_len;
    size_t ad_len;
    size_t data_len;
    int cipher_type;   /* MBEDTLS_CIPHER_AES_*_GCM — not externally constructed */
} cipher_params_t;


int mbedtls_cipher_auth_encrypt_wrapper(const cipher_params_t *input,
                                        unsigned char *output, size_t *olen,
                                        unsigned char *tag, size_t tag_len);

int mbedtls_cipher_auth_decrypt_wrapper(const cipher_params_t *input,
                                        unsigned char *output, size_t *olen,
                                        unsigned char *tag, size_t tag_len);

int mbedtls_message_digest(mbedtls_md_type_t md_type,
                           const uint8_t *input, size_t ilen,
                           uint8_t *digest);

int mbedtls_message_digest_hmac(mbedtls_md_type_t md_type,
                                const uint8_t *key, size_t keylen,
                                const uint8_t *input, size_t ilen,
                                uint8_t *digest);

#ifdef __cplusplus
}
#endif
#endif /* __CRYPTO_WRAPPER_H_ */
