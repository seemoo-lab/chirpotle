#include "lora_if_stdio.h"

#include <string.h>
#include <stdio.h>

#include "stdio_base.h"

#include "pipe.h"
#include "ringbuffer.h"
#include "thread.h"

#include "lora_daemon.h"

#define ENABLE_DEBUG (0)
#include "debug.h"

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

/** The thread passing data from and to the daemon */
static void *_stdio_thread(void* arg);

/** Function to start this interface */
static void _start(void);

static void _stdio_write_byte(int b);
static int _stdio_read_byte(void);

static int _init(lora_daemon_t *d)
{
    daemon = d;
    return LORA_INTERFACE_SETUP_OK;
}

static void *_stdio_thread(void* arg)
{
    (void)arg;
    while(true) {
        /* Wait for start sequence */
        int b = _stdio_read_byte();
        while (ESCSEQ_OBJ_START != b) {
            /* Answer heartbeat */
            if (b == ESCSEQ_PING) {
                _stdio_write_byte(ESCSEQ_PONG);
            }
            b = _stdio_read_byte();
        }
        DEBUG("if_stdio: Command start.\n");
        lora_daemon_acquire(daemon);

        /* stdio -> Daemon */
        uint8_t buf[32] = { 0 };
        size_t bytes_read = 0;
        bool end_reached = false;
        do {
            int next_byte = _stdio_read_byte();
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

        DEBUG("if_stdio: finishing message to daemon...\n");
        int write_res = lora_daemon_write_done(daemon);
        if (write_res != 0) {
            DEBUG("if_stdio: lora_daemon could not process the request\n");
        }

        /* Daemon -> stdio */
        ssize_t read_res = 0;
        DEBUG("if_stdio: reading result from daemon\n");
        _stdio_write_byte(ESCSEQ_OBJ_START);
        do {
            read_res = lora_daemon_read(daemon, buf, sizeof(buf));
            if (read_res > 0) {
                DEBUG("if_stdio: Writing %i bytes to stdio\n", read_res);
                for (ssize_t i = 0; i < read_res; i++) {
                    _stdio_write_byte(buf[i]);
                }
            }
        } while (read_res >= 0);
        _stdio_write_byte(ESCSEQ_OBJ_END);

        lora_daemon_release(daemon);
        DEBUG("if_stdio: Command done.\n");
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
            _stdio_thread,
            NULL,
            "if_stdio"
        );
    }
}

static void _stdio_write_byte(int b)
{
    size_t seq_len = b > 0xff || b == 0 ? 2 : 1;
    uint8_t seq[seq_len];
    seq[0] = 0x00;
    seq[seq_len - 1] = b & 0xff;
    stdio_write(seq, seq_len);
}

static int _stdio_read_byte(void)
{
    uint8_t b1 = 0;
    stdio_read(&b1, 1);
    if (b1 == 0) {
        uint8_t b2 = 0;
        stdio_read(&b2, 1);
        return (b2 > 0 ? 0x100 + ((int)b2) : 0);
    }
    return b1;
}

const lora_interface_t lora_interface_stdio = {
    .init = _init,
    .start = _start,
};
