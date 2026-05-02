#ifndef TUYA_CONFIG_H_
#define TUYA_CONFIG_H_

/**
 * Tuya device credentials.
 *
 * TUYA_PRODUCT_ID: Product ID from Tuya IoT Platform
 *   Create as: Custom Solution → WiFi product (NOT TuyaLink!)
 *   Set Data Center to Central Europe
 *
 * TUYA_OPENSDK_UUID / TUYA_OPENSDK_AUTHKEY:
 *   From: https://platform.tuya.com/purchase/index?type=6
 *   Or: Tuya IoT Platform → Product → Device → Authorization → get license
 *
 * WARNING: Replace these with your actual values, otherwise the device cannot work.
 */
// clang-format off
#define TUYA_PRODUCT_ID        "xxxxxxxxxxxxxxxx"                        // Your product ID
#define TUYA_OPENSDK_UUID      "uuidxxxxxxxxxxxxxxxx"                    // Your device UUID (20 chars)
#define TUYA_OPENSDK_AUTHKEY   "keyxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"        // Your device auth key (32 chars)
// clang-format on

#endif
