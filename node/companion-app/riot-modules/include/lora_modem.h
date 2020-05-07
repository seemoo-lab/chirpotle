#ifndef LORA_MODEM_H
#define LORA_MODEM_H

#include "mutex.h"
#include "periph/spi.h"
#include "ringbuffer.h"
#include "thread.h"
#include "xtimer.h"

/* Only include network stuff if that is required */
#ifdef MODULE_LORA_MODEM_JAMMER_UDP
#include "net/ipv6.h"
#endif

/* Only include GPIO if we have support for that */
#ifdef MODULE_PERIPH_GPIO
#include "periph/gpio.h"
#endif

#ifdef __cplusplus
extern "C" {
#endif

/** Size of the receive buffer in the lora_modem_t struct. Must be power of 2 */
#define LORA_RECEIVE_BUFFER_SIZE 1024

/** Size of the tx queue, in frames (each will take roughly 310 bytes) */
#define LORA_TRANSMIT_QUEUE_SIZE 3

/** Maximum length of lora payload */
#define LORA_PAYLOAD_MAX_LENGTH 255

/** Maximum length of pattern and mask for the sniffer */
#define LORA_DAEMON_SNIFFER_PATTERN_MAX_LENGTH 20

enum {
    /** Initialization of the modem did work, modem was recognized */
    LORA_MODEM_INIT_OK,
    /** Missing bus definition, cannot initalize the modem */
    LORA_MODEM_INIT_NODEV,
    /** No or unknown device on the bus */
    LORA_MODEM_INIT_UNKNOWNDEV,
};

enum {
    /**
     * Receiving a frame was successful
     */
    LORA_MODEM_RECEIVE_SUCCESS,
    /**
     * Receiving the message was successful, but the content had to be
     * truncated because the buffer was to small
     */
    LORA_MODEM_RECEIVE_SUCCESS_FRMTRUNCATED,
    /**
     * No frame was received
     */
    LORA_MODEM_RECEIVE_NOFRAME,
    /**
     * The TX queue is exhausted
     */
    LORA_MODEM_ERROR_TXQUEUE_FULL,
    /**
     * General SPI problem
     */
    LORA_MODEM_ERROR_SPI,
    /**
     * Unsupported sniffer action
     */
    LORA_MODEM_ERROR_UNSUPPORTED_SNIFFER_ACTION,
    /**
     * Unsupported remote trigger for the jammer
     */
    LORA_MODEM_ERROR_UNSUPPORTED_JAMMER_TRIGGER,
    /**
     * Command cannot be executed because it requires the modem to be in standby mode
     */
    LORA_MODEM_ERROR_COMMAND_REQUIRES_STANDBY,
};

#ifdef MODULE_PERIPH_GPIO
typedef enum {
    /** The GPIO isn't set up */
    DIO_MODE_UNUSED,
    /** The GPIO is set up, but cannot be used as irq pin */
    DIO_MODE_INPUT,
    /** The GPIO is set up as irq pin */
    DIO_MODE_IRQ,
} lora_dio_mode_t;
#endif

typedef enum {
    /** Undefined chip on the transceiver module */
    LORA_CHIP_UNKNOWN = 0,
    /** The chip is SX1272 or compatible */
    LORA_CHIP_SX1272  = 1,
    /** The chip is SX1276 or compatible */
    LORA_CHIP_SX1276  = 2,
} lora_modem_chip_t;

typedef enum {
    /** Modem is in sleep mode. Only mode that allows changing the modulation */
    LORA_OPMODE_SLEEP        = 0,
    /** Standby mode, configuration registers can be accessed */
    LORA_OPMODE_STANDBY      = 1,
    /** Frequency synthesis for TX */
    LORA_OPMODE_FSTX         = 2,
    /** Send out the frame currently configured in the buffer, that goto standby */
    LORA_OPMODE_TX           = 3,
    /** Frequency synthesis for RX */
    LORA_OPMODE_FSRX         = 4,
    /** Continuously receive frames and write them to the FIFO */
    LORA_OPMODE_RXCONTINUOUS = 5,
    /** Receive a single message and return to standby after success or timeout */
    LORA_OPMODE_RXSINGLE     = 6,
    /** Check for channel activity */
    LORA_OPMODE_CAD          = 7,
} lora_opmode_t;

typedef enum {
    /** Use LoRa as modulation */
    LORA_MODULATION_LORA,
    /** Use FSK as modulation */
    LORA_MODULATION_FSK,
} lora_modulation_t;

/**
 * Defines the bandwidth to use. The SX1272 is quite limited in bandwidths, so
 * the available options are currently limited to what both modems support
 */
typedef enum {
    LORA_BANDWIDTH_INVALID = -1,
    /** Use a bandwidth of 125 kHz */
    LORA_BANDWIDTH_125KHZ = 125,
    /** Use a bandwidth of 250 kHz */
    LORA_BANDWIDTH_250KHZ = 250,
    /** Use a bandwidth of 500 kHz */
    LORA_BANDWIDTH_500KHZ = 500,
} lora_bandwidth_t;

/** Defines the mode of forward error correction that should be used */
typedef enum {
    LORA_CODINGRATE_INVALID = -1,
    /** 4/5 coding, default for most of the LoRaWAN specification */
    LORA_CODINGRATE_4_5 = 5,
    /** 4/6 coding */
    LORA_CODINGRATE_4_6 = 6,
    /** 4/7 coding */
    LORA_CODINGRATE_4_7 = 7,
    /** 4/8 coding */
    LORA_CODINGRATE_4_8 = 8,
} lora_codingrate_t;

/** Defines the so-called spreading factor, which correlates to the data rate */
typedef enum {
    LORA_SF_INVALID = -1,
    /** Spreading Factor 6, unused in LoRaWAN */
    LORA_SF_6 = 6,
    /** Spreading Factor 7, highest data rate */
    LORA_SF_7 = 7,
    /** Spreading Factor 8 */
    LORA_SF_8 = 8,
    /** Spreading Factor 9 */
    LORA_SF_9 = 9,
    /** Spreading Factor 10 */
    LORA_SF_10 = 10,
    /** Spreading Factor 11 */
    LORA_SF_11 = 11,
    /** Spreading Factor 12, lowest data rate */
    LORA_SF_12 = 12,
} lora_sf_t;

/**
 * @brief LNA Gain (G1 = Max, G6 = Min)
 */
typedef enum {
    LORA_LNA_GAIN_G1 = 1,
    LORA_LNA_GAIN_G2 = 2,
    LORA_LNA_GAIN_G3 = 3,
    LORA_LNA_GAIN_G4 = 4,
    LORA_LNA_GAIN_G5 = 5,
    LORA_LNA_GAIN_G6 = 6,
} lora_lna_gain_t;

/** Abstract enum to define some levels of transmitter power */
typedef enum {
    LORA_PWR_OUT_0DBM = 0,
    LORA_PWR_OUT_5DBM = 5,
    LORA_PWR_OUT_10DBM = 10,
    LORA_PWR_OUT_15DBM = 15,
    /** Configure the maximum output power */
    LORA_PWR_OUT_MAX = 0xff,
} lora_pwr_out_t;

typedef struct lora_frame {
    /** Payload to send / received */
    uint8_t *payload;
    /** Length of the payload field */
    size_t length;
} lora_frame_t;

/** Contains reception indicators */
typedef struct lora_rx_stats {
    /** RSSI for the packet in dBm */
    int rssi;
    /** Signal to noise ratio */
    int snr;
    /** If true, the modem has detected a CRC error */
    bool crc_error;
    /** The time (in microseconds, since system start) when the header of the frame arrived */
    uint64_t time_header;
    /** The time (in microseconds, since system start) when the whole frame was processed */
    uint64_t time_rxdone;
} lora_rx_stats_t;

/** Function type for lora callbacks */
typedef void(* lora_irq_cb) (void *arg);

/** Contains the methods that should be called for a certain interrupt */
typedef struct lora_irq_config {
    volatile lora_irq_cb valid_header;
    volatile lora_irq_cb rx_done;
    volatile lora_irq_cb tx_done;
} lora_irq_config_t;

typedef struct lora_tx_queue_entry {
    /** Whether this entry is occupied */
    bool used;
    /** The frame data */
    uint8_t payload[LORA_PAYLOAD_MAX_LENGTH];
    /** Length of frame data */
    size_t length;
    /** Message struct that will be delivered to trigger transmission */
    msg_t msg;
    /** Timer entry required for scheduling */
    xtimer_t timer;
} lora_tx_queue_entry_t;

/** Currently active tasks, that e.g. need to be restored after a TX  */
typedef struct lora_modem_active_tasks {
    volatile bool rx;
    volatile bool tx;
    volatile bool sniffer;
    volatile bool jammer;
} lora_modem_active_tasks_t;

typedef enum {
    LORA_SNIFFER_ACTION_NONE = 0,
    LORA_SNIFFER_ACTION_INTERNAL = 1,
    LORA_SNIFFER_ACTION_GPIO = 2,
    LORA_SNIFFER_ACTION_UDP = 3,
} lora_sniffer_action_t;

typedef enum {
    LORA_JAMMER_TRIGGER_NONE = 0,
    LORA_JAMMER_TRIGGER_GPIO = 2,
    LORA_JAMMER_TRIGGER_UDP = 3,
} lora_jammer_trigger_t;

typedef struct lora_modem {
    /** The SPI bus that the modem is connected to */
    spi_t bus;
    /** The CS line that should be used for the modem */
    spi_cs_t cs;

#ifdef MODULE_PERIPH_GPIO
    /** GPIO that the CS pin is connected to */
    gpio_t gpio_reset;
    /** If true, the reset line is inverted, so the modem is in reset state on high */
    bool reset_on_high;
    /** GPIO for DIO0 (RxDone, TxDone, CADdone) */
    gpio_t gpio_dio0;
    /** Mode for the DIO0 pin */
    lora_dio_mode_t dio0_mode;
    /** GPIO for DIO3 (ValidHeader, PayloadCRCError, CADdone) */
    gpio_t gpio_dio3;
    /** Mode for the DIO3 pin */
    lora_dio_mode_t dio3_mode;
    /** GPIO output used by the sniffer to trigger external jammers */
    gpio_t gpio_sniffer;
    /** GPIO input used to trigger the jammer */
    gpio_t gpio_jammer;
#endif

    /** Value of the DIO_MAPPING1 register (used to determine which interrupt has fired) */
    volatile uint8_t dio_mapping1;
    /** Value of the DIO_MAPPING2 register (used to determine which interrupt has fired) */
    volatile uint8_t dio_mapping2;

    /**
     * If the board does not support hardware interrupts on GPIOs or the
     * interrupt lines of the transceiver aren't attached to a suitable port of
     * the board, the module will start a thread that either watches the GPIOs
     * or queries the IRQ register of the transceiver via SPI regularly. This
     * is the PID of that thread
     */
    kernel_pid_t irq_thread_pid;
    /** Stack for the optional irq_thread */
#if THREAD_STACKSIZE_LARGE > 2048
    char irq_thread_stack[THREAD_STACKSIZE_LARGE + THREAD_EXTRA_STACKSIZE_PRINTF];
#else
    char irq_thread_stack[2048 + THREAD_EXTRA_STACKSIZE_PRINTF];
#endif
    /** Name of the irq_thread */
    char irq_thread_name[16];
    /** Currently active tasks */
    lora_modem_active_tasks_t active_tasks;

    /**
     * The interrupt handler configuration. Used to dynamically assign
     * interrupts based on modem events. null pointer means nothing will be done
     */
    lora_irq_config_t irq_config;
    mutex_t mutex_irq_config;

    /** The chip that is connected to the line (will be set by lora_modem_init */
    lora_modem_chip_t chip_type;

    /** Backing buffer for ringbuf_recv. Don't access it directly */
    char buf_recv[LORA_RECEIVE_BUFFER_SIZE];
    /**
     * Ringbuffer that stores the received frames
     *
     * It is filled with an uint8_t denoting the payload size, followed by the
     * payload and finally an lora_rx_stats object for each frame.
     *
     * If the buffer isn't queued often enough, oldest frames will be dropped.
     *
     * Use mutex_ringbuf_recv!
     */
    ringbuffer_t ringbuf_recv;
    /** Mutes for ringbuf_recv */
    mutex_t mutex_ringbuf_recv;

    /** Whether frames have been dropped in reception mode */
    bool frames_dropped;
    /** Time of the last valid header interrupt */
    uint64_t t_valid_header;
    /** Time of the last rxdone interrupt */
    uint64_t t_rxdone;

    /** TX queue for scheduled frames */
    lora_tx_queue_entry_t tx_queue[LORA_TRANSMIT_QUEUE_SIZE];
    /** Mutes for ringbuf_recv */
    mutex_t mutex_tx_queue;
    /** PID to acknowledge a tx_done interrupt to */
    kernel_pid_t tx_done_ack_pid;
    /** Timer used time out waiting for tx done */
    xtimer_t tx_done_timer;

    /** Mask that defines which bits should be checked by the sniffer */
    uint8_t sniffer_mask[LORA_DAEMON_SNIFFER_PATTERN_MAX_LENGTH];
    /** Optimized pattern to select frames (optimized = already combined with the mask) */
    uint8_t sniffer_pattern[LORA_DAEMON_SNIFFER_PATTERN_MAX_LENGTH];
    /** Length (in bytes) that should be used for the sniffer */
    size_t sniffer_mask_len;
    /** Whether the sniffer should store received frames in the RX Buf */
    bool sniffer_to_rxbuf;
    /** Value of REG_FIFORXBYTEADDR after the last frame */
    volatile uint8_t lora_sniffer_last_rxbyteaddr;
    /**
     * When the isr got rxdone, this is set to true, so that the sniffer
     * doesn't miss it and keeps reading
     */
    volatile bool lora_sniffer_rxdone;
    /** Action to perform when the sniffer detects a frame that has to be jammed */
    volatile lora_sniffer_action_t sniffer_action;

    /** Current jammer trigger */
    volatile lora_jammer_trigger_t jammer_trigger;
    /** True if the modem is currently prepared for jamming (buffer filled & fstx) */
    volatile bool jammer_prepared;
    /** Payload length to use for the jammer */
    uint8_t jammer_plength;
    /** True while the jammer is active to debounce the trigger */
    volatile bool jammer_active;

    /** True, if a tx is prepared in the modem's FIFO */
    bool tx_prepared;

#ifdef MODULE_LORA_MODEM_JAMMER_UDP
    /** IPv6 to send the triggers to (from the sniffer) */
    uint8_t sniffer_addr[16];
    /** Network interface ID used for sendign */
    uint16_t sniffer_if;
    /** The PID of the udp jammer thread */
    kernel_pid_t udp_thread_pid;
    /** Stack for the optional irq_thread */
#if THREAD_STACKSIZE_MEDIUM > 2048
    char udp_thread_stack[THREAD_STACKSIZE_MEDIUM + THREAD_EXTRA_STACKSIZE_PRINTF];
#else
    char udp_thread_stack[2048 + THREAD_EXTRA_STACKSIZE_PRINTF];
#endif
#endif //def MODULE_LORA_MODEM_JAMMER_UDP

    /**
     * PID for the rx/tx thread.
     *
     * The TX thread gets woken by xtimer for queued messages and by the ISRs
     * when a frame arrives
     */
    kernel_pid_t modem_thread_pid;
    /** Stack for the modem_thread */
    char modem_thread_stack[THREAD_STACKSIZE_LARGE + THREAD_EXTRA_STACKSIZE_PRINTF];
    /** Name of the thread */
    char modem_thread_name[16];
} lora_modem_t;

typedef enum {
    /** RxDone interrupt */
    LORA_IRQ_RXDONE,
    /** TxDone interrupt */
    LORA_IRQ_TXDONE,
    /** Valid header interrupt */
    LORA_IRQ_VALID_HEADER,
    /** RxDone with the CRC-Fail interrupt included, the latter has no callback */
    LORA_IRQ_RXDONE_AND_CRC,
} lora_irq_t;

/**
 * Configures receiver gain and tx power.
 */
int lora_modem_configure_gain(lora_modem_t *modem,
    lora_lna_gain_t lna_gain, bool lna_boost,
    lora_pwr_out_t pwr_out_lvl);

/**
 * Enables the externally triggered jammer and configures the trigger type.
 *
 * @param[in]    modem          Modem descriptor
 * @param[in]    trigger        Trigger type
 * @return       0              Success
 * @return       LORA_MODEM_ERROR_UNSUPPORTED_JAMMER_TRIGGER Unsupported trigger type
 */
int lora_modem_enable_rc_jammer(lora_modem_t *modem, lora_jammer_trigger_t trigger);

/**
 * Enables the sniffer and configures optional actions when a frame arrives.
 *
 * @param[in]    modem          Modem descriptor
 * @param[in]    pattern        The pattern that must match in the frame
 * @param[in]    mask           The mask that is applied to the pattern (only high bits will be compared)
 * @param[in]    mask_len       Length of mask and pattern
 * @param[in]    rxbuf          Whether the frame should be appended to the rx buffer
 * @param[in]    action         The action that should be performed (action=internal -> rxbuf=false)
 * @param[in]    addr           The IPv6 to send the trigger signal to (only if networking is enabled)
 * @return       0              Success
 * @return       LORA_MODEM_ERROR_UNSUPPORTED_SNIFFER_ACTION Unsupported action type
 */
#ifdef MODULE_LORA_MODEM_JAMMER_UDP
int lora_modem_enable_sniffer(lora_modem_t *modem, uint8_t *pattern, uint8_t *mask,
    size_t mask_len, bool rxbuf, lora_sniffer_action_t action, ipv6_addr_t *addr);
#else
int lora_modem_enable_sniffer(lora_modem_t *modem, uint8_t *pattern, uint8_t *mask,
    size_t mask_len, bool rxbuf, lora_sniffer_action_t action);
#endif

/**
 * Returns the oldest frame from the modem's frame buffer and discards it from
 * that buffer.
 *
 * @param[in]    modem          Modem descriptor
 * @param[out]   payload        Buffer to write the frame into (expects length >=255)
 * @param[out]   rx_stats       Reception parameters for the frame
 * @param[out]   has_more       True iff there are already more frames available in the buffer
 * @param[out]   frames_dropped True iff frames have been dropped since the last call to fetch_frame
 * @return       >=0            Length of frame (valid data in payload buffer)
 * @return       -1             If there was no frame available
 */
ssize_t lora_modem_fetch_frame(lora_modem_t *modem, uint8_t *payload,
    lora_rx_stats_t *rx_stats, bool *has_more, bool *frames_dropped);
/**
 * @brief Initializes a lora_modem and checks if the connection works
 *
 * @param[inout] modem                 The modem to initialize. bus and cs
 *                                     fields have to be set
 * @return LORA_MODEM_INIT_OK          Initialization was successful
 * @return LORA_MODEM_INIT_NODEV       No device has been found
 * @return LORA_MODEM_INIT_UNKNOWNDEV  Invalid/Unknown device
 */
int lora_modem_init(lora_modem_t *modem);

lora_bandwidth_t lora_modem_get_bandwidth(lora_modem_t *modem);

lora_codingrate_t lora_modem_get_codingrate(lora_modem_t *modem);

/**
 * Returns whether the modem is configured to use inverted polarity while
 * receiving. The default is on, however, if you want to receive uplink frames,
 * you need to set it to false.
 *
 * @param[in] modem Modem descriptor
 * @return 0 Normal polarity (uplink frames)
 * @return 1 Inverted polarity (downlink frames and beacons, default)
 * @return -1 Error reading polarity
 */
int lora_modem_get_invertiqrx(lora_modem_t *modem);

/**
 * Returns whether the modem is configured to use inverted polarity for
 * transmission. It is turned off by default, however, if you want to spoof
 * beacons or downlink frames, you need to turn this on.
 *
 * @param[in] modem Modem descriptor
 * @return 0 Normal polarity (uplink frames, default)
 * @return 1 Inverted polarity (beacons or downlink frames)
 * @return -1 Error reading polarity
 */
int lora_modem_get_invertiqtx(lora_modem_t *modem);

int lora_modem_get_explicitheader(lora_modem_t *modem);

uint32_t lora_modem_get_frequency(lora_modem_t *modem);

int lora_modem_get_preamble_length(lora_modem_t *modem);

lora_sf_t lora_modem_get_sf(lora_modem_t *modem);

int lora_modem_get_syncword(lora_modem_t *modem);

int lora_modem_get_txcrc(lora_modem_t *modem);

/**
 * Prepares the transmission of a message so that it can be sent immediately
 * without any further preparation time.
 *
 * Cancels any other task on the modem, like calling lora_modem_standby().
 *
 * @param[in] modem Modem descriptor
 * @param[in] frame Payload
 * @return 0 success
 * @return !=0 failure
 */
int lora_modem_prepare_tx(lora_modem_t *modem, lora_frame_t *frame);

int lora_modem_receive(lora_modem_t *modem);

int lora_modem_set_bandwidth(lora_modem_t *modem, lora_bandwidth_t bw);

int lora_modem_set_codingrate(lora_modem_t *modem, lora_codingrate_t cr);

int lora_modem_set_explicitheader(lora_modem_t *modem, bool explicitheader);

int lora_modem_set_frequency(lora_modem_t *modem, uint32_t freq);

/**
 * Configures whether the modem is configured to use inverted polarity while
 * receiving. The default is on, however, if you want to receive uplink frames,
 * you need to set it to false.
 *
 * @param[in] modem Modem descriptor
 * @param[in] invertiq true, if polarity should be inverted
 * @return 0 success
 * @return !=0 failure
 */
int lora_modem_set_invertiqrx(lora_modem_t *modem, bool invertiq);

/**
 * Configures whether the modem is configured to use inverted polarity for
 * transmission. It is turned off by default, however, if you want to spoof
 * beacons or downlink frames, you need to turn this on.
 *
 * @param[in] modem Modem descriptor
 * @param[in] invertiq true, if polarity should be inverted
 * @return 0 success
 * @return !=0 failure
 */
int lora_modem_set_invertiqtx(lora_modem_t *modem, bool invertiq);

void lora_modem_set_jammer_plength(lora_modem_t *modem, uint8_t length);

int lora_modem_set_modulation(lora_modem_t *modem, lora_modulation_t mod);

int lora_modem_set_opmode(lora_modem_t *modem, lora_opmode_t opmode);

int lora_modem_set_preamble_length(lora_modem_t *modem, uint16_t length);

int lora_modem_set_sf(lora_modem_t *modem, lora_sf_t sf);

int lora_modem_set_syncword(lora_modem_t *modem, uint8_t syncword);

int lora_modem_set_txcrc(lora_modem_t *modem, bool txcrc);

int lora_modem_standby(lora_modem_t *modem);

/**
 * Schedules a frame for transmission
 *
 * @param[in] modem Modem descriptor
 * @param[in] frame Frame to schedule
 * @param[in] time  Time to send the frame (system time in microseconds), 0 for immediate transmission
 * @param[in] blocking If set to true (and time == 0), the call will block until tx is done
 * @return    0     If everything went well
 */
int lora_modem_transmit(lora_modem_t *modem, lora_frame_t *frame,
    uint64_t time, bool blocking);

/**
 * Transmits a previously prepared frame
 *
 * The modem must not be used for other actions between the calls to
 * lora_modem_prepare_tx and lora_modem_transmit_prepared.
 *
 * @param[in] modem The modem descriptor
 * @param[in] await The function will sleep until txdone
 * @return 0 on success
 */
int lora_modem_transmit_prepared(lora_modem_t *modem, bool await);

/** Dumps the content of the FIFO to stdout */
void lora_modem_dump_fifo(lora_modem_t *modem);

/** Dumps the content of modem registers to stdout */
void lora_modem_dump_regs(lora_modem_t *modem);

#ifdef __cplusplus
}
#endif

#endif /* LORA_MODEM_H */