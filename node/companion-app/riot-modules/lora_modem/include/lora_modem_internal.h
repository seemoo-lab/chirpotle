#ifndef LORA_MODEM_INTERNAL_H
#define LORA_MODEM_INTERNAL_H
/*
 * All functions in this file are meant to be used by the modem internally, as
 * they do not aquire the bus, but are more or less the building blocks for the
 * SPI transactions on a higher level
 */

/** Port used for jammer signalling */
#define UDP_JAMMER_PORT (9001)

#ifdef __cplusplus
extern "C" {
#endif

#include "periph/spi.h"

#include "lora_modem.h"

#define SPI_ACQUIRE(m) spi_acquire(m->bus, m->cs, SPI_MODE_0, SPI_CLK_5MHZ)
#define SPI_RELEASE(m) spi_release(m->bus)

#define ENABLE_DEBUG_MODEM_ALL (0)

enum {
    /**
     * Send by the scheduler to inform the tx thread that a message has
     * to be transmitted now. Content is the index of the message in the tx queue
     */
    LORAMODEM_MTYPE_TXSCHED = 0x200,
    /**
     * Used to stop a thread
     */
    LORAMODEM_MTPYE_STOPTHREAD,
    /**
     * Used to signal a valid header interrupt so the sniffer starts
     */
    LORAMODEM_MTYPE_SIGNAL_SNIFFER,
    /**
     * Used to trigger the jammer
     */
    LORAMODEM_MTYPE_TRIGGER_JAMMER,
    /**
     * Handle rx_done event and store message in buffer
     */
    LORAMODEM_MTYPE_FRAME_TO_BUF,
    /**
     * Restore the modem state after a transmission
     */
    LORAMODEM_MTYPE_TX_RESTORE,
    /**
     * Transmit a prepared message based on a GPIO trigger
     */
    LORAMODEM_MTYPE_TRIGGER_MESSAGE,
};

/**
 * @brief Calculates the symbol time in microseconds
 * @param[in]    sf Spreading factor for the calculation
 * @param[in]    bw Bandwidth for the calculation
 * @return       Symbol time in microseconds
 */
uint32_t lm_calc_symboltime(lora_sf_t sf, lora_bandwidth_t bw);

/**
 * @brief Queries the bandwidth of the LoRa modem
 * @param[in]    modem    Modem descriptor
 * @return       The modem's current bandwidth
 */
lora_bandwidth_t lm_get_bandwidth(lora_modem_t *modem);

/**
 * @brief Queries the coding rate of the LoRa modem
 * @param[in]    modem    Modem descriptor
 * @return       The modem's current coding rate
 */
lora_codingrate_t lm_get_codingrate(lora_modem_t *modem);

/**
 * @brief Returns whether the modem is in explicit header mode
 */
bool lm_get_explicitheader(lora_modem_t *modem);

/**
 * @brief Queries the frequency of the LoRa modem
 * @param[in]    modem    Modem descriptor
 * @return       The modem's current frequency in Hz
 */
uint32_t lm_get_frequency(lora_modem_t *modem);

/**
 * @brief Returns the opmode of the modem
 * @param[in]    modem    Modem descriptor
 * @return       Current opmode
 */
lora_opmode_t lm_get_opmode(lora_modem_t *modem);

/**
 * @brief Queries the spreading factor of the LoRa modem
 * @param[in]    modem    Modem descriptor
 * @return       The modem's current spreading factor
 */
lora_sf_t lm_get_sf(lora_modem_t *modem);

/**
 * @brief Queries the syncword of the LoRa modem
 * @param[in]    modem    Modem descriptor
 * @return       The modem's current syncword
 */
uint8_t lm_get_syncword(lora_modem_t *modem);


/**
 * @brief Reads modem register at address
 * @param[in]    modem    Modem descriptor
 * @param[in]    address  Address to read
 * @return       The value of that register
 */
uint8_t lm_read_reg(lora_modem_t *modem, uint8_t address);

/**
 * @brief Reads a modem register and applies the given mask to its value before returning
 *
 * @param[in]    modem    Modem descriptor
 * @param[in]    address  Address of the register to write
 * @param[in]    mask     Bitmask for bits that should be modified
 * @return       Value of the register masked with mask (but not shifted)
 */
uint8_t lm_read_reg_masked(lora_modem_t *modem, uint8_t address, uint8_t mask);

void lm_read_reg_burst(lora_modem_t *modem, uint8_t address,
        uint8_t *data, size_t length);

/**
 * @brief Writes value to address of modem, returns former value of that register
 * @param[in]    modem    Modem descriptor
 * @param[in]    address  Address of the register to write
 * @param[in]    value    The new value for that register
 * @return       The previous value of that register
 */
uint8_t lm_write_reg(lora_modem_t *modem, uint8_t address, uint8_t value);

/**
 * @brief Writes multiple bytes to a register (group)
 * @param[in]    modem    Modem descriptor
 * @param[in]    address  (Start) address of the register (group)
 * @param[in]    data     The data to write to the register (group)
 * @param[in]    length   Length of the data paramter
 * @return       The previous value of that register
 */
void lm_write_reg_burst(lora_modem_t *modem, uint8_t address,
        uint8_t *data, size_t length);


/**
 * @brief Writes value to address of modem, returns former value of that register
 *
 * Only the bits that are set in mask are modified.
 *
 * @param[in]    modem    Modem descriptor
 * @param[in]    address  Address of the register to write
 * @param[in]    mask     Bitmask for bits that should be modified
 * @param[in]    value    The new value for that register (already shifted to mask)
 * @return       The previous value of the masked bits
 */
uint8_t lm_write_reg_masked(lora_modem_t *modem, uint8_t address,
        uint8_t mask, uint8_t value);

/**
 * @brief Resets the modem
 *
 * NOOP if gpio_reset of the descriptor isn't set or GPIO aren't available.
 *
 * @param[in]    modem    Modem descriptor
 */
void lm_reset(lora_modem_t *modem);

/**
 * Returns whether the modem is configured to use inverted polarity for receiving
 * (default: off (as used for uplinks), set to true to spoof downlinks or beacons)
 *
 * @param[in]    modem    Modem descriptor
 */
bool lm_get_invertiqrx(lora_modem_t *modem);

/**
 * Returns whether the modem is configured to use inverted polarity for receiving
 * (default: on (as used for downlinks or beacons), set to true to spoof uplinks)
 *
 * @param[in]    modem    Modem descriptor
 */
bool lm_get_invertiqtx(lora_modem_t *modem);

/**
 * @brief Returns the current RSSI in in dBm
 * @param[in]    modem    Modem descriptor
 */
int lm_get_rssi(lora_modem_t *modem);

/**
 * @brief Returns the latest packet's RSSI in in dBm and the SNR
 * @param[in]    modem    Modem descriptor
 * @param[inout] stats    The stats to write the values to
 */
void lm_get_rx_stats(lora_modem_t *modem, lora_rx_stats_t *stats);

/**
 * @brief Returns whether phy CRC is enabled on payload for tx
 */
bool lm_get_txcrc(lora_modem_t *modem);

/**
 * @brief Configures auto gain control
 *
 * Modem needs to be in sleep or standby first
 *
 * @param[in]    modem    Modem descriptor
 * @param[in]    freq     State for AGC
 */
void lm_set_agc_autoon(lora_modem_t *modem, bool on);

/**
 * @brief Configure the bandwidth
 *
 * Modem needs to be in sleep or standby first
 *
 * @param[in]    modem    Modem descriptor
 * @param[in]    freq     Bandwidth
 */
void lm_set_bandwidth(lora_modem_t *modem, lora_bandwidth_t bw);

/**
 * @brief Configure the coding rate for sending/implicit header messages
 *
 * Modem needs to be in sleep or standby first
 *
 * @param[in]    modem    Modem descriptor
 * @param[in]    freq     Coding rate
 */
void lm_set_codingrate(lora_modem_t *modem, lora_codingrate_t cr);

/**
 * @brief Sets the modem to explicit header mode
 */
void lm_set_explicitheader(lora_modem_t *modem, bool explicitheader);

/**
 * @brief Configure the frequency
 *
 * Modem needs to be in sleep or standby first
 *
 * @param[in]    modem    Modem descriptor
 * @param[in]    freq     Frequency in Hz
 */
void lm_set_frequency(lora_modem_t *modem, uint32_t freq);

/**
 * @brief Set frequency hopping period
 * @param[in]    modem      Modem descriptor
 * @param[in]    hop_period Period (in symbols) between channel hops. 0=off
 */
void lm_set_hop_period(lora_modem_t *modem, uint8_t hop_period);

/**
 * Convigures whether the modem will used inverted polarity for receiving.
 *
 * The default (as for downlink frames in LoRaWAN) is on. If you want to
 * receive uplink frames, set it to false.
 *
 * @param[in]    modem    Modem descriptor
 * @param[in]    invertiq true, if rx polarity should be inverted
 */
void lm_set_invertiqrx(lora_modem_t *modem, bool invertiq);

/**
 * Convigures whether the modem will used inverted polarity for transmission.
 *
 * The default (as for uplink frames in LoRaWAN) is off. If you want to spoof
 * downlink frames or beacons, set it to true.
 *
 * @param[in]    modem    Modem descriptor
 * @param[in]    invertiq true, if tx polarity should be inverted
 */
void lm_set_invertiqtx(lora_modem_t *modem, bool invertiq);

/**
 * @brief Configure the LNA gain
 * @param[in]    modem    Modem descriptor
 * @param[in]    gain     Gain value to use
 * @param[in]    boost    Enable boost with 150% LNA current
 */
void lm_set_lna(lora_modem_t *modem, lora_lna_gain_t gain, bool boost);

/**
 * @brief Configure the maximum payload length
 * @param[in]    modem    Modem descriptor
 * @param[in]    length   Payload length (in bytes)
 */
void lm_set_max_payload(lora_modem_t *modem, uint8_t length);

/**
 * @brief Sets the modulation that should be used.
 *
 * Make sure the opmode is set to sleep before.
 *
 * @param[in]    modem    Modem descriptor
 * @param[in]    mod      Modulation to use
 */
void lm_set_modulation(lora_modem_t *modem, lora_modulation_t mod);

/**
 * @brief Configures the opmode
 * @param[in]    modem    Modem descriptor
 * @param[in]    opmode   New opmode
 */
void lm_set_opmode(lora_modem_t *modem, lora_opmode_t opmode);

/**
 * @brief Configure high power settings of the PA
 * @param[in]    modem    Modem descriptor
 * @param[in]    enabled  true: +20 dBm on PA_BOOST when max_pwr is set to max.
 *                        (see also lm_set_paconfig)
 */
void lm_set_padac(lora_modem_t *modem, bool enabled);

/**
 * @brief Configures the PA configuration
 *
 * PA Boost defines the value range for the other parameters. It is dependend on
 * the transceiver type.
 *
 * All units are 10th of dBm. If a value is out of range, the valid minimum or
 * maximum will be assumed.
 *
 * For the SX1272:
 * - pwr_max has no effect
 * - with pa_boost=true: pwr_out ranges from 20..190
 * - with pa_boost=false: pwr_out ranges from -10..130
 *
 * For the SX1276:
 * - pwr_max ranges from 108..150 in steps of 6
 * - with pa_boost=false: pwr_out ranges from pwr_max to pwr_max-150 (steps of 10)
 * - with pa_boost=true: pwr_out ranges from 170..20 (steps of 10)
 *
 * @param[in]    modem    Modem descriptor
 * @param[in]    pa_boost Use PA_Boost as output pin
 * @param[in]    pwr_max  Maximum output power, in 10th of dBm (SX1276 only)
 * @param[in]    pwr_out  Output power, in dBm
 */
void lm_set_paconfig(lora_modem_t *modem, bool pa_boost,
        uint8_t pwr_max, int16_t pwr_out);

/**
 * @brief Configure the spreading factor
 *
 * Modem needs to be in sleep or standby first
 *
 * @param[in]    modem    Modem descriptor
 * @param[in]    freq     Spreading factor
 */
void lm_set_sf(lora_modem_t *modem, lora_sf_t sf);

/**
 * @brief Configure the sync word
 *
 * Modem needs to be in sleep or standby first.
 *
 * Private sync word: 0x12, public sync word: 0x34
 *
 * @param[in]    modem    Modem descriptor
 * @param[in]    freq     Sync word
 */
void lm_set_syncword(lora_modem_t *modem, uint8_t syncword);

/**
 * @brief Configures payload CRC for tx
 */
void lm_set_txcrc(lora_modem_t *modem, bool txcrc);

/**
 * @brief Configures the "low datarate optimization"
 *
 * It is activated for symbol times > 16ms, the symbol time is calculated based
 * on the given spreading factor and bandwidth.
 *
 * @param[in]    modem    Modem descriptor
 * @param[in]    sf       Spreading factor
 * @param[in]    bw       Bandwidth
 */
void lm_update_dr_optimize(lora_modem_t *modem, lora_sf_t sf, lora_bandwidth_t bw);

#ifdef __cplusplus
}
#endif

#endif /* LORA_MODEM_INTERNAL_H */