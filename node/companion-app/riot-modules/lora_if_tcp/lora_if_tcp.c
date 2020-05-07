#include "lora_if_tcp.h"

#include "mutex.h"
#include "net/af.h"
#include "net/gnrc/ipv6.h"
#include "net/gnrc/netif.h"
#include "net/gnrc/tcp.h"
#include "thread.h"

#include "lora_daemon.h"

#define ENABLE_DEBUG (0)
#include "debug.h"

#if ENABLE_DEBUG == 1
#define LOG_TCP_ERROR(fun,errno) do {char x[16];_tcp_errname(x,errno);DEBUG("if_tcp: " fun "(): %s\n",x);} while(0)
#else
#define LOG_TCP_ERROR(fun,errno) do {} while(0)
#endif

#define LORA_TCP_CONNECTION_TIMEOUT (21000000U) // Twice the heartbeat period and a bit = 21s

/** PID for the interface */
static kernel_pid_t pid = KERNEL_PID_UNDEF;

/** Stack for the interface thread */
static char thread_stack[THREAD_STACKSIZE_MEDIUM + THREAD_EXTRA_STACKSIZE_PRINTF];

/**
 * Buffer used to aggregate calls to gnrc_tcp_send. Without it, every single
 * entity created by ubjson will be sent in its own packet
 */
static uint8_t tcp_write_buf[128];
static size_t tcp_write_buf_idx;

/** The daemon to use */
static lora_daemon_t *dmn = NULL;

/** Initialization */
static int _init(lora_daemon_t *d);

/** Function to start this interface */
static void _start(void);

#if ENABLE_DEBUG == 1
/**
 * Writes the error name for errno into str (str should have a length of 16)
 *
 * Used for the LOG_TCP_ERROR macro.
 */
static void _tcp_errname(char *str, int no);
#endif

/**
 * Flushes the internal TCP buffer down to the network stack
 *
 * @param[in]    tcb    Transmission control block to use
 * @return       >=0    Amount of bytes flushed
 * @return       <0     Error, like gnrc_tcp_send
 */
ssize_t _tcp_flush_buffered(gnrc_tcp_tcb_t *tcb);

/**
 * Adds data to the internal TCP buffer. If the data does not fit, the buffer
 * will be flushed until everything is sent.
 *
 * You need to call _tcp_flush_buffered after a transmission if you want to
 * force data to the client.
 *
 * @param[in]     tcb      Transmission Control Block to use
 * @param[in]     data_in  Data to add to the buffer
 * @param[in]     len_in   Length of the input data
 * @return        >=0      Amount of bytes added to the buffer/sent
 * @return        <0       Error, like gnrc_tcp_send
 */
ssize_t _tcp_write_buffered(gnrc_tcp_tcb_t *tcb, const void *data_in, const size_t len_in);

/**
 * Reads the next data byte of the TCP stream
 *
 * @param[in]    tcb     The transmission control block
 * @return       0-255   Data
 * @return       <0      Error
 * @return       >255    Escape sequence
 */
static int _tcp_read_byte(gnrc_tcp_tcb_t *tcb);

/**
 * Function that awaits an incoming the TCP connection
 *
 * Returns 0 if the connection has been established successfully
 */
static int _tcp_await_connection(gnrc_tcp_tcb_t *tcb);

/** The TCP thread function */
static void *_tcp_thread(void *arg);

/**
 * Writes bytes to the stream and escapes them if necessary (0x00 -> 0x00 0x00)
 *
 * @param[in]    tcb     The transmission control block
 * @param[in]    in_buf  The buffer containing the unescaped data
 * @param[in]    in_len  Length of the buffer
 * @return       >=0     Bytes written (always ==in_len, if the call succeeds)
 * @return       < 0     Error code (like for gnrc_tcp_send)
 */
ssize_t _tcp_write_and_escape(gnrc_tcp_tcb_t *tcb, uint8_t *in_buf, size_t in_len);

/**
 * Writes a single, unescaped byte to the stream. May be used to send escape sequences as well
 *
 * @param[in]    tcb     The transmission control block
 * @param[in]    b       The byte to send (or ESCSEQ_...)
 * @return       0       Success
 * @return       <0      Error code (like for gnrc_tcp_send)
 */
ssize_t _tcp_write_byte(gnrc_tcp_tcb_t *tcb, int b);

static int _init(lora_daemon_t *d) {
    dmn = d;
    tcp_write_buf_idx = 0;
    memset(tcp_write_buf, 0, sizeof(tcp_write_buf));
    return LORA_INTERFACE_SETUP_OK;
}

static void _start(void) {
    if (pid == KERNEL_PID_UNDEF) {
        memset(thread_stack, 0, sizeof(thread_stack));
        pid = thread_create(
            thread_stack,
            sizeof(thread_stack),
            THREAD_PRIORITY_MAIN - 1,
            0,
            _tcp_thread,
            NULL,
            "if_tcp"
        );
    }
}

static int _tcp_await_connection(gnrc_tcp_tcb_t *tcb)
{
    /** Re-initialize the TCB */
    gnrc_tcp_tcb_init(tcb);
    DEBUG("if_tcp: _tcp_await_connection: Calling gnrc_tcp_open_passive...\n");
    int res = gnrc_tcp_open_passive(tcb, AF_INET6, NULL, LORA_TCP_DAEMON_PORT);
    LOG_TCP_ERROR("_tcp_await_connection", res);
    return res;
}

#if ENABLE_DEBUG == 1
static void _tcp_errname(char* str, int no)
{
    memset(str, 0, 16);
    no = no > 0 ? no : -no;
    switch(no) {
        case 0:
            strcpy(str, "ok");
            break;
        case ETIMEDOUT:
            strcpy(str, "ETIMEDOUT");
            break;
        case EISCONN:
            strcpy(str, "EISCONN");
            break;
        case EINVAL:
            strcpy(str, "EINVAL");
            break;
        case EAFNOSUPPORT:
            strcpy(str, "EAFNOSUPPORT");
            break;
        case ENOMEM:
            strcpy(str, "ENOMEM");
            break;
        case ECONNRESET:
            strcpy(str, "ECONNRESET");
            break;
        case ECONNABORTED:
            strcpy(str, "ECONNABORTED");
            break;
        case ENOTCONN:
            strcpy(str, "ENOTCONN");
            break;
        default:
            sprintf(str, "UNKNOW(%d)", errno);
    }
}
#endif

ssize_t _tcp_flush_buffered(gnrc_tcp_tcb_t *tcb)
{
    size_t written_idx = 0;
    do {
        ssize_t res = gnrc_tcp_send(tcb, &(tcp_write_buf[written_idx]),
            tcp_write_buf_idx - written_idx, 0);
        if (res < 0) {
            LOG_TCP_ERROR("_tcp_flush_buffered", res);
            return res;
        }
        DEBUG("if_tcp: TCP send buffer: %d bytes flushed\n", res);
        written_idx += res;
    } while(written_idx < tcp_write_buf_idx);
    tcp_write_buf_idx = 0;
    return written_idx;
}

static int _tcp_read_byte(gnrc_tcp_tcb_t *tcb)
{
    uint8_t b = 0;
    ssize_t res = gnrc_tcp_recv(tcb, &b, 1, LORA_TCP_CONNECTION_TIMEOUT);
    if (res < 0) {
        LOG_TCP_ERROR("_tcp_read_byte", res);
        return res;
    }
    if (b != 0) {
        DEBUG("if_tcp: Got data byte: 0x%02x\n", b);
        return b;
    }
    res = gnrc_tcp_recv(tcb, &b, 1, LORA_TCP_CONNECTION_TIMEOUT);
    if (res < 0) {
        LOG_TCP_ERROR("_tcp_read_byte", res);
        return res;
    }
    switch(b) {
        case 0:
            return 0;
        case 1:
            DEBUG("if_tcp: Got ESCSEQ_OBJ_START\n");
            return ESCSEQ_OBJ_START;
        case 2:
            DEBUG("if_tcp: Got ESCSEQ_OBJ_END\n");
            return ESCSEQ_OBJ_END;
        case 3:
            DEBUG("if_tcp: Got ESCSEQ_PING\n");
            return ESCSEQ_PING;
        default:
            return -1;
    }
}

static void *_tcp_thread(void *arg)
{
    (void)arg;

    /** Flag that states that this thread is still running */
    bool running = true;

    /* Transmission control block */
    gnrc_tcp_tcb_t tcb;

    DEBUG("if_tcp: Thread started, will be listening on port %d\n", LORA_TCP_DAEMON_PORT);

    while (running) {
        /* Listen for incoming connection */
        if (_tcp_await_connection(&tcb) != 0) {
            running = false;
            DEBUG("if_tcp: Could not create connection.\n");
            break;
        }

        /* The client may send an arbitrary amount of commands while being connected */
        bool connected = true;
        bool acquired = false;
        while (connected) {
            /* Wait for a "obj_start" flag (\x00\x01) in the stream */
            int b = _tcp_read_byte(&tcb);
            while (b >= 0 && b != ESCSEQ_OBJ_START) {
                if (b == ESCSEQ_PING) {
                    _tcp_write_byte(&tcb, ESCSEQ_PONG);
                    _tcp_flush_buffered(&tcb);
                }
                b = _tcp_read_byte(&tcb);
            }
            if (b != ESCSEQ_OBJ_START) {
                connected = false;
                continue;
            }

            DEBUG("if_tcp: Acquiring daemon.\n");
            lora_daemon_acquire(dmn);
            acquired = true;

            /** Read command and write it to the daemon */
            uint8_t buf[128];
            int next_byte = _tcp_read_byte(&tcb);
            size_t buf_pos = 0;
            while(next_byte >= 0x00 && next_byte < 0x100) {
                buf[buf_pos++] = next_byte;
                if (buf_pos >= sizeof(buf)) {
                    DEBUG("if_tcp: Writing %d bytes to daemon\n", buf_pos);
                    lora_daemon_write(dmn, buf, sizeof(buf));
                    buf_pos = 0;
                }
                next_byte = _tcp_read_byte(&tcb);
            }
            if (next_byte < 0 || next_byte != ESCSEQ_OBJ_END) {
                connected = false;
                continue;
            }
            if (buf_pos > 0) {
                DEBUG("if_tcp: Writing %d bytes to daemon\n", buf_pos);
                lora_daemon_write(dmn, buf, buf_pos);
            }
            DEBUG("if_tcp: Terminating command\n");
            int write_res = lora_daemon_write_done(dmn);
            if (write_res == LORA_DAEMON_WRITE_FAIL) {
                DEBUG("if_tcp: Invalid command\n");
                connected = false;
                continue;
            }
            DEBUG("if_tcp: Daemon done, sending response\n");

            /* Write response */
            if (_tcp_write_byte(&tcb, ESCSEQ_OBJ_START) != 0) {
                connected = false;
                continue;
            }
            ssize_t bytes_read = 0;
            write_res = 0;
            do {
                bytes_read = lora_daemon_read(dmn, buf, sizeof(buf));
                if (bytes_read > 0) {
                    write_res = _tcp_write_and_escape(&tcb, buf, bytes_read);
                }
            } while(bytes_read >= 0 && write_res >= 0);
            lora_daemon_release(dmn);
            acquired = false;
            if (write_res < 0 ||
                _tcp_write_byte(&tcb, ESCSEQ_OBJ_END) != 0 ||
                _tcp_flush_buffered(&tcb) < 0) {
                connected = false;
            }
        } /* while (connected) */
        if (acquired) {
            lora_daemon_release(dmn);
        }

        gnrc_tcp_close(&tcb);
    } /* while running */

    return NULL;
}


ssize_t _tcp_write_and_escape(gnrc_tcp_tcb_t *tcb, uint8_t *in_buf, size_t in_len)
{
    /* Count the bytes that have to be escaped: 0x00 -> 0x00 0x00 */
    size_t out_len = in_len;
    for (size_t n = 0; n < in_len; n++) {
        if (in_buf[n] == 0) {
            out_len += 1;
        }
    }
    /* Write escaped data to a new buffer */
    uint8_t out_buf[out_len];
    size_t out_idx = 0;
    for (size_t in_idx = 0; in_idx < in_len; in_idx++) {
        uint8_t in = in_buf[in_idx];
        if (in == 0) {
            out_buf[out_idx++] = 0;
        }
        out_buf[out_idx++] = in;
    }
    /* Send data via TCP */
    out_idx = 0;
    do {
        ssize_t res = _tcp_write_buffered(tcb, &(out_buf[out_idx]), out_len-out_idx);
        if (res >= 0) {
            out_idx += res;
        }
        else {
            LOG_TCP_ERROR("_tcp_write_and_escape", res);
            return res;
        }
    } while (out_idx < out_len);
    return in_len;
}

ssize_t _tcp_write_buffered(gnrc_tcp_tcb_t *tcb, const void *data_in, const size_t len_in)
{
    size_t idx_in = 0;
    while (idx_in < len_in) {
        /* Fill as much as possible in the buffer */
        size_t bytes_avail_buf = sizeof(tcp_write_buf) - tcp_write_buf_idx;
        size_t bytes_remain_input = len_in - idx_in;
        size_t bytes_to_write = bytes_avail_buf >= bytes_remain_input ?
            bytes_remain_input : bytes_avail_buf;
        memcpy(&(tcp_write_buf[tcp_write_buf_idx]),
            &(((uint8_t*)data_in)[idx_in]), bytes_to_write);
        DEBUG("if_tcp: TCP send buffer usage: %4d of %4d\n",
            tcp_write_buf_idx, sizeof(tcp_write_buf));
        idx_in += bytes_to_write;
        tcp_write_buf_idx += bytes_to_write;

        /* If the buffer is full, flush */
        if (tcp_write_buf_idx == sizeof(tcp_write_buf)) {
            ssize_t res = _tcp_flush_buffered(tcb);
            if (res < 0) {
                return res;
            }
        }
    }
    return idx_in;
}

ssize_t _tcp_write_byte(gnrc_tcp_tcb_t *tcb, int b)
{
    size_t len = b > 0xff ? 2 : 1;
    uint8_t buf[len];
    buf[0] = 0;
    buf[len-1] = (uint8_t)(b & 0xff);
    if (_tcp_write_buffered(tcb, buf, len) < 0) {
        return -1;
    }
    return 0;
}

const lora_interface_t lora_interface_tcp = {
    .init = _init,
    .start = _start,
};
