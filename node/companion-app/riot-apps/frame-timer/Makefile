APPLICATION = frame-timer
RIOTBASE ?= $(CURDIR)/../../RIOT
BOARD ?= esp32-wroom-32

# ------------------------------------------------------------------------------
# External modules
# ------------------------------------------------------------------------------
EXTERNAL_MODULES_BASE ?= $(CURDIR)/../../riot-modules
EXTERNAL_MODULE_DIRS += $(EXTERNAL_MODULES_BASE)
INCLUDES += -I$(EXTERNAL_MODULES_BASE)/include

# ------------------------------------------------------------------------------
# Debug and development settings
# ------------------------------------------------------------------------------
# Comment this out to disable code in RIOT that does safety checking
# which is not needed in a production environment but helps in the
# development process:
DEVELHELP ?= 1

# Change this to 0 show compiler invocation lines by default:
QUIET ?= 1

# ------------------------------------------------------------------------------
# Default modules
# ------------------------------------------------------------------------------
# Access to the lora_modem to transmit beacons
USEMODULE += lora_modem

# MINMEA NMEA parsing library
USEPKG += minmea

# Shell support
USEMODULE += shell
USEMODULE += shell_commands
USEMODULE += ps

CFLAGS += -DSHELL_NO_PROMPT
CFLAGS += -DSHELL_NO_ECHO

# Timer support
USEMODULE += xtimer

# USE GPIOs and interrupts for PPS
FEATURES_REQUIRED += periph_gpio
FEATURES_REQUIRED += periph_gpio_irq

# ------------------------------------------------------------------------------
# GPS Configuration
# ------------------------------------------------------------------------------
# GPIO that the 1PPS output of the module is connected to
GPS_GPIO_PPS ?= "GPIO_PIN(0, 35)"

# UART interface for NMEA records
GPS_UART ?= "UART_DEV(2)"
CFLAGS += -DUART2_TXD=GPIO17
CFLAGS += -DUART2_RXD=GPIO16

# ------------------------------------------------------------------------------
# LoRa Configuration
# ------------------------------------------------------------------------------
# Select the SPI device to which the modem is connected to
LORA_SPI_BUS ?= "SPI_DEV(1)"

# Select the chip select line to which the modem is connected to
LORA1_SPI_CS  ?= "GPIO_PIN(0, 15)"

# Reset pin of the modem.
LORA1_GPIO_RESET ?= "GPIO_PIN(0, 33)"

# DIO0 pin for TXDone
LORA1_GPIO_DIO0 ?= "GPIO_PIN(0, 32)"

# Unused (only used for valid header, so setting it to the rxdone interrupt DIO line unblocks the device, too)
LORA1_GPIO_DIO3 ?= "GPIO_PIN(0, 32)"

# Second transceiver. Shared SPI bus, separate CS line
LORA2_SPI_CS  ?= "GPIO_PIN(0, 5)"
LORA2_GPIO_RESET ?= "GPIO_PIN(0, 27)"
LORA2_GPIO_DIO0 ?= "GPIO_PIN(0, 19)"
LORA2_GPIO_DIO3 ?= "GPIO_PIN(0, 18)"

# ------------------------------------------------------------------------------
# Build Preparation
# ------------------------------------------------------------------------------
# Pass transceiver wiring to the app
CFLAGS += -DGPS_GPIO_PPS=$(GPS_GPIO_PPS)
CFLAGS += -DGPS_UART=$(GPS_UART)
CFLAGS += -DLORA_SPI_BUS=$(LORA_SPI_BUS)
CFLAGS += -DLORA1_SPI_CS=$(LORA1_SPI_CS)
CFLAGS += -DLORA1_GPIO_RESET=$(LORA1_GPIO_RESET)
CFLAGS += -DLORA1_GPIO_DIO0=$(LORA1_GPIO_DIO0)
CFLAGS += -DLORA1_GPIO_DIO3=$(LORA1_GPIO_DIO3)
CFLAGS += -DLORA2_SPI_CS=$(LORA2_SPI_CS)
CFLAGS += -DLORA2_GPIO_RESET=$(LORA2_GPIO_RESET)
CFLAGS += -DLORA2_GPIO_DIO0=$(LORA2_GPIO_DIO0)
CFLAGS += -DLORA2_GPIO_DIO3=$(LORA2_GPIO_DIO3)

# Local headers
INCLUDES += -I$(CURDIR)/include

include $(RIOTBASE)/Makefile.include