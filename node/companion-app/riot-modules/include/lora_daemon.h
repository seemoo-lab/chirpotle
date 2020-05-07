#ifndef LORA_DAEMON_H
#define LORA_DAEMON_H

#include "mutex.h"
#include "thread.h"
#include "ubjson.h"

#include "lora_modem.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
    LORA_DAEMON_INIT_OK,
};


enum {
    /** Writing to the daemon worked */
    LORA_DAEMON_WRITE_OK,
    /** Writing to the daemon failed */
    LORA_DAEMON_WRITE_FAIL
};

typedef enum lora_daemon_state {
    /** Deamon isn't acquired and does nothing */
    LORA_DAEMON_STATE_IDLE,
    /** Daemon has just been acquired and should start parsing */
    LORA_DAEMON_STATE_START_PARSING,
    /** Daemon is currently parsing the UBJSON */
    LORA_DAEMON_STATE_PARSING,
    /** Run the command against lora_modem */
    LORA_DAEMON_STATE_RUN_CMD,
    /** Send the response object */
    LORA_DAEMON_STATE_SEND_RES,
    /** Handle request parsing failure */
    LORA_DAEMON_STATE_HANDLE_REQ_FAIL,
} lora_daemon_state_t;

typedef struct lora_daemon {
    /** The underlying modem */
    lora_modem_t *modem;
    /** Mutex that is locked when the daemon is acquired by a frontend */
    mutex_t mutex;
    /** PID of the daemon thread */
    kernel_pid_t thread_pid;
    /** name of the daemon */
    char name[16];
    /** Stack of the thread */
#if THREAD_STACKSIZE_LARGE > 2048
    char thread_stack[THREAD_STACKSIZE_LARGE + THREAD_EXTRA_STACKSIZE_PRINTF];
#else
    char thread_stack[3072 + THREAD_EXTRA_STACKSIZE_PRINTF];
#endif
    /** Current state of the daemon */
    volatile lora_daemon_state_t state;
    /** UBJson Cookie for command parsing (placing it here allows container_of to be used */
    ubjson_cookie_t ubjson_cookie;
    /** Pointer to current parser state (void* as it's internal to the module) */
    void *parser_state;
} lora_daemon_t;

/**
 * Initializes the daemon
 */
int lora_daemon_init(lora_daemon_t *daemon);

/**
 * Exclusively acquires the daemon, so that messages can be streamed to it
 */
void lora_daemon_acquire(lora_daemon_t *daemon);

/**
 * Releases the daemon
 */
void lora_daemon_release(lora_daemon_t *daemon);

/**
 * @brief Writes data to the input of the daemon
 *
 * The daemon has to be acquired first.
 *
 * Blocks until the data has been passed to the thread.
 *
 * @param[in]  daemon        Reference to the daemon
 * @param[in]  data          The bytes to write
 * @param[in]  length        Length of the data buffer
 *
 * @return     Bytes read from data. If the commands succeeds, it's equal to length
 */
ssize_t lora_daemon_write(lora_daemon_t *daemon, uint8_t *data, size_t length);

/**
 * @brief Tells the daemon that the input is complete
 *
 * @param[in]  daemon         Reference to the daemon
 *
 * @return LORA_DAEMON_WRITE_OK   The command is (syntactically) valid, a response can be created.
 * @return LORA_DAEMON_WRITE_FAIL The input was invalid
 */
int lora_daemon_write_done(lora_daemon_t *daemon);

/**
 * @brief Reads response data from the daemon
 *
 * The daemon has to be acuired first, and lora_daemon_write must have returned
 * LORA_DAEMON_WRITE_OK_CMD_BOUNDARY to be able to read data.
 *
 * @param[in]  daemon    The daemon to use
 * @param[out] buf       Buffer to write the response to
 * @param[in]  buf_size  Maximum usable size of the buffer buf
 *
 * @return     Actual amount of bytes written to buf.
 * @return     -1        If the end of the response has been reached
 */
ssize_t lora_daemon_read(lora_daemon_t *daemon, uint8_t *buf, size_t buf_size);

#ifdef __cplusplus
}
#endif

#endif /* LORA_DAEMON_H */