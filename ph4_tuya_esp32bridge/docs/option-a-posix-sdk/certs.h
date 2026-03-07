/*
 * Compatibility shim for mbedtls/certs.h.
 *
 * mbedtls 3.x (used by ESP-IDF 5.x) removed certs.h. This empty header
 * satisfies the #include in platform/posix/network_wrapper.c without
 * requiring any changes to the upstream SDK source files.
 *
 * It works because network_wrapper.c includes certs.h for completeness
 * but does not actually use any symbols from it (no mbedtls_test_cas_pem
 * or similar test-certificate globals are referenced in the Tuya code).
 */
