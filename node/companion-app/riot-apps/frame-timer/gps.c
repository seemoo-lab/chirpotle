#include "gps.h"

#include <stdio.h>
#include <string.h>
#include <time.h>

#include "periph/gpio.h"

#include "minmea.h"
#include "msg.h"
#include "thread.h"
#include "tsrb.h"
#include "xtimer.h"

#include "appconfig.h"

#define GPS_OFFSET_UTC      315964782

#define MTYPE_LINE_COMPLETE 0x01

/**
 * Read the current NMEA record into buf
 *
 * @param rec_len length of the current record in the uart buffer
 * @param buf     destination buffer
 * @param buf_len length of the destination buffer
 */
static void _fetch_record(size_t rec_len, char *buf, size_t buf_len);

/**
 * ISR for 1PPS puleses from the GPS module, gets PID of GPS thread as parameter
 */
static void _pps_cb(void *pid);

/**
 * Helper function to process an incoming RMC record
 */
static void _process_rmc(struct minmea_sentence_rmc *frame);

/**
 * ISR for incoming UART data, writes it into the linebuf
 */
static void _uart_cb(void *pid, uint8_t data);

/** Current line from UART, back for the tsrb */
static uint8_t linebuf[256];
/** UART input buffer */
static tsrb_t linebuf_tsrb = TSRB_INIT(linebuf);
/** Length of the current line */
static uint8_t linelen;

/** Current record */
static char record[MINMEA_MAX_LENGTH + 1];

/** GPS data */
static bool gps_valid = false;

/** Should records be dumped? */
static bool gps_dump = false;

/** Currently tracked sattelites */
static int gps_sattelites = 0;

/** GPS time */
static uint32_t gps_time = 0;

/** Last PPS pulse */
static uint64_t gps_last_pps = 0;

/** What happend last? PPS or RMC? */
static enum {
    EV_PPS = 1,
    EV_RMC = 2,
} gps_last_event = EV_PPS;

void gps_enable_dump(bool dump)
{
    gps_dump = dump;
}

uint64_t gps_local2gpstime(uint64_t localtime)
{
    int64_t diff = localtime-gps_last_pps;
    if (gps_last_event == EV_PPS) {
        /* The value in gps_time is for the previous pps pulse */
        diff += 1000000;
    }
    return ((uint64_t)gps_time) * 1000000lu + diff;
}

int gps_get_sattelites(void)
{
    return gps_sattelites;
}

bool gps_get_valid(void)
{
    return gps_valid;
}

uint32_t gps_get_time(void)
{
    return gps_time;
}

void *thread_gps(void *arg)
{
    bool module_configured = false;
    kernel_pid_t pid = thread_getpid();
    int init_res = uart_init(GPS_UART, GPS_BAUDRATE, _uart_cb, &pid);
    if (init_res != UART_OK) {
        printf("Could not initialize GPS, rc=%d\n", init_res);
        return NULL;
    }
    init_res = gpio_init_int(GPS_GPIO_PPS, GPIO_IN, GPIO_RISING, _pps_cb, &pid);
    if (init_res != 0) {
        printf("Could not initialize PPS ISR\n");
        return NULL;
    }

    while(true) {
        msg_t msg;
        msg_receive(&msg);
        if (msg.type == MTYPE_LINE_COMPLETE) {
            _fetch_record(msg.content.value, record, sizeof(record));
            if (gps_dump) {
                printf("GPS-NMEA: %s", record);
            }
            enum minmea_sentence_id type = minmea_sentence_id(record, false);
            if (type == MINMEA_SENTENCE_RMC) {
                struct minmea_sentence_rmc frame;
                if (minmea_parse_rmc(&frame, record)) {
                    _process_rmc(&frame);
                }
            }
            else if (type == MINMEA_SENTENCE_GGA) {
                struct minmea_sentence_gga frame;
                if (minmea_parse_gga(&frame, record)) {
                    gps_sattelites = frame.satellites_tracked;
                }
            }
            /* Wait until the first sentence is processed to be sure the modem
             * has started and is ready to process these command */
            if (!module_configured) {
                /* Configure the Quectel L80 to send NMEA records strictly after
                * the corresponding PPS pulse. */
                uart_write(GPS_UART, (const uint8_t*)"$PMTK255,1*2D\r\n",15);
                /* Turn PPS always on, with a 10 ms pulse width */
                uart_write(GPS_UART, (const uint8_t*)"$PMTK285,4,10*08\r\n",18);
                module_configured = true;
            }
        }
    }
    return arg;
}

static void _fetch_record(size_t rec_len, char *buf, size_t buf_len)
{
    rec_len = rec_len > buf_len -1 ? buf_len - 1 : rec_len;
    buf[rec_len] = 0;
    while(rec_len > 0) {
        size_t bytes_read = tsrb_get(&linebuf_tsrb, (uint8_t*)buf, rec_len);
        rec_len -= bytes_read;
        buf  += bytes_read;
    }
}

static void _pps_cb(void *pid)
{
    gps_last_pps = xtimer_now_usec64();
    gps_last_event = EV_PPS;
}

static void _process_rmc(struct minmea_sentence_rmc *rmc)
{
    gps_valid = rmc->valid;
    if (gps_valid) {
        struct timespec ts;
        if (minmea_gettime(&ts, &(rmc->date), &(rmc->time)) == 0) {
            gps_time = ts.tv_sec - GPS_OFFSET_UTC;
            gps_last_event = EV_RMC;
        }
    }
    else {
        gps_time = 0;
    }
}

static void _uart_cb(void *pid, uint8_t data)
{
    tsrb_add_one(&linebuf_tsrb, data);
    linelen++;
    if (data == '\n') {
        msg_t msg;
        msg.type = MTYPE_LINE_COMPLETE;
        msg.content.value = linelen;
        linelen = 0;
        msg_send_int(&msg, *((kernel_pid_t*)pid));
    }
}
