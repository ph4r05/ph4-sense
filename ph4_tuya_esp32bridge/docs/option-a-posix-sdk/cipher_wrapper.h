/*
 * ESP32 compatibility shim for cipher_wrapper.h.
 *
 * mbedtls/cipher.h was removed from the public API in mbedtls 4.x (ESP-IDF 6.x).
 * The cipher API moved to PSA Crypto. This header replaces include/cipher_wrapper.h
 * (platform/esp32/ is first in INCLUDE_DIRS, so it shadows the SDK version).
 *
 * Changes from the original:
 *   - Removed #include "mbedtls/cipher.h"  (does not exist in mbedtls 4.x)
 *   - Removed #include "mbedtls/platform.h" (not needed by callers)
 *   - mbedtls_cipher_type_t defined as int with local constants
 *   - mbedtls/md.h still available in mbedtls 4.x, included for mbedtls_md_type_t
 */

#ifndef __CRYPTO_WRAPPER_H_
#define __CRYPTO_WRAPPER_H_

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stddef.h>

/* mbedtls/md.h is still public in mbedtls 4.x (via tf-psa-crypto/include path).
 * Provides mbedtls_md_type_t and MBEDTLS_MD_SHA256 used by tuyalink_core.c. */
#include "mbedtls/md.h"

/* mbedtls/cipher.h is gone in mbedtls 4.x. Define only what the SDK uses. */
typedef int mbedtls_cipher_type_t;
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
    mbedtls_cipher_type_t cipher_type;
} cipher_params_t;


int mbedtls_cipher_auth_encrypt_wrapper(const cipher_params_t* input,
                                        unsigned char *output, size_t *olen,
                                        unsigned char *tag, size_t tag_len);

int mbedtls_cipher_auth_decrypt_wrapper(const cipher_params_t* input,
                                        unsigned char *output, size_t *olen,
                                        unsigned char *tag, size_t tag_len);

int mbedtls_message_digest(mbedtls_md_type_t md_type,
                           const uint8_t* input, size_t ilen,
                           uint8_t* digest);

int mbedtls_message_digest_hmac(mbedtls_md_type_t md_type,
                                const uint8_t* key, size_t keylen,
                                const uint8_t* input, size_t ilen,
                                uint8_t* digest);

#ifdef __cplusplus
}
#endif
#endif /* __CRYPTO_WRAPPER_H_ */
