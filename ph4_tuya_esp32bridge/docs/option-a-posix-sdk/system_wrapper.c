/*
 * ESP32 system wrapper for tuya-iot-core-sdk.
 *
 * Replaces platform/posix/system_wrapper.c for the single function that
 * does not work on ESP-IDF's newlib: system_sleep() uses nanosleep() which
 * is not provided by newlib. All other functions (malloc/calloc/free,
 * clock_gettime, gettimeofday, rand) are available on ESP-IDF and kept as-is.
 *
 * system_sleep() is replaced with vTaskDelay() which is the idiomatic
 * FreeRTOS sleep and works correctly on ESP32.
 */

#ifdef __cplusplus
extern "C" {
#endif

#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <sys/time.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "system_interface.h"

void *system_malloc(size_t n)
{
    return malloc(n);
}

void *system_calloc(size_t n, size_t size)
{
    return calloc(n, size);
}

void system_free(void *ptr)
{
    free(ptr);
}

uint32_t system_ticks(void)
{
    struct timespec current_time;
    clock_gettime(CLOCK_MONOTONIC, &current_time);
    return (uint32_t)((current_time.tv_sec * 1000) + (current_time.tv_nsec / 1000000));
}

uint32_t system_timestamp(void)
{
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (uint32_t)tv.tv_sec;
}

void system_sleep(uint32_t time_ms)
{
    /* nanosleep() is not available on ESP-IDF's newlib; use vTaskDelay. */
    if (time_ms == 0) {
        taskYIELD();
    } else {
        vTaskDelay(pdMS_TO_TICKS(time_ms));
    }
}

uint32_t system_random(void)
{
    return (uint32_t)rand();
}

#ifdef __cplusplus
}
#endif
