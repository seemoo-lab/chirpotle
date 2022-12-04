#include "lora_modem_transmitter.h"

#include "lora_modem_internal.h"
#include "lora_modem_irq.h"
#include "lora_modem_jammer.h"
#include "lora_modem_receiver.h"
#include "lora_modem_sniffer.h"
#include "lora_registers_common.h"

#if ENABLE_DEBUG_MODEM_ALL
#define ENABLE_DEBUG (1)
#else
#define ENABLE_DEBUG (0)
#endif
#include "debug.h"

int lm_stop_transmission(lora_modem_t *modem)
{
    DEBUG("%s: Stopping ongoing transmission\n", thread_getname(thread_getpid()));
    int spi_res;
    if ((spi_res = SPI_ACQUIRE(modem)) == SPI_OK) {
        lm_set_opmode(modem, LORA_OPMODE_STANDBY);
        modem->lora_sniffer_last_rxbyteaddr =
            lm_read_reg(modem, REG127X_LORA_FIFORXBASEADDR);
        modem->active_tasks.tx = false;
        lora_irq_cb txdone = lm_get_irq_cb(modem, LORA_IRQ_TXDONE);

        lm_disable_irq(modem, LORA_IRQ_TXDONE);
        if (txdone != NULL) {
            txdone(modem);
        }
        SPI_RELEASE(modem);
        return 0;
    }
    DEBUG("%s: Couldn't acquire SPI, couldn't stop transmission\n", thread_getname(thread_getpid()));
    return spi_res;
}

void lm_restore_after_transmit(lora_modem_t *modem)
{
    DEBUG("%s: tx_done -> Restoring modem state\n", thread_getname(thread_getpid()));
    modem->active_tasks.tx = false;
    if (modem->active_tasks.rx) {
        if (lm_enable_receiver(modem, false) == 0) {
            DEBUG("%s: Restored rx\n", thread_getname(thread_getpid()));
        }
        else {
            DEBUG("%s: Restoring rx failed\n", thread_getname(thread_getpid()));
            modem->active_tasks.rx = false;
        }
    }
    if (modem->active_tasks.sniffer) {
        if (lm_setup_sniffing(modem) == 0) {
            DEBUG("%s: Restored sniffer\n", thread_getname(thread_getpid()));
        }
        else {
            DEBUG("%s: Restoring sniffer failed\n", thread_getname(thread_getpid()));
            modem->active_tasks.sniffer = false;
        }
    }
    if (modem->active_tasks.jammer) {
        lm_jammer_enable_trigger(modem, modem->jammer_trigger);
        DEBUG("%s: Restored jammer\n", thread_getname(thread_getpid()));
    }
#ifdef MODULE_PERIPH_GPIO_IRQ
    if (modem->active_tasks.prepared_tx) {
        lora_frame_t frame;
        frame.length = modem->gpio_tx_len;
        frame.payload = modem->gpio_tx_payload;
        lm_prepare_transmission(modem, &frame);
    }
#endif
    DEBUG("%s: Restoring done\n", thread_getname(thread_getpid()));
}

#ifdef MODULE_PERIPH_GPIO_IRQ
void lm_disable_gpio_tx(lora_modem_t *modem)
{
    modem->gpio_tx_len = 0;
    modem->gpio_tx_prepared = false;
    modem->active_tasks.prepared_tx = false;
}

void lm_prepare_transmission(lora_modem_t *modem, lora_frame_t *frame)
{
    if (SPI_ACQUIRE(modem) == SPI_OK) {
        lm_write_reg(modem, REG127X_LORA_PAYLOADLENGTH, frame->length);
        lm_write_reg(modem, REG127X_LORA_FIFOADDRPTR,
            lm_read_reg(modem, REG127X_LORA_FIFOTXBASEADDR));
        lm_write_reg_burst(modem, REG127X_FIFO, frame->payload, frame->length);
        SPI_RELEASE(modem);
        modem->gpio_tx_prepared = true;
        modem->active_tasks.prepared_tx = true;
    }
}

void lm_transmit_prepared_frame(lora_modem_t *modem)
{
    if (modem->gpio_tx_prepared) {
        if (SPI_ACQUIRE(modem) == SPI_OK) {
            
            // Interrupt to enable the tx done interrupt that restores the state.
            // No need to clear rx done, as its mutual exclusive to tx done
            // The interrupt will take care of re-preparation
            lm_enable_irq(modem, LORA_IRQ_TXDONE, isr_reset_state_after_tx);
            lm_disable_irq(modem, LORA_IRQ_VALID_HEADER);

            lm_set_opmode(modem, LORA_OPMODE_TX);
            modem->gpio_tx_prepared = false;

            SPI_RELEASE(modem);
        }
    } else {
        DEBUG("%s: Could not transmit prepared frame, modem not prepared\n", thread_getname(thread_getpid()));
    }
}
#endif

int lm_transmit_now(lora_modem_t *modem, lora_frame_t *frame, bool blocking)
{
    int spi_res;
    if ((spi_res = SPI_ACQUIRE(modem)) == SPI_OK) {
        modem->active_tasks.tx = true;
        modem->tx_done_ack_pid = blocking ? thread_getpid() : KERNEL_PID_UNDEF;

        // Goto standby for preparation
        lm_set_opmode(modem, LORA_OPMODE_STANDBY);
        modem->lora_sniffer_last_rxbyteaddr =
            lm_read_reg(modem, REG127X_LORA_FIFORXBASEADDR);

        // Interrupt to enable the tx done interrupt that restores the state.
        // No need to clear rx done, as its mutual exclusive to tx done
        lm_enable_irq(modem, LORA_IRQ_TXDONE, isr_reset_state_after_tx);
        lm_disable_irq(modem, LORA_IRQ_VALID_HEADER);

        // Set length
        lm_write_reg(modem, REG127X_LORA_PAYLOADLENGTH, frame->length);

        DEBUG("Transmitting: ");
        for(unsigned int n = 0; n < frame->length; n++) {
            DEBUG(" %02x", frame->payload[n]);
        }
        DEBUG("\n");

        // Write message
        lm_write_reg(modem, REG127X_LORA_FIFOADDRPTR,
            lm_read_reg(modem, REG127X_LORA_FIFOTXBASEADDR));

        lm_write_reg_burst(modem, REG127X_FIFO, frame->payload, frame->length);

        // Send
        lm_set_opmode(modem, LORA_OPMODE_TX);

        SPI_RELEASE(modem);

        if (blocking) {
            DEBUG("%s: Waiting for tx_done before returning\n", thread_getname(thread_getpid()));
            xtimer_set_wakeup(&(modem->tx_done_timer), 5000000, thread_getpid());
            thread_sleep();
        }

        return 0;
    }
    return LORA_MODEM_ERROR_SPI;
}
