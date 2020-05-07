#include "lora_modem.h"

#include "lora_modem_internal.h"
#include "lora_modem_irq.h"
#include "lora_modem_jammer.h"
#include "lora_modem_receiver.h"
#include "lora_modem_sniffer.h"
#include "lora_modem_transmitter.h"
#include "lora_registers_common.h"
#include "lora_registers_sx1272.h"
#include "lora_registers_sx1276.h"

#include <string.h>

#include "xtimer.h"

#if ENABLE_DEBUG_MODEM_ALL
#define ENABLE_DEBUG (1)
#else
#define ENABLE_DEBUG (0)
#endif
#include "debug.h"

/** Used to create unique names for threads */
static uint8_t modem_thread_count = 0;

/** Function for the transmission scheduler thread. */
static void *_modemthread(void *arg);

int lora_modem_configure_gain(lora_modem_t *modem,
    lora_lna_gain_t lna_gain, bool lna_boost,
    lora_pwr_out_t pwr_out_lvl
    )
{
    int spi_res = SPI_ACQUIRE(modem);
    if (spi_res == SPI_OK) {
        /* Receiver gain */
        lm_set_lna(modem, lna_gain, lna_boost);

        uint8_t pwr_max = 0;
        int16_t pwr_out = 0;
        bool padac = false;
        bool pa_boost = false;
        /* Transmitter config */
        if (modem->chip_type == LORA_CHIP_SX1276) {
            switch(pwr_out_lvl) {
                case LORA_PWR_OUT_0DBM:
                    /* 5dBm */
                    padac = false;
                    pa_boost = false;
                    pwr_max = 150;
                    pwr_out = 0;
                    break;
                case LORA_PWR_OUT_5DBM:
                    /* 5dBm */
                    padac = false;
                    pa_boost = false;
                    pwr_max = 150;
                    pwr_out = 50;
                    break;
                case LORA_PWR_OUT_10DBM:
                    /* 5dBm */
                    padac = false;
                    pa_boost = false;
                    pwr_max = 150;
                    pwr_out = 100;
                    break;
                case LORA_PWR_OUT_15DBM:
                    /* 15 dBm */
                    padac = false;
                    pa_boost = false;
                    pwr_max = 0xff;
                    pwr_out = 0x4ff;
                    break;
                case LORA_PWR_OUT_MAX:
                default:
                    /* Full power: 17 dBm */
                    padac = true;
                    pa_boost = true;
                    pwr_max = 0xff;
                    pwr_out = 0x4ff;
            }
        }
        else if (modem->chip_type == LORA_CHIP_SX1272) {
            switch(pwr_out_lvl) {
                case LORA_PWR_OUT_0DBM:
                    /* 5dBm */
                    padac = false;
                    pa_boost = false;
                    pwr_out = 0;
                    break;
                case LORA_PWR_OUT_5DBM:
                    /* 5dBm */
                    padac = false;
                    pa_boost = false;
                    pwr_out = 50;
                    break;
                case LORA_PWR_OUT_10DBM:
                    /* 5dBm */
                    padac = false;
                    pa_boost = false;
                    pwr_out = 100;
                    break;
                case LORA_PWR_OUT_15DBM:
                    /* 15 dBm */
                    padac = true;
                    pa_boost = true;
                    pwr_out = 150;
                    break;
                case LORA_PWR_OUT_MAX:
                default:
                    /* Full power */
                    padac = true;
                    pa_boost = true;
                    pwr_out = 0x4ff;
            }
        }

        lm_set_paconfig(modem, pa_boost, pwr_max, pwr_out);
        lm_set_padac(modem, padac);

        SPI_RELEASE(modem);
        return 0;
    }
    return -1;
}

int lora_modem_enable_rc_jammer(lora_modem_t *modem, lora_jammer_trigger_t trigger)
{
    switch(trigger) {
        case LORA_JAMMER_TRIGGER_UDP:
#ifndef MODULE_LORA_MODEM_JAMMER_UDP
            DEBUG("lora_modem: Cannot activate GPIO jammer, missing UPD support\n");
            return LORA_MODEM_ERROR_UNSUPPORTED_JAMMER_TRIGGER;
#else
            DEBUG("lora_modem: Enabling jammer with UDP trigger\n");
            break;
#endif
        case LORA_JAMMER_TRIGGER_GPIO:
#ifndef MODULE_PERIPH_GPIO_IRQ
            DEBUG("lora_modem: Cannot activate GPIO jammer, missing HW IRQ\n");
            return LORA_MODEM_ERROR_UNSUPPORTED_JAMMER_TRIGGER;
#else
            if (modem->gpio_jammer == GPIO_UNDEF) {
                DEBUG("lora_modem: Cannot activate GPIO jammer, no GPIO defiend");
                return LORA_MODEM_ERROR_UNSUPPORTED_JAMMER_TRIGGER;
            }
            break;
#endif
        default:
            DEBUG("lora_modem: Unknown trigger type ID: %d\n", trigger);
            return LORA_MODEM_ERROR_UNSUPPORTED_JAMMER_TRIGGER;
    }
    modem->tx_prepared = false;
    if (modem->jammer_trigger != LORA_JAMMER_TRIGGER_NONE) {
        lm_jammer_disable_trigger(modem);
    }
    lm_jammer_enable_trigger(modem, trigger);
    lm_jammer_prepare_jamming(modem);
    return 0;
}

#ifdef MODULE_LORA_MODEM_JAMMER_UDP
int lora_modem_enable_sniffer(lora_modem_t *modem, uint8_t *pattern, uint8_t *mask,
    size_t mask_len, bool rxbuf, lora_sniffer_action_t action, ipv6_addr_t *addr)
#else
int lora_modem_enable_sniffer(lora_modem_t *modem, uint8_t *pattern, uint8_t *mask,
    size_t mask_len, bool rxbuf, lora_sniffer_action_t action)
#endif
{
    /** First: Check the action. If it is not supported, this is a no-op */
    switch(action) {
        case LORA_SNIFFER_ACTION_UDP:
#ifndef MODULE_LORA_MODEM_JAMMER_UDP
            return LORA_MODEM_ERROR_UNSUPPORTED_SNIFFER_ACTION;
#else
            DEBUG("lora_modem: Enabling sniffer with UDP action\n");
            memcpy(modem->sniffer_addr, addr->u8, sizeof(modem->sniffer_addr));
            modem->sniffer_action = LORA_SNIFFER_ACTION_UDP;
            break;
#endif
        case LORA_SNIFFER_ACTION_GPIO:
#ifdef MODULE_PERIPH_GPIO
            if (modem->gpio_sniffer == GPIO_UNDEF) {
                DEBUG("lora_modem: Sniffer GPIO is undefined\n");
                return LORA_MODEM_ERROR_UNSUPPORTED_SNIFFER_ACTION;
            }
            DEBUG("lora_modem: Enabling sniffer with GPIO action\n");
            modem->sniffer_action = LORA_SNIFFER_ACTION_GPIO;
            break;
#else
            return LORA_MODEM_ERROR_UNSUPPORTED_SNIFFER_ACTION;
#endif
        case LORA_SNIFFER_ACTION_INTERNAL:
            DEBUG("lora_modem: Enabling sniffer with internal action\n");
            rxbuf = false;
            modem->sniffer_action = LORA_SNIFFER_ACTION_INTERNAL;
            break;
        default:
            break;
    }

    modem->tx_prepared = false;
    if (modem->active_tasks.sniffer == true) {
        lm_stop_sniffer(modem);
    }

    /* Optimize pattern and mask, and store it. */
    modem->sniffer_mask_len = 0;
    for (size_t idx = 0; idx < mask_len; idx++) {
        /* Strip 0x00-bytes at the end */
        if (mask[idx] != 0x00) {
            modem->sniffer_mask_len = idx + 1;
        }
        modem->sniffer_mask[idx] = mask[idx];
        /* We can already & the pattern and the mask here */
        modem->sniffer_pattern[idx] = mask[idx] & pattern[idx];
    }

    modem->sniffer_to_rxbuf = rxbuf;

    return lm_setup_sniffing(modem);
}

ssize_t lora_modem_fetch_frame(lora_modem_t *modem, uint8_t *payload,
    lora_rx_stats_t *rx_stats, bool *has_more, bool *frames_dropped)
{
    ringbuffer_t *rb = &(modem->ringbuf_recv);
    DEBUG("lora_modem: Locking ringbuffer for fetch_frame\n");
    mutex_lock(&(modem->mutex_ringbuf_recv));
    if (ringbuffer_empty(rb)) {
        DEBUG("lora_modem: Ringbuffer is empty\n");
        mutex_unlock(&(modem->mutex_ringbuf_recv));
        return -1;
    }

    /* Copy payload and size */
    ssize_t res = ringbuffer_get_one(rb);
    uint8_t payload_size = (uint8_t)res;
    DEBUG("lora_modem: Fetching frame of %u bytes\n", payload_size);
    uint8_t bytes_read = 0;
    while (bytes_read < payload_size) {
        uint8_t n = ringbuffer_get(rb, (char*)&(payload[bytes_read]), payload_size - bytes_read);
        DEBUG("lora_modem: Read %u payload bytes from ringbuffer:\n", n);
        bytes_read += n;
    }

    /* Copy RX stats */
    bytes_read = 0;
    char rx_stats_buf[sizeof(lora_rx_stats_t)];
    while (bytes_read < sizeof(rx_stats_buf)) {
        uint8_t n = ringbuffer_get(rb, rx_stats_buf+bytes_read, sizeof(rx_stats_buf)-bytes_read);
        DEBUG("lora_modem: Read %u rx_stats bytes from ringbuffer\n", n);
        bytes_read += n;
    }
    (*has_more) = ringbuffer_empty(rb) == 0;
    mutex_unlock(&(modem->mutex_ringbuf_recv));
    DEBUG("lora_modem: Unlocked ringbuffer\n");
    memcpy(rx_stats, rx_stats_buf, sizeof(lora_rx_stats_t));

    (*frames_dropped) = modem->frames_dropped;
    modem->frames_dropped = false;

    return payload_size;
}

int lora_modem_init(lora_modem_t *modem)
{
    /* Receive Buffer */
    ringbuffer_init(&(modem->ringbuf_recv), modem->buf_recv, LORA_RECEIVE_BUFFER_SIZE);
    mutex_init(&(modem->mutex_ringbuf_recv));
    /* Transmit Buffer */
    mutex_init(&(modem->mutex_tx_queue));
    memset(modem->tx_queue, 0, LORA_TRANSMIT_QUEUE_SIZE * sizeof(lora_tx_queue_entry_t));
    /* Thread PIDs */
    modem->irq_thread_pid = KERNEL_PID_UNDEF;
    modem->modem_thread_pid = KERNEL_PID_UNDEF;
    modem->tx_done_ack_pid = KERNEL_PID_UNDEF;
#ifdef MODULE_LORA_MODEM_JAMMER_UDP
    modem->udp_thread_pid = KERNEL_PID_UNDEF;
    modem->sniffer_if = 0;
#endif
    /* Timestamps and receiver status */
    modem->t_rxdone = 0;
    modem->t_valid_header = 0;
    modem->frames_dropped = false;
    memset(&(modem->tx_done_timer), 0, sizeof(modem->tx_done_timer));
    /* Jammer configuration */
    modem->jammer_trigger = LORA_JAMMER_TRIGGER_NONE;
    modem->jammer_prepared = false;
    modem->jammer_plength = 0x40;
    modem->jammer_active = false;
    /* Prepares transmissions */
    modem->tx_prepared = false;
    /* Sniffer configuration */
    modem->sniffer_action = LORA_SNIFFER_ACTION_NONE;
    /* Set all active tasks to false */
    memset(&(modem->active_tasks), 0, sizeof(modem->active_tasks));
    /* IRQ configuration */
    memset(&(modem->irq_config), 0, sizeof(lora_irq_config_t));
    mutex_init(&(modem->mutex_irq_config));

    sprintf(modem->modem_thread_name, "loramodem:%d", modem_thread_count);
    sprintf(modem->irq_thread_name,   "loramodem:%d", modem_thread_count++);
    lm_init_gpios(modem);

    if (spi_init_cs(modem->bus, modem->cs) != SPI_OK) {
        DEBUG("lora_modem: Couldn't initialize SPI pins.\n");
        return LORA_MODEM_INIT_NODEV;
    }
    lm_reset(modem);

    modem->chip_type = LORA_CHIP_UNKNOWN;
    int spi_res = SPI_ACQUIRE(modem);
    if (spi_res != SPI_OK) {
        DEBUG("lora_modem: Couldn't acquire SPI.\n");
        return LORA_MODEM_INIT_NODEV;
    }

    uint8_t type_id = lm_read_reg(modem, REG127X_VERSION);
    if (type_id == VAL1276_VERSION) {
        DEBUG("lora_modem: Found SX1276\n");
        modem->chip_type = LORA_CHIP_SX1276;
    } else if (type_id == VAL1272_VERSION) {
        DEBUG("lora_modem: Found SX1272\n");
        modem->chip_type = LORA_CHIP_SX1272;
    } else {
        SPI_RELEASE(modem);
        DEBUG("lora_modem: Unknown modem identifier: 0x%02x\n", type_id);
        return LORA_MODEM_INIT_UNKNOWNDEV;
    }

    // Go to sleep mode (required to switch to LoRa mode)
    lm_set_opmode(modem, LORA_OPMODE_SLEEP);

    // Set LoRa mode
    lm_set_modulation(modem, LORA_MODULATION_LORA);

    // Enable AGC auto on
    lm_set_agc_autoon(modem, true);

    // Disable channel hopping
    lm_set_hop_period(modem, 0x00);

    // Set maximum paylaod length. For the evaluation, we aren't interested in the
    // modem filtering out some messages.
    lm_set_max_payload(modem, 0xff);

    // Set LNA Gain to max and enable boost
    lm_set_lna(modem, LORA_LNA_GAIN_G1, true);

    // Configure TX power to max
    lm_set_paconfig(modem, true, 0xff, 0x4ff);
    lm_set_padac(modem, true);

    // Set the TX Buffer to the RX buffer
    lm_write_reg(modem, REG127X_LORA_FIFOTXBASEADDR, 0x00);
    lm_write_reg(modem, REG127X_LORA_FIFORXBASEADDR, 0x00);

    // Configure buffers and fifo
    lm_write_reg(modem, REG127X_LORA_FIFOADDRPTR, lm_read_reg(modem, REG127X_LORA_FIFORXBASEADDR));

    /* We need this as reference to calculate the amount of bytes already transmitted */
    modem->lora_sniffer_last_rxbyteaddr = lm_read_reg(modem, REG127X_LORA_FIFORXBYTEADDR);

    lm_write_reg(modem, REG127X_LORA_PAYLOADLENGTH, 0xFF);

    // Read DIO-Mappings
    modem->dio_mapping1 = lm_read_reg(modem, REG127X_DIO_MAPPING1);
    modem->dio_mapping2 = lm_read_reg(modem, REG127X_DIO_MAPPING2);

    // Setup the default channel: 868.1 MHz, SF7, 125 kHz, 4/5 Coding, private sync word
    lm_set_frequency(modem, 868100000);
    lm_set_sf(modem, LORA_SF_7);
    lm_set_bandwidth(modem, LORA_BANDWIDTH_125KHZ);
    lm_update_dr_optimize(modem, LORA_SF_7, LORA_BANDWIDTH_125KHZ);
    lm_set_codingrate(modem, LORA_CODINGRATE_4_5);
    lm_set_syncword(modem, 0x12);

    // Disable all interrupts
    lm_write_reg(modem, REG127X_LORA_IRQFLAGSMASK, 0xFF);

    // Go to standby
    lm_set_opmode(modem, LORA_OPMODE_STANDBY);

    SPI_RELEASE(modem);

    // Start modem thread
    DEBUG("lora_modem: Starting RX/TX thread: %s\n", modem->modem_thread_name);

    memset(modem->modem_thread_stack, 0, sizeof(modem->modem_thread_stack));
    modem->modem_thread_pid = thread_create(
        modem->modem_thread_stack,
        sizeof(modem->modem_thread_stack),
        THREAD_PRIORITY_MAIN + 1,
        0,
        _modemthread,
        modem,
        modem->modem_thread_name
    );

    return LORA_MODEM_INIT_OK;
}

int lora_modem_receive(lora_modem_t *modem)
{
    modem->tx_prepared = false;
    return lm_enable_receiver(modem, true);
}

uint32_t lora_modem_get_frequency(lora_modem_t *modem)
{
    int spi_res = SPI_ACQUIRE(modem);
    if (spi_res == SPI_OK) {
        uint32_t res = lm_get_frequency(modem);
        SPI_RELEASE(modem);
        return res;
    }
    return 0;
}

lora_bandwidth_t lora_modem_get_bandwidth(lora_modem_t *modem)
{
    int spi_res = SPI_ACQUIRE(modem);
    if (spi_res == SPI_OK) {
        lora_bandwidth_t res = lm_get_bandwidth(modem);
        SPI_RELEASE(modem);
        return res;
    }
    return LORA_BANDWIDTH_INVALID;
}

lora_codingrate_t lora_modem_get_codingrate(lora_modem_t *modem)
{
    int spi_res = SPI_ACQUIRE(modem);
    if (spi_res == SPI_OK) {
        lora_codingrate_t res = lm_get_codingrate(modem);
        SPI_RELEASE(modem);
        return res;
    }
    return LORA_CODINGRATE_INVALID;
}

int lora_modem_get_explicitheader(lora_modem_t *modem)
{
    if (SPI_ACQUIRE(modem) == SPI_OK) {
        bool explicitheader = lm_get_explicitheader(modem);
        SPI_RELEASE(modem);
        return explicitheader != 0;
    }
    return -1;
}

int lora_modem_get_invertiqrx(lora_modem_t *modem)
{

    if (SPI_ACQUIRE(modem) == SPI_OK) {
        bool invertiq = lm_get_invertiqrx(modem);
        SPI_RELEASE(modem);
        return invertiq;
    }
    return -1;
}

int lora_modem_get_invertiqtx(lora_modem_t *modem)
{

    if (SPI_ACQUIRE(modem) == SPI_OK) {
        bool invertiq = lm_get_invertiqtx(modem);
        SPI_RELEASE(modem);
        return invertiq;
    }
    return -1;
}

int lora_modem_get_preamble_length(lora_modem_t *modem)
{
    if (SPI_ACQUIRE(modem) == SPI_OK) {
        uint16_t length = 0;
        length |= lm_read_reg(modem, REG127X_LORA_PREAMBLEMSB) << 8;
        length |= lm_read_reg(modem, REG127X_LORA_PREAMBLELSB);
        SPI_RELEASE(modem);
        return length;
    }
    return -1;
}

lora_sf_t lora_modem_get_sf(lora_modem_t *modem)
{
    int spi_res = SPI_ACQUIRE(modem);
    if (spi_res == SPI_OK) {
        lora_sf_t res = lm_get_sf(modem);
        SPI_RELEASE(modem);
        return res;
    }
    return LORA_SF_INVALID;
}

int lora_modem_get_syncword(lora_modem_t *modem)
{
    int spi_res = SPI_ACQUIRE(modem);
    if (spi_res == SPI_OK) {
        uint8_t res = lm_get_syncword(modem);
        SPI_RELEASE(modem);
        return res;
    }
    return -1;
}

int lora_modem_get_txcrc(lora_modem_t *modem)
{
    int spi_res = SPI_ACQUIRE(modem);
    if (spi_res == SPI_OK) {
        bool res = lm_get_txcrc(modem);
        SPI_RELEASE(modem);
        return res;
    }
    return -1;
}

int lora_modem_prepare_tx(lora_modem_t *modem, lora_frame_t *frame)
{
    if (lora_modem_standby(modem) != 0) {
        return -1;
    }
    if (SPI_ACQUIRE(modem) == SPI_OK) {
        lm_write_reg(modem, REG127X_LORA_PAYLOADLENGTH, frame->length);
        lm_write_reg(modem, REG127X_LORA_FIFOADDRPTR,
            lm_read_reg(modem, REG127X_LORA_FIFOTXBASEADDR));
        lm_write_reg_burst(modem, REG127X_FIFO, frame->payload, frame->length);
        SPI_RELEASE(modem);
        modem->tx_prepared = true;
        return 0;
    }
    return -1;
}

int lora_modem_transmit_prepared(lora_modem_t *modem, bool await)
{
    if (modem->tx_prepared && SPI_ACQUIRE(modem) == SPI_OK) {
        lm_set_opmode(modem, LORA_OPMODE_TX);
        modem->tx_done_ack_pid = await ? thread_getpid() : KERNEL_PID_UNDEF;
        lm_enable_irq(modem, LORA_IRQ_TXDONE, isr_reset_state_after_tx);
        modem->tx_prepared = false;
        SPI_RELEASE(modem);
        if (await) {
            thread_sleep();
        }
        return 0;
    }
    return -1;
}

int lora_modem_set_opmode(lora_modem_t *modem, lora_opmode_t opmode)
{
    int spi_res;
    if ((spi_res = SPI_ACQUIRE(modem)) == SPI_OK) {
        lm_set_opmode(modem, opmode);
        /* Undocumented feature: Pushing the modem to standby sets
         *  fifoRxByteAddr := fifoRxBaseAddr
         * (at least for the SX1276)
         */
        modem->lora_sniffer_last_rxbyteaddr =
            lm_read_reg(modem, REG127X_LORA_FIFORXBASEADDR);
        SPI_RELEASE(modem);
    }
    return spi_res;
}

int lora_modem_set_invertiqrx(lora_modem_t *modem, bool invertiq)
{
    if (SPI_ACQUIRE(modem)==SPI_OK) {
        lm_set_invertiqrx(modem, invertiq);
        SPI_RELEASE(modem);
        return 0;
    }
    return -1;
}

int lora_modem_set_invertiqtx(lora_modem_t *modem, bool invertiq)
{
    if (SPI_ACQUIRE(modem)==SPI_OK) {
        lm_set_invertiqtx(modem, invertiq);
        SPI_RELEASE(modem);
        return 0;
    }
    return -1;
}

int lora_modem_set_preamble_length(lora_modem_t *modem, uint16_t length)
{
    int res = SPI_ACQUIRE(modem);
    if (res == SPI_OK) {
        lora_opmode_t opmode = lm_get_opmode(modem);
        if (opmode == LORA_OPMODE_SLEEP || opmode == LORA_OPMODE_STANDBY) {
            lm_write_reg(modem, REG127X_LORA_PREAMBLEMSB, (uint8_t)((length>>8)&0xff));
            lm_write_reg(modem, REG127X_LORA_PREAMBLELSB, (uint8_t)(length&0xff));
            res = 0;
        }
        else {
            res = LORA_MODEM_ERROR_COMMAND_REQUIRES_STANDBY;
        }
        SPI_RELEASE(modem);
    }
    return res;
}

int lora_modem_set_modulation(lora_modem_t *modem, lora_modulation_t mod)
{
    int spi_res;
    if ((spi_res = SPI_ACQUIRE(modem)) == SPI_OK) {
        lm_set_modulation(modem, mod);
        SPI_RELEASE(modem);
    }
    return spi_res;
}

int lora_modem_set_frequency(lora_modem_t *modem, uint32_t freq)
{
    int spi_res;
    if ((spi_res = SPI_ACQUIRE(modem)) == SPI_OK) {
        lm_set_frequency(modem, freq);
        SPI_RELEASE(modem);
    }
    return spi_res;
}

int lora_modem_set_bandwidth(lora_modem_t *modem, lora_bandwidth_t bw)
{
    int spi_res;
    if ((spi_res = SPI_ACQUIRE(modem)) == SPI_OK) {
        lm_set_bandwidth(modem, bw);
        lora_sf_t sf = lm_get_sf(modem);
        lm_update_dr_optimize(modem, sf, bw);
        SPI_RELEASE(modem);
    }
    return spi_res;
}

int lora_modem_set_codingrate(lora_modem_t *modem, lora_codingrate_t cr)
{
    int spi_res;
    if ((spi_res = SPI_ACQUIRE(modem)) == SPI_OK) {
        lm_set_codingrate(modem, cr);
        SPI_RELEASE(modem);
    }
    return spi_res;
}

int lora_modem_set_explicitheader(lora_modem_t *modem, bool explicitheader)
{
    int res = SPI_ACQUIRE(modem);
    if (res == SPI_OK) {
        lm_set_explicitheader(modem, explicitheader);
        SPI_RELEASE(modem);
        return 0;
    }
    return -1;
}

void lora_modem_set_jammer_plength(lora_modem_t *modem, uint8_t length)
{
    modem->jammer_plength = length;
    if (SPI_ACQUIRE(modem) == SPI_OK) {
        lm_write_reg(modem, REG127X_LORA_PAYLOADLENGTH, length);
        SPI_RELEASE(modem);
    }
}

int lora_modem_set_sf(lora_modem_t *modem, lora_sf_t sf)
{
    int spi_res;
    if ((spi_res = SPI_ACQUIRE(modem)) == SPI_OK) {
        lm_set_sf(modem, sf);
        lora_bandwidth_t bw = lm_get_bandwidth(modem);
        lm_update_dr_optimize(modem, sf, bw);
        SPI_RELEASE(modem);
    }
    return spi_res;
}

int lora_modem_set_syncword(lora_modem_t *modem, uint8_t syncword)
{
    int spi_res;
    if ((spi_res = SPI_ACQUIRE(modem)) == SPI_OK) {
        lm_set_syncword(modem, syncword);
        SPI_RELEASE(modem);
    }
    return spi_res;
}

int lora_modem_set_txcrc(lora_modem_t *modem, bool txcrc)
{
    int res = SPI_ACQUIRE(modem);
    if (res == SPI_OK) {
        lora_opmode_t opmode = lm_get_opmode(modem);
        if (opmode == LORA_OPMODE_SLEEP || opmode == LORA_OPMODE_STANDBY) {
            lm_set_txcrc(modem, txcrc);
            res = 0;
        }
        else {
            res = LORA_MODEM_ERROR_COMMAND_REQUIRES_STANDBY;
        }
        SPI_RELEASE(modem);
        return res;
    }
    return -1;
}

int lora_modem_standby(lora_modem_t *modem)
{
    DEBUG("%s: Going to standby\n", thread_getname(thread_getpid()));
    lora_modem_active_tasks_t active_tasks;
    /* Copy flags, otherwise the stopping actions might try to restore some state */
    memcpy(&active_tasks, &(modem->active_tasks), sizeof(lora_modem_active_tasks_t));
    memset(&(modem->active_tasks), 0, sizeof(lora_modem_active_tasks_t));
    if (active_tasks.rx) {
        lm_disable_receiver(modem);
    }
    if (active_tasks.tx) {
        lm_stop_transmission(modem);
    }
    if (active_tasks.sniffer) {
        lm_stop_sniffer(modem);
    }
    if (active_tasks.jammer) {
        lm_jammer_disable_trigger(modem);
    }
    if (SPI_ACQUIRE(modem)==SPI_OK) {
        /* Reset all IRQs */
        uint8_t flags = lm_write_reg(modem, REG127X_LORA_IRQFLAGSMASK, 0xff);
        uint8_t irqs = lm_write_reg(modem, REG127X_LORA_IRQFLAGS, 0xff);
        SPI_RELEASE(modem);
        if (flags!=0xff) {
            printf("Going to standby. IRQFLAGSMASK was still 0x%02x\n", flags);
        }
        if (irqs) {
            printf("Going to standby. IRQFLAGS was still 0x%02x\n", flags);
        }
    }
    modem->jammer_active = false;
    return 0;
}

int lora_modem_transmit(lora_modem_t *modem, lora_frame_t *frame,
    uint64_t time, bool blocking)
{
    /* If the scheduled time is in the past (or 0 = no time), send immediately */
    uint64_t now = xtimer_now_usec64();
    DEBUG("lora_modem: now=%llu sched=%llu -> ", now, time);
    modem->tx_prepared = false;
    if (time < now) {
        DEBUG("transmitting now\n");
        return lm_transmit_now(modem, frame, blocking);
    }
    else {
        DEBUG("scheduling\n");
        /* Queue the frame */
        mutex_lock(&(modem->mutex_tx_queue));
        size_t queueslot = 0;
        while (queueslot < LORA_TRANSMIT_QUEUE_SIZE &&
            modem->tx_queue[queueslot].used) {
                queueslot+=1;
        }
        if (queueslot >= LORA_TRANSMIT_QUEUE_SIZE) {
            DEBUG("Cannot schedule. No slot available (QUEUE_SIZE=%d)\n", LORA_TRANSMIT_QUEUE_SIZE);
            /* No slot available */
            mutex_unlock(&(modem->mutex_tx_queue));
            return LORA_MODEM_ERROR_TXQUEUE_FULL;
        }
        else {
            lora_tx_queue_entry_t *entry = &(modem->tx_queue[queueslot]);
            entry->used = true;
            entry->msg.content.value = queueslot;
            entry->msg.type = LORAMODEM_MTYPE_TXSCHED;
            memcpy(entry->payload, frame->payload, frame->length);
            entry->length = frame->length;
            mutex_unlock(&(modem->mutex_tx_queue));
            xtimer_set_msg64(&(entry->timer), time-now, &(entry->msg), modem->modem_thread_pid);
            return 0;
        }
    }
}

static void *_modemthread(void *arg)
{
    lora_modem_t *modem = (lora_modem_t*)arg;
    msg_t msg_queue[4];
    msg_init_queue(msg_queue, 4);
    msg_t msg;

    DEBUG("%s: Starting...\n", thread_getname(thread_getpid()));
    while(true) {
        /* Prepare the jammer if the modem isn't occupied otherwise */
        lm_jammer_prepare_jamming(modem);

        DEBUG("%s: Waiting for message\n", thread_getname(thread_getpid()));
        msg_receive(&msg);
        /* In order of time criticality */
        if (msg.type == LORAMODEM_MTYPE_TRIGGER_JAMMER) {
            DEBUG("%s: Got MTYPE_TRIGGER_JAMMER\n", thread_getname(thread_getpid()));
            lm_jammer_jam_frame(modem);
        }
        else if (msg.type == LORAMODEM_MTYPE_SIGNAL_SNIFFER) {
            DEBUG("%s: Got MTYPE_SIGNAL_SNIFFER\n", thread_getname(thread_getpid()));
            lm_start_sniffing(modem);
        }
        else if (msg.type == LORAMODEM_MTYPE_TXSCHED) {
            DEBUG("%s: Got MTYPE_TXSCHED\n", thread_getname(thread_getpid()));
            lora_frame_t frame;
            size_t idx = msg.content.value;
            mutex_lock(&(modem->mutex_tx_queue));
            lora_tx_queue_entry_t *entry = &(modem->tx_queue[idx]);
            frame.payload = entry->payload;
            frame.length = entry->length;
            lm_transmit_now(modem, &frame, false);
            entry->used = false;
            mutex_unlock(&(modem->mutex_tx_queue));
            DEBUG("lora_modem.tx: Sent scheduled message.\n");
        }
        else if (msg.type == LORAMODEM_MTYPE_FRAME_TO_BUF) {
            DEBUG("%s: Got MTYPE_FRAME_TO_BUF\n", thread_getname(thread_getpid()));
            lm_frame_to_buffer(modem);
        }
        else if (msg.type == LORAMODEM_MTYPE_TX_RESTORE) {
            DEBUG("%s: Got LORAMODEM_MTYPE_TX_RESTORE\n", thread_getname(thread_getpid()));
            lm_restore_after_transmit(modem);
        }
        else {
            DEBUG("%s: Got unexpected MTYPE: %d\n", thread_getname(thread_getpid()), msg.type);
        }
    }
    return NULL;
}

/** Dumps the content of the FIFO to stdout */
void lora_modem_dump_fifo(lora_modem_t *modem)
{
    if (SPI_ACQUIRE(modem)==SPI_OK) {
        uint8_t rxbyteaddr = lm_read_reg(modem, REG127X_LORA_FIFORXBYTEADDR);
        uint8_t rxbaseaddr = lm_read_reg(modem, REG127X_LORA_FIFORXBASEADDR);
        uint8_t txbaseaddr = lm_read_reg(modem, REG127X_LORA_FIFOTXBASEADDR);
        printf("RxByteAddr: 0x%02x RxBaseAddr: 0x%02x TxBaseAddr: 0x%02x Sniffer:0x%02x\n",
            rxbyteaddr, rxbaseaddr, txbaseaddr, modem->lora_sniffer_last_rxbyteaddr);
        lm_write_reg(modem, REG127X_LORA_FIFOADDRPTR, 0);
        uint8_t fifo[256];
        lm_read_reg_burst(modem, REG127X_FIFO, fifo, sizeof(fifo));
        printf("     ");
        for(uint8_t n = 0; n < 16; n++) {
            printf("   %1x", n);
        }
        putchar('\n');
        for(uint8_t n = 0; n < 16; n++) {
            printf("0x%x0: ", n);
            for(uint8_t m = 0; m < 16; m++) {
                uint8_t idx = (n<<4)+m;
                if (idx == rxbyteaddr) {
                    putchar('>');
                }
                else if (idx == rxbaseaddr || idx == txbaseaddr) {
                    putchar('~');
                }
                else {
                    putchar(' ');
                }
                printf("%02x ", fifo[idx]);
            }
            printf("\n");
        }
        SPI_RELEASE(modem);
    }
    else {
        printf("No SPI, sorry :(\n");
    }
}

#define DUMPLORAREG(REG) printf("0x%02x " #REG " = 0x%02x\n", REG127X_ ## REG, lm_read_reg(modem, REG127X_ ## REG))

/** Dumps the content of modem registers to stdout */
void lora_modem_dump_regs(lora_modem_t *modem)
{
    if (SPI_ACQUIRE(modem)==SPI_OK) {
        DUMPLORAREG(OPMODE);
        DUMPLORAREG(FRFMSB);
        DUMPLORAREG(FRFMID);
        DUMPLORAREG(FRFLSB);
        DUMPLORAREG(PACONFIG);
        DUMPLORAREG(PARAMP);
        DUMPLORAREG(OCP);
        DUMPLORAREG(LNA);
        DUMPLORAREG(LORA_FIFOADDRPTR);
        DUMPLORAREG(LORA_FIFOTXBASEADDR);
        DUMPLORAREG(LORA_FIFORXBASEADDR);
        DUMPLORAREG(LORA_RXCURRENTADDR);
        DUMPLORAREG(LORA_IRQFLAGSMASK);
        DUMPLORAREG(LORA_IRQFLAGS);
        DUMPLORAREG(LORA_RXNBBYTES);
        DUMPLORAREG(LORA_RXHEADERCNTVALUEMSB);
        DUMPLORAREG(LORA_RXHEADERCNTVALUELSB);
        DUMPLORAREG(LORA_RXPACKETCNTVALUEMSB);
        DUMPLORAREG(LORA_RXPACKETCNTVALUELSB);
        DUMPLORAREG(LORA_MODEMSTAT);
        DUMPLORAREG(LORA_PKTSNRVALUE);
        DUMPLORAREG(LORA_PKTRSSIVALUE);
        DUMPLORAREG(LORA_RSSIVALUE);
        DUMPLORAREG(LORA_MODEMCONFIG1);
        DUMPLORAREG(LORA_MODEMCONFIG2);
        DUMPLORAREG(LORA_PREAMBLEMSB);
        DUMPLORAREG(LORA_PREAMBLELSB);
        DUMPLORAREG(LORA_PAYLOADLENGTH);
        DUMPLORAREG(LORA_MAXPAYLOADLENGTH);
        DUMPLORAREG(LORA_HOPPERIOD);
        DUMPLORAREG(LORA_FIFORXBYTEADDR);
        DUMPLORAREG(LORA_INVERTIQ);
        DUMPLORAREG(LORA_SYNCWORD);
        DUMPLORAREG(DIO_MAPPING1);
        DUMPLORAREG(DIO_MAPPING2);
        SPI_RELEASE(modem);
    }
    else {
        printf("No SPI, sorry :(\n");
    }
}
