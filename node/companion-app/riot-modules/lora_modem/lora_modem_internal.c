#ifdef MODULE_PERIPH_GPIO
#include "periph/gpio.h"
#endif
#include "xtimer.h"

#include "lora_modem_internal.h"
#include "lora_registers_common.h"
#include "lora_registers_sx1272.h"
#include "lora_registers_sx1276.h"

#if ENABLE_DEBUG_MODEM_ALL
#define ENABLE_DEBUG (1)
#else
#define ENABLE_DEBUG (0)
#endif
#include "debug.h"

uint32_t lm_calc_symboltime(lora_sf_t sf, lora_bandwidth_t bw)
{
    return ((1<<sf)*1000)/bw;
}

uint8_t lm_read_reg(lora_modem_t *modem, uint8_t address)
{
    /* MSB=0 means reading */
    uint8_t buf[2] = {address & 0x7f, 0x00};
    spi_transfer_bytes(modem->bus, modem->cs, false, buf, buf, 2);
    return buf[1];
}

uint8_t lm_read_reg_masked(lora_modem_t *modem, uint8_t address, uint8_t mask)
{
    uint8_t buf[2] = {address & 0x7f, 0x00};
    spi_transfer_bytes(modem->bus, modem->cs, false, buf, buf, 2);
    return buf[1] & mask;
}

void lm_read_reg_burst(lora_modem_t *modem, uint8_t address,
        uint8_t *data, size_t length)
{
    uint8_t addrBuf[1] = {address & 0x7f};
    spi_transfer_bytes(modem->bus, modem->cs, true, addrBuf, NULL, 1);
    spi_transfer_bytes(modem->bus, modem->cs, false, NULL, data, length);
}

uint8_t lm_write_reg(lora_modem_t *modem, uint8_t address, uint8_t value)
{
    /* MSB=0 means writing */
    uint8_t buf[2] = {address | 0x80, value};
    spi_transfer_bytes(modem->bus, modem->cs, false, buf, buf, 2);
    return buf[1];
}

void lm_write_reg_burst(lora_modem_t *modem, uint8_t address,
        uint8_t *data, size_t length)
{
    uint8_t addrBuf[1] = {address | 0x80};
    spi_transfer_bytes(modem->bus, modem->cs, true, addrBuf, NULL, 1);
    spi_transfer_bytes(modem->bus, modem->cs, false, data, NULL, length);
}

uint8_t lm_write_reg_masked(lora_modem_t *modem, uint8_t address,
        uint8_t mask, uint8_t value)
{
    return lm_write_reg(
        modem,
        address,
        (value & mask) | (lm_read_reg(modem, address) & ~mask)
    ) & mask;
}

void lm_reset(lora_modem_t *modem)
{
#ifdef MODULE_PERIPH_GPIO
    if (modem->gpio_reset != GPIO_UNDEF) {
        gpio_write(modem->gpio_reset, modem->reset_on_high ? 1 : 0);
        xtimer_usleep(10000); /* 10ms */
        gpio_write(modem->gpio_reset, modem->reset_on_high ? 0 : 1);
        xtimer_usleep(5000);  /* 5ms */
    }
#else
    (void)modem;
#endif
}

lora_bandwidth_t lm_get_bandwidth(lora_modem_t *modem)
{
    if (modem->chip_type == LORA_CHIP_SX1276) {
        uint8_t bwVal = lm_read_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
                MSK1276_LORA_MODEMCONFIG1_BW);
        if (bwVal == VAL1276_LORA_MODEMCONFIG1_BW125) {
            return LORA_BANDWIDTH_125KHZ;
        }
        else if (bwVal == VAL1276_LORA_MODEMCONFIG1_BW250) {
            return LORA_BANDWIDTH_250KHZ;
        }
        else if (bwVal == VAL1276_LORA_MODEMCONFIG1_BW500) {
            return LORA_BANDWIDTH_500KHZ;
        }
    }
    else if (modem->chip_type == LORA_CHIP_SX1272) {
        uint8_t bwVal = lm_read_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
                MSK1272_LORA_MODEMCONFIG1_BW);
        if (bwVal == VAL1272_LORA_MODEMCONFIG1_BW125) {
            return LORA_BANDWIDTH_125KHZ;
        }
        else if (bwVal == VAL1272_LORA_MODEMCONFIG1_BW250) {
            return LORA_BANDWIDTH_250KHZ;
        }
        else if (bwVal == VAL1272_LORA_MODEMCONFIG1_BW500) {
            return LORA_BANDWIDTH_500KHZ;
        }
    }
    return 0;
}

lora_codingrate_t lm_get_codingrate(lora_modem_t *modem)
{
    if (modem->chip_type == LORA_CHIP_SX1276) {
        return (lm_read_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
                MSK1276_LORA_MODEMCONFIG1_CR) >> 1) + 4;
    }
    else if (modem->chip_type == LORA_CHIP_SX1272) {
        return (lm_read_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
                MSK1272_LORA_MODEMCONFIG1_CR) >> 3) + 4;
    }
    return 0;
}

bool lm_get_explicitheader(lora_modem_t *modem)
{
    if (modem->chip_type == LORA_CHIP_SX1276) {
        return lm_read_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
            MSK1276_LORA_MODEMCONFIG1_IMPLICIT_HDR) ==
            VAL1276_LORA_MODEMCONFIG1_IMPLICIT_HDR_OFF;
    }
    else if (modem->chip_type == LORA_CHIP_SX1272) {
        return lm_read_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
            MSK1276_LORA_MODEMCONFIG1_IMPLICIT_HDR) ==
            VAL1276_LORA_MODEMCONFIG1_IMPLICIT_HDR_OFF;
    }
    return false;
}

uint32_t lm_get_frequency(lora_modem_t *modem)
{
    uint64_t frf =
        ((uint64_t)(lm_read_reg(modem, REG127X_FRFMSB)) << 16) +
        ((uint64_t)(lm_read_reg(modem, REG127X_FRFMID)) <<  8) +
        (uint64_t)(lm_read_reg(modem, REG127X_FRFLSB));
    frf*=32000000;
    return (uint32_t)(frf >> 19);
}

bool lm_get_invertiqrx(lora_modem_t *modem)
{
    uint8_t val_invertiq = lm_read_reg_masked(modem,
        REG127X_LORA_INVERTIQ, MSK1272_LORA_INVERTIQ_INVERTIQ_RX);
    return val_invertiq == VAL1272_LORA_INVERTIQ_INVERTIQ_RX_INVERTED;
}

bool lm_get_invertiqtx(lora_modem_t *modem)
{
    uint8_t val_invertiq = lm_read_reg_masked(modem,
        REG127X_LORA_INVERTIQ, MSK1272_LORA_INVERTIQ_INVERTIQ_TX);
    return val_invertiq == VAL1272_LORA_INVERTIQ_INVERTIQ_TX_INVERTED;
}

lora_opmode_t lm_get_opmode(lora_modem_t *modem)
{
    return (lora_opmode_t)lm_read_reg_masked(
        modem, REG127X_OPMODE, MSK127X_OPMODE_MODE);
}

int lm_get_rssi(lora_modem_t *modem)
{
    /* Note: The offset is only valid for the HF band for the SX1276-type */
    return lm_read_reg(modem, REG127X_LORA_RSSIVALUE) -
        (modem->chip_type == LORA_CHIP_SX1272 ? 139 : 157);
}

void lm_get_rx_stats(lora_modem_t *modem, lora_rx_stats_t *stats)
{
    stats->time_header = modem->t_valid_header;
    stats->time_rxdone = modem->t_rxdone;
    int rssi_raw = lm_read_reg(modem, REG127X_LORA_PKTRSSIVALUE);
    int snr_raw = ((int)lm_read_reg(modem, REG127X_LORA_PKTSNRVALUE))-128;
    stats->snr = snr_raw/4;
    if (modem->chip_type == LORA_CHIP_SX1272) {
        /* see chapter 6.3 of the data sheet */
        stats->rssi = rssi_raw - 139 + (snr_raw < 0 ? snr_raw / 4 : 0);
    }
    else if (modem->chip_type == LORA_CHIP_SX1276) {
        /* See chapter 5.5.5 of the data sheet */
        stats->rssi = rssi_raw - 157 + (snr_raw < 0 ? snr_raw / 4 : 0);
    }
    stats->crc_error =
        (lm_read_reg(modem, REG127X_LORA_IRQFLAGS) & VAL127X_LORA_IRQFLAGS_PAYLOADCRCERROR) != 0;
}

lora_sf_t lm_get_sf(lora_modem_t *modem)
{
    return (lora_sf_t)(lm_read_reg_masked(modem, REG127X_LORA_MODEMCONFIG2,
            MSK127X_LORA_MODEMCONFIG2_SF) >> 4);
}

uint8_t lm_get_syncword(lora_modem_t *modem)
{
    return lm_read_reg(modem, REG127X_LORA_SYNCWORD);
}

bool lm_get_txcrc(lora_modem_t *modem)
{
    if (modem->chip_type == LORA_CHIP_SX1272) {
        return lm_read_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
            MSK1272_LORA_MODEMCONFIG1_RXPAYLOADCRC) ==
            VAL1272_LORA_MODEMCONFIG1_RXPAYLOADCRC_ON;
    }
    else if (modem->chip_type == LORA_CHIP_SX1276) {
        return lm_read_reg_masked(modem, REG127X_LORA_MODEMCONFIG2,
            MSK1276_LORA_MODEMCONFIG2_RXPAYLOADCRC) ==
            VAL1276_LORA_MODEMCONFIG2_RXPAYLOADCRC_ON;
    }
    return false;
}

void lm_set_invertiqrx(lora_modem_t *modem, bool invertiq)
{
    /* Eventhough the data sheet for the SX1276 only knows the 6th bit in
     * register 0x33, the reference implementation etc. configure the modem like
     * they configure the SX1272, so we do the same here.
     */
    lm_write_reg_masked(modem, REG127X_LORA_INVERTIQ,
        MSK1272_LORA_INVERTIQ_INVERTIQ_RX, invertiq ?
        VAL1272_LORA_INVERTIQ_INVERTIQ_RX_INVERTED :
        VAL1272_LORA_INVERTIQ_INVERTIQ_RX_DEFAULT);
    lm_write_reg_masked(modem, REG1272_LORA_INVERTIQ2,
        MSK1272_LORA_INVERTIQ2_INVERTIQ2, invertiq ?
        VAL1272_LORA_INVERTIQ2_INVERTIQ2_INVERTED :
        VAL1272_LORA_INVERTIQ2_INVERTIQ2_DEFAULT);
}

void lm_set_invertiqtx(lora_modem_t *modem, bool invertiq)
{
    lm_write_reg_masked(modem, REG127X_LORA_INVERTIQ,
        MSK1272_LORA_INVERTIQ_INVERTIQ_TX, invertiq ?
        VAL1272_LORA_INVERTIQ_INVERTIQ_TX_INVERTED :
        VAL1272_LORA_INVERTIQ_INVERTIQ_TX_DEFAULT);
}

void lm_set_opmode(lora_modem_t *modem, lora_opmode_t opmode)
{
    lm_write_reg_masked(modem, REG127X_OPMODE, MSK127X_OPMODE_MODE, opmode);
}

void lm_set_modulation(lora_modem_t *modem, lora_modulation_t mod) {
    lm_write_reg(modem, REG127X_OPMODE,
        mod == LORA_MODULATION_LORA ?
            VAL127X_OPMODE_MODULATION_LORA :
            VAL127X_OPMODE_MODULATION_FSK
    );
}

void lm_set_frequency(lora_modem_t *modem, uint32_t freq) {
    uint64_t frf = (uint64_t)(((uint64_t)freq) << 19) / 32000000;
    lm_write_reg(modem, REG127X_FRFMSB, (uint8_t)(frf>>16) );
    lm_write_reg(modem, REG127X_FRFMID, (uint8_t)(frf>> 8) );
    lm_write_reg(modem, REG127X_FRFLSB, (uint8_t)(frf>> 0) );
}

void lm_set_bandwidth(lora_modem_t *modem, lora_bandwidth_t bw)
{
    if (modem->chip_type == LORA_CHIP_SX1276) {
        uint8_t bwVal = VAL1276_LORA_MODEMCONFIG1_BW125;
        if (bw == LORA_BANDWIDTH_250KHZ) {
            bwVal = VAL1276_LORA_MODEMCONFIG1_BW250;
        }
        else if (bw == LORA_BANDWIDTH_500KHZ) {
            bwVal = VAL1276_LORA_MODEMCONFIG1_BW500;
        }
        lm_write_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
                MSK1276_LORA_MODEMCONFIG1_BW, bwVal);
    }
    else if (modem->chip_type == LORA_CHIP_SX1272) {
        uint8_t bwVal = VAL1272_LORA_MODEMCONFIG1_BW125;
        if (bw == LORA_BANDWIDTH_250KHZ) {
            bwVal = VAL1272_LORA_MODEMCONFIG1_BW250;
        }
        else if (bw == LORA_BANDWIDTH_500KHZ) {
            bwVal = VAL1272_LORA_MODEMCONFIG1_BW500;
        }
        lm_write_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
                MSK1272_LORA_MODEMCONFIG1_BW, bwVal);
    }
}

void lm_set_codingrate(lora_modem_t *modem, lora_codingrate_t cr)
{
    if (modem->chip_type == LORA_CHIP_SX1276) {
        uint8_t crVal = (cr - 4) << 1;
        lm_write_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
                MSK1276_LORA_MODEMCONFIG1_CR, crVal);
    }
    else if (modem->chip_type == LORA_CHIP_SX1272) {
        uint8_t crVal = (cr - 4) << 3;
        lm_write_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
                MSK1272_LORA_MODEMCONFIG1_CR, crVal);
    }
}

void lm_set_explicitheader(lora_modem_t *modem, bool explicitheader)
{
    if (modem->chip_type == LORA_CHIP_SX1276) {
        lm_write_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
            MSK1276_LORA_MODEMCONFIG1_IMPLICIT_HDR, explicitheader ?
            VAL1276_LORA_MODEMCONFIG1_IMPLICIT_HDR_OFF :
            VAL1276_LORA_MODEMCONFIG1_IMPLICIT_HDR_ON
        );
    }
    else if (modem->chip_type == LORA_CHIP_SX1272) {
        lm_write_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
            MSK1272_LORA_MODEMCONFIG1_IMPLICIT_HDR, explicitheader ?
            VAL1272_LORA_MODEMCONFIG1_IMPLICIT_HDR_OFF :
            VAL1272_LORA_MODEMCONFIG1_IMPLICIT_HDR_ON
        );
    }
}

void lm_set_sf(lora_modem_t *modem, lora_sf_t sf)
{
    uint8_t sfVal = sf << 4;
    lm_write_reg_masked(modem, REG127X_LORA_MODEMCONFIG2,
            MSK127X_LORA_MODEMCONFIG2_SF, sfVal);
}

void lm_set_syncword(lora_modem_t *modem, uint8_t syncword)
{
    lm_write_reg(modem, REG127X_LORA_SYNCWORD, syncword);
}

void lm_set_agc_autoon(lora_modem_t *modem, bool on)
{
    uint8_t val = on ? 0xff : 0x00;
    if (modem->chip_type == LORA_CHIP_SX1276) {
        lm_write_reg_masked(modem, REG1276_LORA_MODEMCONFIG3,
                MSK1276_LORA_MODEMCONFIG3_AGCAUTOON, val);
    }
    else {
        lm_write_reg_masked(modem, REG127X_LORA_MODEMCONFIG2,
                MSK1272_LORA_MODEMCONFIG2_AGCAUTOON, val);
    }
}

void lm_set_hop_period(lora_modem_t *modem, uint8_t hop_period)
{
    lm_write_reg(modem, REG127X_LORA_HOPPERIOD, hop_period);
}

void lm_set_max_payload(lora_modem_t *modem, uint8_t length)
{
    lm_write_reg(modem, REG127X_LORA_MAXPAYLOADLENGTH, length);
}

void lm_set_lna(lora_modem_t *modem, lora_lna_gain_t gain, bool boost) {
    lm_write_reg_masked(modem, REG127X_LNA, MSK127X_LNA_GAIN, gain << 5);
    lm_write_reg_masked(modem, REG127X_LNA, MSK127X_LNA_BOOST,
            boost ? VAL127X_LNA_BOOST_ON : VAL127X_LNA_BOOST_OFF);
}

void lm_set_paconfig(lora_modem_t *modem, bool pa_boost,
        uint8_t pwr_max, int16_t pwr_out)
{
    uint8_t v = 0x00;
    if (pa_boost) {
        v |= VAL127X_PACONFIG_PASELECT_PABOOST;
    }

    if (modem->chip_type == LORA_CHIP_SX1272) {
        // With pa_boost: pwr_out =  2+reg[3:0] dBm
        // Without:       pwr_out = -1+reg[3:0] dBm
        int16_t p = ((pwr_out + (pa_boost ? -20 : 10)) / 10);
        p = (p > 0 ? (p < 15 ? p : 15) : 0);
        v |= (p | MSK127X_PACONFIG_OUTPUTPOWER);
    }
    else if(modem->chip_type == LORA_CHIP_SX1276) {
        // Configure max power. max_pwr = 10.8+0.6*reg[6:4]
        uint8_t m = (pwr_max > 108 ? pwr_max - 108 : 0) / 6;
        m = (m > 0x07 ? 0x07 : m);
        v |= (m << 4) | MSK1276_PACONFIG_MAXPOWER;

        // With pa_boost: pwr_out = 17-(15-reg[3:0])
        // Without:       pwr_out = pa_max-(15-reg[3:0])
        int16_t p = pwr_out - (pa_boost ? 170 : pwr_max) / 10;
        p = (p > 0 ? (p < 15 ? p : 15) : 0);
        v |= (p | MSK127X_PACONFIG_OUTPUTPOWER);
    }

    lm_write_reg(modem, REG127X_PACONFIG, v);
}

void lm_set_padac(lora_modem_t *modem, bool enabled)
{
    if (modem->chip_type == LORA_CHIP_SX1272) {
        lm_write_reg_masked(modem, REG1272_PADAC, MSK127X_PADAC_PADAC,
            enabled ? VAL127X_PADAC_PADAC_DEFAULT : VAL127X_PADAC_PADAC_DEFAULT
        );
    }
    else if (modem->chip_type == LORA_CHIP_SX1276) {
        lm_write_reg_masked(modem, REG1276_PADAC, MSK127X_PADAC_PADAC,
            enabled ? VAL127X_PADAC_PADAC_DEFAULT : VAL127X_PADAC_PADAC_DEFAULT
        );
    }
}

void lm_set_txcrc(lora_modem_t *modem, bool txcrc)
{
    if (modem->chip_type == LORA_CHIP_SX1272) {
        lm_write_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
            MSK1272_LORA_MODEMCONFIG1_RXPAYLOADCRC, txcrc ?
            VAL1272_LORA_MODEMCONFIG1_RXPAYLOADCRC_ON :
            VAL1272_LORA_MODEMCONFIG1_RXPAYLOADCRC_OFF
        );
    }
    else if (modem->chip_type == LORA_CHIP_SX1276) {
        lm_write_reg_masked(modem, REG127X_LORA_MODEMCONFIG2,
            MSK1276_LORA_MODEMCONFIG2_RXPAYLOADCRC, txcrc ?
            VAL1276_LORA_MODEMCONFIG2_RXPAYLOADCRC_ON :
            VAL1276_LORA_MODEMCONFIG2_RXPAYLOADCRC_OFF
        );
    }
}

void lm_update_dr_optimize(lora_modem_t *modem, lora_sf_t sf, lora_bandwidth_t bw)
{
    bool drOptimize = lm_calc_symboltime(sf, bw) >= 16000;
    if (modem->chip_type == LORA_CHIP_SX1272) {
        lm_write_reg_masked(modem, REG127X_LORA_MODEMCONFIG1,
            MSK1272_LORA_MODEMCONFIG1_LOWDATARATEOPTIMIZE, drOptimize ?
            VAL1272_LORA_MODEMCONFIG1_LOWDATARATEOPTIMIZE_ON :
            VAL1272_LORA_MODEMCONFIG1_LOWDATARATEOPTIMIZE_OFF
        );
    }
    else if (modem->chip_type == LORA_CHIP_SX1276) {
        lm_write_reg_masked(modem, REG1276_LORA_MODEMCONFIG3,
            MSK1276_LORA_MODEMCONFIG3_LOWDATARATEOPTIMIZE, drOptimize ?
            VAL1276_LORA_MODEMCONFIG3_LOWDATARATEOPTIMIZE_ON :
            VAL1276_LORA_MODEMCONFIG3_LOWDATARATEOPTIMIZE_OFF
        );
    }
}
