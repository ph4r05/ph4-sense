#pragma once
#include <stdint.h>

/**
 * Real DP ID assignment for product "Ph4BridgeSwitch" (PID g8lfcppln9qlvug2)
 * on the Tuya IoT Platform. This is NOT a linear base+offset layout — see
 * HISTORY.md for why:
 *
 *   - Switch channels 1-6 got DP 1-6, channels 7-16 got DP 101-110 (Tuya
 *     assigns new custom DPs in whatever range is free; these aren't
 *     contiguous with each other).
 *   - Relay/socket channels 7-16 got DP 111-120 (bool, correct).
 *   - Relay/socket channels 1-6 got DP 121-126, identifiers
 *     `relay_trigger_1`..`relay_trigger_6` (bool, R/W, "Send and Report"),
 *     mirroring 111-120. The identifiers are NOT `relay_status_1..6` because
 *     the original DP 29-34 ("Power-on Restart Status", an auto-generated
 *     enum function) held those identifiers, and the Tuya console would not
 *     release them even after that function was deleted from the product —
 *     see HISTORY.md. The identifier string is cosmetic; the firmware only
 *     ever talks to Tuya by numeric DP ID.
 */
#define DP_MAP_CHANNEL_COUNT 16

static const uint8_t SWITCH_DP_MAP[DP_MAP_CHANNEL_COUNT] = {
    1, 2, 3, 4, 5, 6, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110
};

static const uint8_t RELAY_DP_MAP[DP_MAP_CHANNEL_COUNT] = {
    121, 122, 123, 124, 125, 126, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120
};

static inline uint8_t switch_channel_to_dp(uint8_t channel)
{
    return (channel >= 1 && channel <= DP_MAP_CHANNEL_COUNT) ? SWITCH_DP_MAP[channel - 1] : 0;
}

static inline uint8_t relay_channel_to_dp(uint8_t channel)
{
    return (channel >= 1 && channel <= DP_MAP_CHANNEL_COUNT) ? RELAY_DP_MAP[channel - 1] : 0;
}

/* Returns 1-based channel number, or -1 if dp_id is not a known switch DP */
static inline int dp_to_switch_channel(uint8_t dp_id)
{
    for (int i = 0; i < DP_MAP_CHANNEL_COUNT; i++) {
        if (SWITCH_DP_MAP[i] == dp_id) return i + 1;
    }
    return -1;
}

/* Returns 1-based channel number, or -1 if dp_id is not a known relay DP */
static inline int dp_to_relay_channel(uint8_t dp_id)
{
    for (int i = 0; i < DP_MAP_CHANNEL_COUNT; i++) {
        if (RELAY_DP_MAP[i] == dp_id) return i + 1;
    }
    return -1;
}
