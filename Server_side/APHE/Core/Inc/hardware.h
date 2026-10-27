#ifndef HARDWARE_H
#define HARDWARE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* --------------------------------------------------------------------------
 * Generic Hardware Abstraction Interface
 * --------------------------------------------------------------------------
 * Core logic calls these generic functions, which are implemented by the
 * HAL wrapper (hardware.c). This keeps business logic completely portable
 * and testable under host-based unit tests.
 * -------------------------------------------------------------------------- */

/**
 * @brief  Read a generic sensor / digital input pin.
 * @return 1 if active / high, 0 if inactive / low.
 */
uint8_t sensor_read(void);

/**
 * @brief  Set connection status LED.
 * @param  state: 1 for ON, 0 for OFF.
 */
void led_conn_set(uint8_t state);

/**
 * @brief  Set game status LED.
 * @param  state: 1 for ON, 0 for OFF.
 */
void led_game_set(uint8_t state);

/**
 * @brief  Toggle game status LED.
 */
void led_game_toggle(void);

#ifdef __cplusplus
}
#endif

#endif /* HARDWARE_H */
