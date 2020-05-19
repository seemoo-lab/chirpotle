#ifndef _BEACON_TOOL_APPCONFIG_H
#define _BEACON_TOOL_APPCONFIG_H

#include "periph/gpio.h"
#include "periph/spi.h"
#include "periph/uart.h"

/* ------------- LoRa Transceiver Configuration ------------- */
#ifndef LORA_SPI_BUS
#define LORA_SPI_BUS SPI_DEV(0)
#endif
#ifndef LORA1_SPI_CS
#define LORA1_SPI_CS  SPI_HWCS(0)
#endif
#ifndef LORA1_GPIO_RESET
#define LORA1_GPIO_RESET GPIO_UNDEF
#endif
#ifndef LORA1_GPIO_DIO0
#define LORA1_GPIO_DIO0  GPIO_UNDEF
#endif
#ifndef LORA1_GPIO_DIO3
#define LORA1_GPIO_DIO3  GPIO_UNDEF
#endif

#ifndef LORA2_SPI_CS
#define LORA2_SPI_CS  SPI_HWCS(1)
#endif
#ifndef LORA2_GPIO_RESET
#define LORA2_GPIO_RESET GPIO_UNDEF
#endif
#ifndef LORA2_GPIO_DIO0
#define LORA2_GPIO_DIO0  GPIO_UNDEF
#endif
#ifndef LORA2_GPIO_DIO3
#define LORA2_GPIO_DIO3  GPIO_UNDEF
#endif

/* -------------   GPS Receiver Configuration   ------------- */
#ifndef GPS_GPIO_PPS
#define GPS_GPIO_PPS    GPIO_UNDEF
#endif
#ifndef GPS_UART
#define GPS_UART        UART_DEV(0)
#endif
#ifndef GPS_BAUDRATE
#define GPS_BAUDRATE    9600
#endif

#endif