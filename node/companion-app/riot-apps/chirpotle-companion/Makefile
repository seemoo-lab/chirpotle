APPLICATION = chirpotle-companion
RIOTBASE ?= $(CURDIR)/../../../../submodules/RIOT
BOARD ?= native

# ------------------------------------------------------------------------------
# Preconfigured boards
# ------------------------------------------------------------------------------
# For some boards, there are already some preconfigurations in the
# Makefiles.preconf file, so we include it here
include $(CURDIR)/Makefile.preconf

# ------------------------------------------------------------------------------
# Local modules and boards
# ------------------------------------------------------------------------------
# Add custom modules directory
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
# We need the lora_daemon to run in the background for all interfaces
USEMODULE += lora_daemon
# The deamon requires either lora_modem or lora_modem_null to be present. For
# the actual application, we need the real module
USEMODULE += lora_modem

# ------------------------------------------------------------------------------
# Interface Selection
# ------------------------------------------------------------------------------
# The frontend interface depends on the deployment scenario.
# The value of INTERFACE may already been defined in Makefile.preconf

INTERFACE ?= uart
ifeq ($(INTERFACE),uart)
	USEMODULE += lora_if_uart
	CFLAGS += -DLORA_INTERFACE_UART
else ifeq ($(INTERFACE),tcp)
	USEMODULE += lora_if_tcp
	CFLAGS += -DLORA_INTERFACE_TCP
	# Allow more than 2 IP addresses
	CFLAGS += -DGNRC_NETIF_IPV6_ADDRS_NUMOF=4
else ifeq ($(INTERFACE),stdio)
	USEMODULE += lora_if_stdio
	CFLAGS += -DLORA_INTERFACE_STDIO
else
$(error Unknown interface type: $(INTERFACE). Available options: uart, tcp)
endif
$(info Interface type: $(INTERFACE))

# ------------------------------------------------------------------------------
# Hardware specification
# ------------------------------------------------------------------------------
# These are mostly fallback values used if no configuration has been specified
# by either passing a board listed in Makefile.preconf or setting the values
# when starting the build.
# They provide a minimal working example without interrupts using the first
# hardware SPI device and a UART interface.

# Select the SPI device to which the modem is connected to
LORA_SPI_BUS ?= "SPI_DEV(0)"

# Select the chip select line to which the modem is connected to
LORA_SPI_CS  ?= "SPI_HWCS(0)"

# Reset pin of the modem. Not required, but makes the whole thing more stable,
# e.g. after rebooting the controller
LORA_GPIO_RESET ?= "GPIO_UNDEF"

# Assign DIO0/3 Pins from the modem to GPIOs. Unavailable DIOs may be mapped to
# GPIO_UNDEF. If possible, try to use IRQ-enabled lines.
LORA_GPIO_DIO0 ?= "GPIO_UNDEF"
LORA_GPIO_DIO3 ?= "GPIO_UNDEF"

# Use the following GPIOs for the sniffer and jammer triggering. The jammer
# GPIO should be IRQ-enabled.
LORA_GPIO_SNIFFER ?= "GPIO_UNDEF"
LORA_GPIO_JAMMER  ?= "GPIO_UNDEF"

# This GPIO is used to trigger a synchronized transmission via an external line,
# configured using the transmit_on_gpio_trigger()
LORA_GPIO_TRIGGER_TX ?= "GPIO_UNDEF"

# If the board supports GPIOs and/or GPIO interrupts, we want to have them.
# Except for native, where IRQs aren't stable yet.
ifneq ($(BOARD),native)
FEATURES_OPTIONAL = periph_gpio_irq
endif
FEATURES_REQUIRED = periph_gpio

# Allows to force the usage of irqthread fallback even if the board supports
# hardware IRQs
FORCE_IRQ_THREAD ?= 0

# ------------------------------------------------------------------------------
# UART interface configuration
# ------------------------------------------------------------------------------

ifeq ($(INTERFACE),uart)
	# Serial interface to use for communication with the daemon
	LORA_UART_DAEMON_DEVICE ?= "UART_DEV(0)"
	# Baud rate for the daemon
	LORA_UART_DAEMON_BAUDRATE ?= 115200
endif

# ------------------------------------------------------------------------------
# TCP interface configuration
# ------------------------------------------------------------------------------

ifeq ($(INTERFACE),tcp)
	# The port to use
	LORA_TCP_DAEMON_PORT ?= 9000
endif

# ------------------------------------------------------------------------------
# Build Preparation
# ------------------------------------------------------------------------------
# Pass transceiver wiring to the app
CFLAGS += -DLORA_SPI_BUS=$(LORA_SPI_BUS)
CFLAGS += -DLORA_SPI_CS=$(LORA_SPI_CS)
CFLAGS += -DLORA_GPIO_RESET=$(LORA_GPIO_RESET)
CFLAGS += -DLORA_GPIO_DIO0=$(LORA_GPIO_DIO0)
CFLAGS += -DLORA_GPIO_DIO1=$(LORA_GPIO_DIO1)
CFLAGS += -DLORA_GPIO_DIO2=$(LORA_GPIO_DIO2)
CFLAGS += -DLORA_GPIO_DIO3=$(LORA_GPIO_DIO3)
CFLAGS += -DLORA_GPIO_DIO4=$(LORA_GPIO_DIO4)
CFLAGS += -DLORA_GPIO_DIO5=$(LORA_GPIO_DIO5)
CFLAGS += -DLORA_GPIO_SNIFFER=$(LORA_GPIO_SNIFFER)
CFLAGS += -DLORA_GPIO_JAMMER=$(LORA_GPIO_JAMMER)
CFLAGS += -DLORA_GPIO_TRIGGER_TX=$(LORA_GPIO_TRIGGER_TX)
CFLAGS += -DLORA_UART_DAEMON_DEVICE=$(LORA_UART_DAEMON_DEVICE)
CFLAGS += -DLORA_UART_DAEMON_BAUDRATE=$(LORA_UART_DAEMON_BAUDRATE)
CFLAGS += -DLORA_TCP_DAEMON_PORT=$(LORA_TCP_DAEMON_PORT)
CFLAGS += -DFORCE_IRQ_THREAD=$(FORCE_IRQ_THREAD)

# Enable debugging symbols, if neccesary
#CFLAGS += -g
#LDFLAGS += -g

# When building in Docker, pass down the dynamic command line parameters down to
# the container.
DOCKER_VOLUMES_AND_ENV += -e 'INTERFACE=$(INTERFACE)'
DOCKER_VOLUMES_AND_ENV += -e 'TARGET_ARCH=$(TARGET_ARCH)'
DOCKER_VOLUMES_AND_ENV += -e 'BOARD=$(BOARD)'
DOCKER_VOLUMES_AND_ENV += -e 'FORCE_IRQ_THREAD=$(FORCE_IRQ_THREAD)'

# Local headers
INCLUDES += -I$(CURDIR)/include

include $(RIOTBASE)/Makefile.include
