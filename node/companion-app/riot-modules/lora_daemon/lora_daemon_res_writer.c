#include "lora_daemon_res_writer.h"

#include <string.h>

#include "ubjson.h"

#define ENABLE_DEBUG (0)
#include "debug.h"

#define WRITE_FIELD_ARRAY(COOKIE,NAME,VAL,LEN) \
    ubjson_write_key(COOKIE, NAME, sizeof(NAME)-1); \
    _write_array(COOKIE,VAL,LEN)

#define WRITE_FIELD_BOOL(COOKIE,NAME,VAL) \
    ubjson_write_key(COOKIE, NAME, sizeof(NAME)-1); \
    ubjson_write_bool(COOKIE, VAL)

#define WRITE_FIELD_I32(COOKIE,NAME,VAL) \
    ubjson_write_key(COOKIE, NAME, sizeof(NAME)-1); \
    ubjson_write_i32(COOKIE, VAL)

#define WRITE_FIELD_I64(COOKIE,NAME,VAL) \
    ubjson_write_key(COOKIE, NAME, sizeof(NAME)-1); \
    ubjson_write_i64(COOKIE, VAL)

#define WRITE_FIELD_STR(COOKIE,NAME,VAL) \
    ubjson_write_key(COOKIE, NAME, sizeof(NAME)-1); \
    ubjson_write_string(COOKIE, VAL, strlen(VAL))

/**
 * Writes an array to the ubjson stream. Should be called after write_key within
 * the response object to write the array as value
 */
void _write_array(ubjson_cookie_t *cookie, const uint8_t *buf, size_t len);

/**
 * Write callback that pushed the data from the ubjson_write functions to the
 * response pipe
 */
ssize_t _write_callback(ubjson_cookie_t *cookie, const void *buf, size_t len);

void _write_res_error(ubjson_cookie_t *cookie, lora_daemon_res_t *res);
void _write_res_frame_data(ubjson_cookie_t *cookie, lora_daemon_res_t *res);
void _write_res_lora_channel(ubjson_cookie_t *cookie, lora_daemon_res_t *res);
void _write_res_preamble_length(ubjson_cookie_t *cookie, lora_daemon_res_t *res);
void _write_res_status(ubjson_cookie_t *cookie, lora_daemon_res_t *res);
void _write_res_time(ubjson_cookie_t *cookie, lora_daemon_res_t *res);
void _write_res_txcrc(ubjson_cookie_t *cookie, lora_daemon_res_t *res);

void lora_daemon_write_res(lora_daemon_t *daemon, lora_daemon_res_t *res)
{
    /* Determine the function to use and the name of the key in the response */
    void (*write_res_fun)(ubjson_cookie_t *cookie, lora_daemon_res_t *res);
    char *key = NULL;
    switch(res->type) {
        case LORA_DAEMON_RES_FRAME_DATA:
            key = "frame_data";
            write_res_fun = &_write_res_frame_data;
            break;
        case LORA_DAEMON_RES_LORA_CHANNEL:
            key = "lora_channel";
            write_res_fun = &_write_res_lora_channel;
            break;
        case LORA_DAEMON_RES_PREAMBLE_LENGTH:
            key = "preamble_length";
            write_res_fun = &_write_res_preamble_length;
            break;
        case LORA_DAEMON_RES_STATUS:
            key = "status";
            write_res_fun = &_write_res_status;
            break;
        case LORA_DAEMON_RES_TIME:
            key = "time";
            write_res_fun = &_write_res_time;
            break;
        case LORA_DAEMON_RES_TXCRC:
            key = "txcrc";
            write_res_fun = &_write_res_txcrc;
            break;
        case LORA_DAEMON_RES_ERROR:
            key = "error";
            write_res_fun = &_write_res_error;
            break;
    }

    /* Do the writing. Using the cookie from the daemon descriptor allows
     * calls to container_of later on */
    ubjson_cookie_t *cookie = &(daemon->ubjson_cookie);
    ubjson_write_init(cookie, _write_callback);
    ubjson_open_object(cookie);
    if (key != NULL) {
        ubjson_write_key(cookie, key, strlen(key));
        ubjson_open_object(cookie);
        (*write_res_fun)(cookie, res);
        ubjson_close_object(cookie);
    }
    ubjson_close_object(cookie);

    /* Wait for last read request and answer with STOP */
    msg_t msg, msg_stop;
    msg_receive(&msg);
    msg_stop.type = LORA_DAEMON_MTYPE_STOP;
    msg_reply(&msg, &msg_stop);
}

void _write_array(ubjson_cookie_t *cookie, const uint8_t *buf, size_t len)
{
    ubjson_open_array(cookie);
    for (size_t idx = 0; idx < len; idx++) {
        ubjson_write_i32(cookie, buf[idx]);
    }
    ubjson_close_array(cookie);
}

ssize_t _write_callback(ubjson_cookie_t *cookie, const void *buf, size_t len)
{
    (void)cookie;
    msg_t msg, msg_ack;
    size_t bytes_written = 0;
    lora_daemon_t *daemon = container_of(cookie, lora_daemon_t, ubjson_cookie);
    DEBUG("%s: _write_callback(%i bytes)\n", daemon->name, len);

    do {
        msg_receive(&msg);
        lora_daemon_msg_data_t *data = msg.content.ptr;
        if (data->size >= len - bytes_written) {
            /* Enough space to write the remaining message */
            memcpy(data->data, &(((uint8_t*)buf)[bytes_written]), len - bytes_written);
            data->size = len - bytes_written;
            bytes_written = len;
            DEBUG("%s: _write_callback could write all %i bytes\n", daemon->name, data->size);
        }
        else {
            /* Not enough space. Write as much as possible and wait for next msg */
            DEBUG("%s: _write_callback can only write %i bytes\n", daemon->name, data->size);
            memcpy(data->data, &(((uint8_t*)buf)[bytes_written]), data->size);
            bytes_written += data->size;
        }
        msg_ack.type = LORA_DAEMON_MTYPE_DATA_ACK;
        msg_reply(&msg, &msg_ack);
    } while(bytes_written < len);

    return len;
}

void _write_res_error(ubjson_cookie_t *cookie, lora_daemon_res_t *res)
{
    lora_daemon_res_error_t *error = &(res->data.error);
    WRITE_FIELD_STR(cookie, "message", error->message);
}


void _write_res_frame_data(ubjson_cookie_t *cookie, lora_daemon_res_t *res)
{
    lora_daemon_res_frame_data_t *fd = &(res->data.frame_data);
    lora_rx_stats_t *rx = &(fd->rx_stats);
    WRITE_FIELD_BOOL(cookie, "has_more", fd->has_more);
    WRITE_FIELD_BOOL(cookie, "frames_dropped", fd->frames_dropped);
    WRITE_FIELD_I32(cookie, "rssi", rx->rssi);
    WRITE_FIELD_I32(cookie, "snr", rx->snr);
    WRITE_FIELD_I64(cookie, "time_valid_header", rx->time_header);
    WRITE_FIELD_I64(cookie, "time_rxdone", rx->time_rxdone);
    WRITE_FIELD_BOOL(cookie, "crc_error", rx->crc_error);
    WRITE_FIELD_ARRAY(cookie, "payload", fd->payload, fd->length);
}

void _write_res_preamble_length(ubjson_cookie_t *cookie, lora_daemon_res_t *res)
{
    lora_daemon_res_preamble_length_t *preamble_length = &(res->data.preamble_length);
    WRITE_FIELD_I32(cookie, "len", preamble_length->len);
}

void _write_res_status(ubjson_cookie_t *cookie, lora_daemon_res_t *res)
{
    lora_daemon_res_status_t *status = &(res->data.status);
    WRITE_FIELD_STR(cookie, "message", status->message);
    WRITE_FIELD_I32(cookie, "code", status->code);
}

void _write_res_lora_channel(ubjson_cookie_t *cookie, lora_daemon_res_t *res)
{
    lora_daemon_res_lora_channel_t *channel = &(res->data.lora_channel);
    WRITE_FIELD_I32(cookie, "frequency", channel->frequency);
    WRITE_FIELD_I32(cookie, "bandwidth", channel->bandwidth);
    WRITE_FIELD_I32(cookie, "spreadingfactor", channel->spreading_factor);
    WRITE_FIELD_I32(cookie, "syncword", channel->syncword);
    WRITE_FIELD_I32(cookie, "codingrate", channel->coding_rate);
    WRITE_FIELD_BOOL(cookie, "invertiqtx", channel->invertiqtx);
    WRITE_FIELD_BOOL(cookie, "invertiqrx", channel->invertiqrx);
    WRITE_FIELD_BOOL(cookie, "explicitheader", channel->explicitheader);
}

void _write_res_time(ubjson_cookie_t *cookie, lora_daemon_res_t *res)
{
    lora_daemon_res_time_t *time = &(res->data.time);
    WRITE_FIELD_I64(cookie, "time", time->time);
}

void _write_res_txcrc(ubjson_cookie_t *cookie, lora_daemon_res_t *res)
{
    lora_daemon_res_txcrc_t *txcrc = &(res->data.txcrc);
    WRITE_FIELD_BOOL(cookie, "txcrc", txcrc->txcrc);
}
