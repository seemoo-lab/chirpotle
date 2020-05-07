#include "lora_if_uart.h"

#include <string.h>

#include "periph/uart.h"
#include "pipe.h"
#include "ringbuffer.h"
#include "thread.h"

#include "lora_daemon.h"

#define ENABLE_DEBUG (0)
#include "debug.h"

#ifndef LORA_UART_DAEMON_DEVICE
#define LORA_UART_DAEMON_DEVICE UART_DEV(0)
#endif

#ifndef LORA_UART_DAEMON_BAUDRATE
#define LORA_UART_DAEMON_BAUDRATE (115200)
#endif

/** The device to use for UART */
static uart_t dev_uart = LORA_UART_DAEMON_DEVICE;

/** Ring buffer for serial input (so that the interrupt-handler can act quickly) */
static ringbuffer_t ringbuf_in;

/** Backing buffer for the ringbuffer */
static char buf_in[256];

/** Pipe on top of the ringbuffer */
static pipe_t pipe_in;

/** The daemon to use */
static lora_daemon_t *daemon = NULL;

/** PID for the interface */
static kernel_pid_t pid = KERNEL_PID_UNDEF;

/** Stack for the interface thread */
#if THREAD_STACKSIZE_LARGE > 2048
    char thread_stack[THREAD_STACKSIZE_LARGE + THREAD_EXTRA_STACKSIZE_PRINTF];
#else
    char thread_stack[2048 + THREAD_EXTRA_STACKSIZE_PRINTF];
#endif

/** Initialization */
static int _init(lora_daemon_t *d);

/** Callback used for rx on the serial terminal */
static void _rx_cb(void *arg, uint8_t data);

/** The thread passing data from and to the daemon */
static void *_serial_thread(void* arg);

/** Function to start this interface */
static void _start(void);

static void _uart_write_byte(int b);
static int _uart_read_byte(void);

static int _init(lora_daemon_t *d)
{
    if (dev_uart == UART_UNDEF) {
        return LORA_INTERFACE_DEV_MISSING;
    }
    if (uart_init(dev_uart, LORA_UART_DAEMON_BAUDRATE, &_rx_cb, NULL) != 0) {
        return LORA_INTERFACE_SETUP_FAIL;
    }

    /* Configure the ring buffer for uart input */
    memset(buf_in, 0, sizeof(buf_in));
    ringbuffer_init(&ringbuf_in, buf_in, sizeof(buf_in));
    pipe_init(&pipe_in, &ringbuf_in, NULL);

    daemon = d;
    return LORA_INTERFACE_SETUP_OK;
}

static void *_serial_thread(void* arg)
{
    (void)arg;
    while(true) {
        /* Wait for start sequence */
        int b = _uart_read_byte();
        while (ESCSEQ_OBJ_START != b) {
            /* Answer heartbeat */
            if (b == ESCSEQ_PING) {
                _uart_write_byte(ESCSEQ_PONG);
            }
            b = _uart_read_byte();
        }
        DEBUG("if_uart: Command start.\n");
        lora_daemon_acquire(daemon);

        /* UART -> Daemon */
        uint8_t buf[32] = { 0 };
        size_t bytes_read = 0;
        bool end_reached = false;
        do {
            int next_byte = _uart_read_byte();
            if (next_byte == ESCSEQ_OBJ_END) {
                end_reached = true;
            }
            else {
                buf[bytes_read++] = (uint8_t)next_byte;
            }
            if (bytes_read == sizeof(buf) || end_reached) {
                lora_daemon_write(daemon, buf, bytes_read);
                bytes_read = 0;
            }
        } while(!end_reached);

        DEBUG("if_uart: finishing message to daemon...\n");
        int write_res = lora_daemon_write_done(daemon);
        if (write_res != 0) {
            DEBUG("if_uart: lora_daemon could not process the request\n");
        }

        /* Daemon -> UART */
        ssize_t read_res = 0;
        DEBUG("if_uart: reading result from daemon\n");
        _uart_write_byte(ESCSEQ_OBJ_START);
        do {
            read_res = lora_daemon_read(daemon, buf, sizeof(buf));
            if (read_res > 0) {
                DEBUG("if_uart: Writing %i bytes to UART\n", read_res);
                for (ssize_t i = 0; i < read_res; i++) {
                    _uart_write_byte(buf[i]);
                }
            }
        } while (read_res >= 0);
        _uart_write_byte(ESCSEQ_OBJ_END);

        lora_daemon_release(daemon);
        DEBUG("if_uart: Command done.\n");
    }
    return NULL;
}

static void _start(void)
{
    if (pid == KERNEL_PID_UNDEF && daemon != NULL) {
        memset(thread_stack, 0, sizeof(thread_stack));
        pid = thread_create(
            thread_stack,
            sizeof(thread_stack),
            THREAD_PRIORITY_MAIN - 1,
            0,
            _serial_thread,
            NULL,
            "if_uart"
        );
    }
}

static int _uart_read_byte(void)
{
    uint8_t b1 = 0;
    pipe_read(&pipe_in, &b1, 1);
    if (b1 == 0) {
        uint8_t b2 = 0;
        pipe_read(&pipe_in, &b2, 1);
        return (b2 > 0 ? 0x100 + ((int)b2) : 0);
    }
    return b1;
}

static void _uart_write_byte(int b)
{
    size_t seq_len = b > 0xff || b == 0 ? 2 : 1;
    uint8_t seq[seq_len];
    seq[0] = 0x00;
    seq[seq_len - 1] = b & 0xff;
    uart_write(dev_uart, seq, seq_len);
}

static void _rx_cb(void *arg, uint8_t data)
{
    (void)arg;
    DEBUG("if_uart: rx(0x%2x)\n", data);
    /* If the pipe is full, we cannot do anything here, so we ignore the return value */
    if (pipe_write(&pipe_in, &data, 1) == 0) {
        DEBUG("if_uart: RX buffer exhausted!\n");
    }
}

const lora_interface_t lora_interface_uart = {
    .init = _init,
    .start = _start,
};
