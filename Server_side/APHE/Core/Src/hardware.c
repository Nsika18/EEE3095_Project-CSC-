/**
 ******************************************************************************
 * @file           : hardware.c
 * @brief          : HAL wrapper implementing generic hardware functions
 ******************************************************************************
 */

#include "hardware.h"
#include "main.h"

/* When compiling for the STM32 target, stm32f0xx_hal.h is provided by the HAL driver.
 * When compiling for host unit tests, mock_stm32f0xx_hal.h or support header is used. */
#include "stm32f0xx_hal.h"

#ifndef LED_Pin
#define LED_Pin          GPIO_PIN_5
#define LED_GPIO_Port    GPIOB
#endif

#ifndef LED_CONN_Pin
#define LED_CONN_Pin     GPIO_PIN_4
#define LED_CONN_Port    GPIOB
#endif

#ifndef SENSOR_Pin
#define SENSOR_Pin       GPIO_PIN_0
#define SENSOR_GPIO_Port GPIOA
#endif

/**
 * @brief  Read a generic sensor / digital input pin.
 * @return 1 if pin is HIGH / SET, 0 if RESET.
 */
uint8_t sensor_read(void)
{
    GPIO_PinState state = HAL_GPIO_ReadPin(SENSOR_GPIO_Port, SENSOR_Pin);
    return (state == GPIO_PIN_SET) ? 1U : 0U;
}

/**
 * @brief  Set connection status LED.
 * @param  state: 1 for ON, 0 for OFF.
 */
void led_conn_set(uint8_t state)
{
    HAL_GPIO_WritePin(LED_CONN_Port, LED_CONN_Pin, (state != 0U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

/**
 * @brief  Set game status LED.
 * @param  state: 1 for ON, 0 for OFF.
 */
void led_game_set(uint8_t state)
{
    HAL_GPIO_WritePin(LED_GPIO_Port, LED_Pin, (state != 0U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

/**
 * @brief  Toggle game status LED.
 */
void led_game_toggle(void)
{
    HAL_GPIO_TogglePin(LED_GPIO_Port, LED_Pin);
}
