#include <string.h>
#include <stdlib.h>

#include "periph/gpio.h"
#include "periph/spi.h"
#include "periph/uart.h"

#include "shell.h"
#include "thread.h"

#include "lora_modem.h"

#include "appconfig.h"
#include "gps.h"
#include "lora.h"

/** Send records to the GPS directly */
static int _cmd_gps_sendrec(int argc, char **argv);

/** Shell command to print GPS info */
static int _cmd_gps_info(int argc, char **argv);

/** Command to enable GPS dumping */
static int _cmd_gps_dump(int argc, char **argv);

static int _cmd_lora_setfreq(int argc, char **argv);

static int _cmd_lora_setsf(int argc, char **argv);

static int _cmd_lora_setbw(int argc, char **argv);


/** Shell thread */
static void *_thread_shell(void *arg);

/** Shell thread stack */
char shell_thread_stack[THREAD_STACKSIZE_MEDIUM + THREAD_EXTRA_STACKSIZE_PRINTF];

/** GPS Thread */
char gps_thread_stack[THREAD_STACKSIZE_MEDIUM + THREAD_EXTRA_STACKSIZE_PRINTF];


/** Shell command list */
const shell_command_t commands[] = {
    {"gps_enable_dump", "Prints raw NMEA sentences", _cmd_gps_dump},
    {"gps_sendrec", "Send a record to the GPS device", _cmd_gps_sendrec},
    {"gps_info", "Prints GPS information", _cmd_gps_info},
    {"lora_setfreq", "Sets the center freq of the modem", _cmd_lora_setfreq},
    {"lora_setsf", "Sets the spreading factor of the modem", _cmd_lora_setsf},
    {"lora_setbw", "Sets the bandwidth of the modem", _cmd_lora_setbw},
    {NULL, NULL, NULL},
};

int main(void)
{
    printf("Initializing LoRa modems... ");
    int modem_init_res = lora_setup();
    if (modem_init_res != 0) {
        printf("failed with exit code 0x%x\n", modem_init_res);
        return 1;
    }
    printf("OK!\n");

    printf("Starting GPS thread...");
    thread_create(
        gps_thread_stack, sizeof(gps_thread_stack),
        THREAD_PRIORITY_IDLE - 2, THREAD_CREATE_STACKTEST,
        thread_gps, NULL, "gps");
    printf("OK!\n");


    printf("Starting Shell...\n");
    thread_create(
        shell_thread_stack, sizeof(shell_thread_stack),
        THREAD_PRIORITY_IDLE - 1, THREAD_CREATE_STACKTEST,
        _thread_shell, NULL, "shell");
    return 0;
}

static int _cmd_gps_dump(int argc, char **argv)
{
    if (argc != 2) {
        printf("Call %s <0|1>\n", argv[0]);
        return 1;
    }
    gps_enable_dump(argv[1][0] == '1');
    return 0;
}

static int _cmd_gps_info(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    printf("\n{\"gps\":{\"valid\": %s, ", gps_get_valid() ? "true" : "false");
    printf("\"sattelites\": %d, ", gps_get_sattelites());
    printf("\"time\": %d}}\n", gps_get_time());
    return 0;
}

static int _cmd_gps_sendrec(int argc, char **argv)
{
    if (argc > 1) {
        uart_write(GPS_UART, (uint8_t*)argv[1], strlen(argv[1]));
        uart_write(GPS_UART, (const uint8_t*)"\r\n", 2);
        return 0;
    }
    printf("Usage: %s <sentence>", argv[0]);
    return 1;
}

static int _cmd_lora_setfreq(int argc, char **argv)
{
    if (argc > 1) {
        uint32_t freq = atoi(argv[1]);
        if (freq >= 866000000 && freq <= 870000000) {
            if (lora_set_freq(freq)!=0) {
                puts("failed\n");
                return 1;
            }
            puts("frequency ok");
            return 0;
        }
    }
    puts("invalid\n");
    return 1;
}

static int _cmd_lora_setsf(int argc, char **argv)
{
    if (argc > 1) {
        int sf = atoi(argv[1]);
        if(lora_set_sf(sf) != 0) {
            puts("failed");
            return 1;
        }
        puts("sf ok");
        return 0;
    }
    puts("invalid");
    return 1;
}

static int _cmd_lora_setbw(int argc, char **argv)
{
    if (argc > 1) {
        int bw = atoi(argv[1]);
        if(lora_set_bw(bw) != 0) {
            puts("failed");
            return 1;
        }
        puts("bandwidth ok");
        return 0;
    }
    puts("invalid");
    return 1;
}

static void *_thread_shell(void *arg)
{
    char line_buf[SHELL_DEFAULT_BUFSIZE];
    shell_run(commands, line_buf, SHELL_DEFAULT_BUFSIZE);
    return arg;
}