#ifndef LORA_DAEMON_INTERNAL_H
#define LORA_DAEMON_INTERNAL_H

#include "lora_modem.h"

#ifdef MODULE_LORA_MODEM_JAMMER_UDP
#include "net/ipv6.h"
#endif

enum {
    /** Request to abort the current action */
    LORA_DAEMON_MTYPE_ABORT = 0x0100,
    /** Generic data message */
    LORA_DAEMON_MTYPE_DATA,
    /** Data has been processed */
    LORA_DAEMON_MTYPE_DATA_ACK,
    /** Error during processing */
    LORA_DAEMON_MTYPE_DATA_ERR,
    /** Requests data input */
    LORA_DAEMON_MTYPE_DATA_REQ,
    /** Defines the end of a message / no more data to request */
    LORA_DAEMON_MTYPE_STOP,
    /** Starts the parser */
    LORA_DAEMON_MTYPE_START,
};


/** Maximum length of the error/status message returned by a daemon command */
#define LORA_DAEMON_RES_MSG_MAX_LENGTH 256

#ifdef __cplusplus
extern "C" {
#endif

/** Type of the request object */
typedef enum {
    /** Undefined command (used internally) */
    LORA_DAEMON_REQ_UNDEF,

    /** Configure rx/tx power */
    LORA_DAEMON_REQ_CONFIGURE_GAIN,

    /** Enable the externally controlled jammer */
    LORA_DAEMON_REQ_ENABLE_RC_JAMMER,

    /** Enable the sniffer */
    LORA_DAEMON_REQ_ENABLE_SNIFFER,

    /** Fetch the next frame from the receive buffer */
    LORA_DAEMON_REQ_FETCH_FRAME,

    /** Command to get the channel */
    LORA_DAEMON_REQ_GET_LORA_CHANNEL,

    /** Command to get the preamle length */
    LORA_DAEMON_REQ_GET_PREAMBLE_LENGTH,

    /** Command to get the current time */
    LORA_DAEMON_REQ_GET_TIME,

    /** Command to get the tx crc flag */
    LORA_DAEMON_REQ_GET_TXCRC,

    /** Command to set the length of the jamming frame */
    LORA_DAEMON_REQ_SET_JAMMER_PLENGTH,

    /** Command to set the channel */
    LORA_DAEMON_REQ_SET_LORA_CHANNEL,

    /** Command to set the preamle length */
    LORA_DAEMON_REQ_SET_PREAMBLE_LENGTH,

    /** Command to set the tx crc flag */
    LORA_DAEMON_REQ_SET_TXCRC,

    /** Command to enable the receive mode */
    LORA_DAEMON_REQ_RECEIVE,

    /** Command to set the modem to standby */
    LORA_DAEMON_REQ_STANDBY,

    /** Command to transmit a frame */
    LORA_DAEMON_REQ_TRANSMIT_FRAME,
} lora_daemon_reqtype_t;

/** Type of the response object */
typedef enum {
    /** Data for a previously received frame */
    LORA_DAEMON_RES_FRAME_DATA,

    /** Current channel information */
    LORA_DAEMON_RES_LORA_CHANNEL,

    /** Preamble length configuration */
    LORA_DAEMON_RES_PREAMBLE_LENGTH,

    /** Generic status message */
    LORA_DAEMON_RES_STATUS,

    /** Current time message */
    LORA_DAEMON_RES_TIME,

    /** Current tx CRC status */
    LORA_DAEMON_RES_TXCRC,

    /** If the request failed for some reason */
    LORA_DAEMON_RES_ERROR,
} lora_daemon_restype_t;

/** Request to enable the sniffer, which can act as trigger for the jammer */
typedef struct lora_daemon_enable_sniffer {
    /** Pattern to use when jamming */
    uint8_t pattern[LORA_DAEMON_SNIFFER_PATTERN_MAX_LENGTH];
    /** Mask to apply to the pattern when checking the jammer */
    uint8_t mask[LORA_DAEMON_SNIFFER_PATTERN_MAX_LENGTH];
    /** Length of the mask */
    size_t mask_length;
    /** If the jammer is external, should the frame be stored in the buffer? */
    bool rxbuf;
    /** Action that should be performed when the sniffer selects a frame to be jammed */
    lora_sniffer_action_t action;
#ifdef MODULE_LORA_MODEM_JAMMER_UDP
    /** Address to send the jammer trigger signal to (only if net is available) */
    ipv6_addr_t addr;
#endif
} lora_daemon_req_enable_sniffer_t;


/** Request to enable the sniffer, which can act as trigger for the jammer */
typedef struct lora_daemon_req_configure_gain {
    /** Level of gain to use */
    lora_lna_gain_t lna_gain;
    /** Whether the parameter was present in the request */
    bool lna_gain_set;

    /* Whether the LNA Boost should be activated */
    bool lna_boost;
    /** Whether the parameter was present in the request */
    bool lna_boost_set;

    /** Power for transmission */
    lora_pwr_out_t pwr_out;
    /** Whether the parameter was in the request */
    bool pwr_out_set;

} lora_daemon_req_configure_gain_t;

/** Request to enable the jammer that reacts to a signal by a sniffer */
typedef struct lora_daemon_req_enable_rc_jammer {
    /** Trigger that the jammer should react to */
    lora_jammer_trigger_t trigger;
} lora_daemon_req_enable_rc_jammer_t;

/** Request to fetch one frame from the frame buffer */
typedef struct lora_daemon_req_fetch_frame {
    /** Dummy, so that the struct isn't empty */
    uint8_t filler;
} lora_daemon_req_fetch_frame_t;

/** Request getting the current channel config */
typedef struct lora_daemon_req_get_lora_channel {
    /** Dummy, so that the struct isn't empty */
    uint8_t filler;
} lora_daemon_req_get_lora_channel_t;

/** Request getting the current time */
typedef struct lora_daemon_req_get_time {
    /** Dummy, so that the struct isn't empty */
    uint8_t filler;
} lora_daemon_req_get_time_t;

typedef struct lora_daemon_req_get_txcrc {
    uint8_t filler;
} lora_daemon_req_get_txcrc_t;

/** Request to start receiving */
typedef struct lora_daemon_req_receive {
    /** Dummy, so that the struct isn't empty */
    uint8_t filler;
} lora_daemon_req_receive_t;

/** Request to set the payload length of the jammer */
typedef struct lora_daemon_req_set_jammer_plength {
    /** Length to use */
    uint8_t length;
} lora_daemon_req_set_jammer_plength_t;

/** Request a change of the channel config */
typedef struct lora_daemon_req_set_lora_channel {
    /** Frequency, in Hz */
    uint32_t frequency;
    /** Whether the frequency was set in the request and should be changed */
    bool frequency_set;
    /** Bandwidth in kHz, only 125, 250 and 500 are valid */
    uint16_t bandwidth;
    /** Whether the bandwidth was set in the request and should be changed */
    bool bandwidth_set;
    /** Coding rate. from 4 -> 4/5 up to 8 -> 4/8 */
    uint8_t coding_rate;
    /** Whether the coding rate was set in the request and should be changed */
    bool coding_rate_set;
    /** Spreading factor from 6 to 12 */
    uint8_t spreading_factor;
    /** Whether the spreading factor was set in the request and should be changed */
    bool spreading_factor_set;
    /** LoRa syncword. 0x12 for private LoRaWAN networks, 0x34 for public ones */
    uint8_t syncword;
    /** Whether the syncword was set in the request and should be changed */
    bool syncword_set;
    /** Whether the rx signal should be inverted (true for beacons, false = default) */
    bool invertiqrx;
    /** Whether invertiqrx should be interpreted */
    bool invertiqrx_set;
    /** Whether the tx signal should be inverted (true for beacons, false = default) */
    bool invertiqtx;
    /** Whether invertiqtx should be interpreted */
    bool invertiqtx_set;
    /** Whether the modem should use explicit LoRa header */
    bool explicitheader;
    /** Whether the explicitheader field should be interpreted */
    bool explicitheader_set;
} lora_daemon_req_set_lora_channel_t;

/** Request to set the payload length of the jammer */
typedef struct lora_daemon_req_set_preamble_length {
    /** Length to use */
    uint16_t length;
} lora_daemon_req_set_preamble_length_t;

typedef struct lora_daemon_req_set_txcrc {
    /** Use CRC? */
    bool txcrc;
    /** Was the field set in the request */
    bool txcrc_set;
} lora_daemon_req_set_txcrc_t;

/** Request to go to standby */
typedef struct lora_daemon_req_standby {
    /** Dummy, so that the struct isn't empty */
    uint8_t filler;
} lora_daemon_req_standby_t;

/** Request getting the current channel config */
typedef struct lora_daemon_req_transmit_frame {
    /** The payload to transmit */
    uint8_t payload[LORA_PAYLOAD_MAX_LENGTH];
    /** Size of the payload */
    size_t length;
    /** The time to send the frame (microseconds from system start) */
    uint64_t time;
    /** True if the time field is used (otherwise: send immediate) */
    bool time_set;
    /** True if the call should wait for txdone */
    bool blocking;
} lora_daemon_req_transmit_frame_t;

/** Generic error object if the request failedc */
typedef struct lora_daemon_res_error {
    char message[LORA_DAEMON_RES_MSG_MAX_LENGTH];
} lora_daemon_res_error_t;

typedef struct lora_daemon_res_frame_data {
    /** Payload of the last frame */
    uint8_t payload[LORA_PAYLOAD_MAX_LENGTH];
    /** Length of the payload */
    size_t length;
    /** Whether there are more frames to retrieve */
    bool has_more;
    /** True, if frames had to be dropped in two consecutive fetch_frame calls */
    bool frames_dropped;
    /** RX stats for the frame */
    lora_rx_stats_t rx_stats;
} lora_daemon_res_frame_data_t;

typedef struct lora_daemon_res_preamble_length {
    /** Return value */
    uint16_t len;
} lora_daemon_res_preamble_length_t;

typedef struct lora_daemon_res_status {
    /** Message to return */
    char message[LORA_DAEMON_RES_MSG_MAX_LENGTH];
    /** Code to return */
    int code;
} lora_daemon_res_status_t;

typedef struct lora_daemon_res_time {
    /** Current system time in microseconds */
    uint64_t time;
} lora_daemon_res_time_t;

typedef struct lora_daemon_res_txcrc {
    /** Current system time in microseconds */
    bool txcrc;
} lora_daemon_res_txcrc_t;

/** Response object showing the currently configured channel */
typedef struct lora_daemon_res_lora_channel {
    /** Frequency, in Hz */
    uint32_t frequency;
    /** Bandwidth in kHz, only 125, 250 and 500 are valid */
    uint16_t bandwidth;
    /** Coding rate. from 4 -> 4/5 up to 8 -> 4/8 */
    uint8_t coding_rate;
    /** Spreading factor from 6 to 12 */
    uint8_t spreading_factor;
    /** LoRa syncword. 0x12 for private LoRaWAN networks, 0x34 for public ones */
    uint8_t syncword;
    /** Whether the rx signal should be inverted (true for beacons/downlinks) */
    bool invertiqrx;
    /** Whether the tx signal should be inverted (true for beacons/downlinks) */
    bool invertiqtx;
    /** Whether the modem should use explicit LoRa header */
    bool explicitheader;
} lora_daemon_res_lora_channel_t;

/** Generic structure for a request to the daemon */
typedef struct lora_daemon_req {
    /** Type of the request. Defines which of the union types to use */
    lora_daemon_reqtype_t type;

    union {
        lora_daemon_req_configure_gain_t configure_gain;
        lora_daemon_req_enable_rc_jammer_t enable_rc_jammer;
        lora_daemon_req_enable_sniffer_t enable_sniffer;
        lora_daemon_req_fetch_frame_t fetch_frame;
        lora_daemon_req_get_lora_channel_t get_lora_channel;
        lora_daemon_req_get_time_t get_time;
        lora_daemon_req_get_txcrc_t get_txcrc;
        lora_daemon_req_receive_t receive;
        lora_daemon_req_set_jammer_plength_t set_jammer_plength;
        lora_daemon_req_set_preamble_length_t set_preamble_length;
        lora_daemon_req_set_lora_channel_t set_lora_channel;
        lora_daemon_req_set_txcrc_t set_txcrc;
        lora_daemon_req_standby_t standby;
        lora_daemon_req_transmit_frame_t transmit_frame;
    } params;

} lora_daemon_req_t;

/** Generic structure for a response from the daemon */
typedef struct lora_daemon_res {
    /** Type of the response. Defines which of the union types to use */
    lora_daemon_restype_t type;

    union {
        lora_daemon_res_error_t error;
        lora_daemon_res_frame_data_t frame_data;
        lora_daemon_res_lora_channel_t lora_channel;
        lora_daemon_res_preamble_length_t preamble_length;
        lora_daemon_res_status_t status;
        lora_daemon_res_time_t time;
        lora_daemon_res_txcrc_t txcrc;
    } data;

} lora_daemon_res_t;

/** Message used internally to send data chunks between threads */
typedef struct lora_daemon_msg_data {
    /** The actual data */
    uint8_t *data;
    /** The size */
    size_t   size;
    /** The process to ack to. Data must be kept valid until ack is received */
    kernel_pid_t ack_to;
} lora_daemon_msg_data_t;

#ifdef __cplusplus
}
#endif

#endif