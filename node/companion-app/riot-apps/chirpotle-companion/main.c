#include <stdio.h>

#if defined(MODULE_SHELL) && defined(MODULE_SHELL_COMMANDS)
#define WITH_SHELL
#endif

#ifdef WITH_SHELL
#include "shell.h"
#include "shell_commands.h"
#include "thread.h"
#endif

#ifdef WITH_WIFI
#include "if_wifi.h"
#include "net/gnrc/netif.h"
#endif

#include "periph/spi.h"

#include "lora_daemon.h"
#include "lora_if.h"
#include "lora_modem.h"

#if defined(LORA_INTERFACE_TCP)
#include "lora_if_tcp.h"
#elif defined(LORA_INTERFACE_UART)
#include "lora_if_uart.h"
#elif defined(LORA_INTERFACE_STDIO)
#include "lora_if_stdio.h"
#endif

/* Assign the active interface to lora_interface */
#if defined(LORA_INTERFACE_TCP)
/** Structure for the interface */
const lora_interface_t *lora_interface = &lora_interface_tcp;
const char if_name[] = "TCP";
#elif defined(LORA_INTERFACE_UART)
/** Structure for the interface */
const lora_interface_t *lora_interface = &lora_interface_uart;
const char if_name[] = "UART";
#elif defined(LORA_INTERFACE_STDIO)
const lora_interface_t *lora_interface = &lora_interface_stdio;
const char if_name[] = "STDIO";
#endif

#ifndef LORA_SPI_BUS
#define LORA_SPI_BUS SPI_DEV(0)
#endif
#ifndef LORA_SPI_CS
#define LORA_SPI_CS SPI_HWCS(0)
#endif

#ifdef MODULE_PERIPH_GPIO
#ifndef LORA_GPIO_RESET
#define LORA_GPIO_RESET GPIO_UNDEF
#endif
#ifndef LORA_GPIO_DIO0
#define LORA_GPIO_DIO0 GPIO_UNDEF
#endif
#ifndef LORA_GPIO_DIO3
#define LORA_GPIO_DIO3 GPIO_UNDEF
#endif
#ifndef LORA_GPIO_SNIFFER
#define LORA_GPIO_SNIFFER GPIO_UNDEF
#endif
#ifndef LORA_GPIO_JAMMER
#define LORA_GPIO_JAMMER GPIO_UNDEF
#endif
#ifndef LORA_GPIO_TRIGGER_TX
#define LORA_GPIO_TRIGGER_TX GPIO_UNDEF
#endif
#endif

/** Structure for the modem */
lora_modem_t modem;

/** Structure for the daemon */
lora_daemon_t daemon;

#ifdef WITH_SHELL
char shell_thread_stack[THREAD_STACKSIZE_SMALL + THREAD_EXTRA_STACKSIZE_PRINTF];

void *_shell_thread(void *arg);

int _sh_dump_modem_fifo(int argc, char ** argv)
{
    lora_modem_dump_fifo(&modem);
    return 0;
}

int _sh_dump_modem_regs(int argc, char ** argv)
{
    lora_modem_dump_regs(&modem);
    return 0;
}

shell_command_t _sh_commands[] = {
    {"lmfifo", "Dumps content of the LoRa transceiver FiFo", _sh_dump_modem_fifo},
    {"lmregs", "Dumps content of the LoRa transceiver registers", _sh_dump_modem_regs},
    {NULL, NULL, NULL}
};
#endif


int main(void)
{
    // Setup modem
    modem.bus = LORA_SPI_BUS;
    modem.cs  = LORA_SPI_CS;
#ifdef MODULE_PERIPH_GPIO
    modem.gpio_reset = LORA_GPIO_RESET;
    modem.reset_on_high = false;
    modem.gpio_dio0  = LORA_GPIO_DIO0;
    modem.gpio_dio3  = LORA_GPIO_DIO3;
    modem.gpio_sniffer = LORA_GPIO_SNIFFER;
    modem.gpio_jammer = LORA_GPIO_JAMMER;
#endif
#ifdef MODULE_PERIPH_GPIO_IRQ
    modem.gpio_trigger_tx = LORA_GPIO_TRIGGER_TX;
#endif
    printf("Initializing modem... ");
    int modem_init_res = lora_modem_init(&modem);
    if (modem_init_res != LORA_MODEM_INIT_OK) {
        printf("failed with exit code 0x%x\n", modem_init_res);
        return 1;
    }
    printf("OK!\n");

    // Setup the daemon and tie it to the modem
    daemon.modem = &modem;
    printf("Starting lora_daemon... ");
    int daemon_init_res = lora_daemon_init(&daemon);
    if (modem_init_res != LORA_DAEMON_INIT_OK) {
        printf("failed with exit code 0x%x\n", daemon_init_res);
        return 1;
    }
    printf("OK!\n");

#ifdef WITH_WIFI
    printf("Connecting to WiFi... ");
    int wifi_res = if_wifi_init();
    if (wifi_res != 0) {
        printf("failed with code 0x%x\n", wifi_res);
        return 1;
    }
    gnrc_netif_t *netif = find_wifi_interface();
    if (netif != NULL) {
        modem.sniffer_if = netif->pid;
    }
    printf("OK!\n");
    if_wifi_dumpaddr();
#endif

    // Setup interface and tie it to the daemon
    printf("Initializing interface %s... ", if_name);
    int interface_init_res = lora_interface->init(&daemon);
    if (interface_init_res != LORA_INTERFACE_SETUP_OK) {
        printf("failed with exit code 0x%x\n", interface_init_res);
        return 1;
    }
    printf("OK!\n");

    printf("Starting interface... ");
    // Start the threads for modem, daemon and interface
    lora_interface->start();
    printf("Done!\n");

#ifdef WITH_SHELL
    printf("Starting Shell...\n");
    thread_create(
        shell_thread_stack, sizeof(shell_thread_stack),
        THREAD_PRIORITY_IDLE - 1, THREAD_CREATE_STACKTEST,
        _shell_thread, NULL, "shell");
#endif
    printf("Ready.\n");
    return 0;
}

#ifdef WITH_SHELL
void *_shell_thread(void *arg)
{
    char line_buf[SHELL_DEFAULT_BUFSIZE];
    shell_run(_sh_commands, line_buf, SHELL_DEFAULT_BUFSIZE);

    return arg;
}
#endif
