#include "lora_daemon.h"

#include <string.h>

#include "msg.h"
#include "mutex.h"
#include "thread.h"

#include "lora_daemon_req_parser.h"
#include "lora_daemon_cmd_runner.h"
#include "lora_daemon_res_writer.h"
#include "lora_daemon_internal.h"

#define ENABLE_DEBUG (0)
#include "debug.h"

/** Counter to create unique thread names */
uint8_t _thread_counter = 0;

/**
 * Daemon thread main loop
 */
void *_daemon_thread(void *arg);

void *_daemon_thread(void *arg)
{
    lora_daemon_t *daemon = (lora_daemon_t*)arg;
    msg_t msg_queue[4];
    msg_init_queue(msg_queue, 4);

    lora_daemon_req_t req;
    lora_daemon_res_t res;

    while(true) {
        msg_t msg;
        switch(daemon->state) {
            case LORA_DAEMON_STATE_IDLE:
                msg_receive(&msg);
                if (msg.type == LORA_DAEMON_MTYPE_START) {
                    DEBUG("%s: waking up...\n", daemon->name);
                    daemon->state = msg.content.value;
                }
                break;
            case LORA_DAEMON_STATE_START_PARSING:
                daemon->state = LORA_DAEMON_STATE_PARSING;
                DEBUG("%s: -> STATE_PARSING\n", daemon->name);
                if (lora_daemon_parse_cmd(daemon, &req) == 0) {
                    daemon->state = LORA_DAEMON_STATE_RUN_CMD;
                    DEBUG("%s: -> STATE_RUN_CMD\n", daemon->name);
                }
                else {
                    daemon->state = LORA_DAEMON_STATE_HANDLE_REQ_FAIL;
                    DEBUG("%s: -> STATE_STATE_HANDLE_REQ_FAIL\n", daemon->name);
                }
                break;
            case LORA_DAEMON_STATE_RUN_CMD:
                lora_daemon_run_cmd(daemon, &req, &res);
                daemon->state = LORA_DAEMON_STATE_SEND_RES;
                DEBUG("%s: -> STATE_SEND_RES\n", daemon->name);
                break;
            case LORA_DAEMON_STATE_HANDLE_REQ_FAIL:
                res.type = LORA_DAEMON_RES_ERROR;
                strncpy(
                    res.data.error.message,
                    "Parsing request failed",
                    LORA_DAEMON_RES_MSG_MAX_LENGTH
                );
                daemon->state = LORA_DAEMON_STATE_SEND_RES;
                DEBUG("%s: -> STATE_SEND_RES\n", daemon->name);
                break;
            case LORA_DAEMON_STATE_SEND_RES:
                lora_daemon_write_res(daemon, &res);
                daemon->state = LORA_DAEMON_STATE_IDLE;
                DEBUG("%s: -> STATE_IDLE\n", daemon->name);
                break;
            case LORA_DAEMON_STATE_PARSING:
                UNREACHABLE();
                break;
        }

    }
}

int lora_daemon_init(lora_daemon_t *daemon)
{
    /** Initialize the struct */
    daemon->state = LORA_DAEMON_STATE_IDLE;

    /** Create the thread */
    memset(daemon->thread_stack, 0, sizeof(daemon->thread_stack));
    sprintf(daemon->name, "lora_daemon:%i", _thread_counter++);
    daemon->thread_pid = thread_create(
        daemon->thread_stack,
        sizeof(daemon->thread_stack),
        THREAD_PRIORITY_MAIN - 2,
        0,
        _daemon_thread,
        daemon,
        daemon->name
    );
    DEBUG("%s: -> STATE_IDLE\n", daemon->name);

    return LORA_DAEMON_INIT_OK;
}

void lora_daemon_acquire(lora_daemon_t *daemon)
{
    /* Lock the mutex to acquire exclusive access */
    mutex_lock(&(daemon->mutex));

    /* Start the parser */
    msg_t msg_start;
    msg_start.type = LORA_DAEMON_MTYPE_START;
    msg_start.content.value = LORA_DAEMON_STATE_START_PARSING;
    DEBUG("%s: -> STATE_START_PARSING\n", daemon->name);
    msg_send(&msg_start, daemon->thread_pid);
}

ssize_t lora_daemon_read(lora_daemon_t *daemon, uint8_t *buf, size_t buf_size)
{
    msg_t msg_req_data, msg_reply;
    lora_daemon_msg_data_t data = {
        .data = buf,
        .size = buf_size,
        .ack_to = KERNEL_PID_UNDEF,
    };
    msg_req_data.type = LORA_DAEMON_MTYPE_DATA_REQ;
    msg_req_data.content.ptr = &data;
    msg_send_receive(&msg_req_data, &msg_reply, daemon->thread_pid);
    if (msg_reply.type == LORA_DAEMON_MTYPE_DATA_ACK) {
        return data.size;
    }
    else {
        return -1;
    }
}

void lora_daemon_release(lora_daemon_t * daemon)
{
    /* Check that there is no parsing ongoing */
    if (daemon->state == LORA_DAEMON_STATE_PARSING) {
        msg_t msg_abort;
        msg_abort.type = LORA_DAEMON_MTYPE_ABORT;
        msg_send(&msg_abort, daemon->thread_pid);
        /* We can continue here safely. Even if the thread won't process the
         * message immediately, the next thing it will to is transitioning to
         * idle state, which is what when need to safely unlock the mutex */
    }

    /* This should not happen if the caller of lora_daemon_read takes care of
     * the return value. However, if not, we drain the buffer and return to IDLE */
    if (daemon->state == LORA_DAEMON_STATE_SEND_RES) {
        uint8_t buf[32];
        msg_t msg_read, msg_reply;
        msg_read.type = LORA_DAEMON_MTYPE_DATA_REQ;
        msg_reply.type = LORA_DAEMON_MTYPE_DATA_ACK;
        lora_daemon_msg_data_t data;
        msg_read.content.ptr = &data;
        do {
            data.data = buf;
            data.size = sizeof(buf);
            msg_send_receive(&msg_read, &msg_reply, daemon->thread_pid);
        } while (msg_reply.type == LORA_DAEMON_MTYPE_DATA_ACK);
    }

    /* Finally unlock the mutex to end the transaction */
    mutex_unlock(&(daemon->mutex));
}

ssize_t lora_daemon_write(lora_daemon_t *daemon, uint8_t *data, size_t length) {
    if (length == 0) {
        return 0;
    }
    /* Send data to the daemon */
    lora_daemon_msg_data_t msg_data = {
        .data = data,
        .size = length,
        .ack_to = thread_getpid(),
    };
    msg_t msg;
    msg.type = LORA_DAEMON_MTYPE_DATA;
    msg.content.ptr = &msg_data;
    msg_send(&msg, daemon->thread_pid);

    /* Sending data to the daemon either results in an ACK or FIN message.
     * Also, we need to block this thread to keep the data array valid until it is
     * processed by the other thread */
    DEBUG("%s: Waiting for ACK from request parser...\n", daemon->name);
    msg_receive(&msg);
    if (msg.type == LORA_DAEMON_MTYPE_DATA_ACK) {
        return length;
    }
    else {
        DEBUG("%s: Got message, but it's not the expected ACK from request parser\n",
            daemon->name);
    }
    return -1;
}

int lora_daemon_write_done(lora_daemon_t *daemon)
{
    msg_t msg_stop;
    msg_t msg_res;
    msg_stop.type = LORA_DAEMON_MTYPE_STOP;
    DEBUG("%s: Sending MTYPE_STOP to PID %" PRIkernel_pid "\n",
        daemon->name, daemon->thread_pid);
    msg_send_receive(&msg_stop, &msg_res, daemon->thread_pid);
    DEBUG("%s: Got answer from PID %" PRIkernel_pid ": 0x%x\n",
        daemon->name, daemon->thread_pid, msg_res.type);

    if (msg_res.type == LORA_DAEMON_MTYPE_DATA_ACK) {
        return LORA_DAEMON_WRITE_OK;
    }
    else {
        return LORA_DAEMON_WRITE_FAIL;
    }
}
