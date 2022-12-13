#include "lora_modem_receiver.h"
#include "lora_modem_internal.h"
#include "lora_modem_irq.h"
#include "lora_modem_transmitter.h"
#include "lora_registers_common.h"

#include <string.h>

#include "thread.h"

#if ENABLE_DEBUG_MODEM_ALL
#define ENABLE_DEBUG (1)
#else
#define ENABLE_DEBUG (0)
#endif
#include "debug.h"

int lm_disable_receiver(lora_modem_t *modem)
{
    int spi_res = SPI_ACQUIRE(modem);
    if (spi_res == SPI_OK) {
        /* Go to standby */
        lm_set_opmode(modem, LORA_OPMODE_STANDBY);

        /* Disable interrupts */
        lm_disable_irq(modem, LORA_IRQ_RXDONE);
        lm_disable_irq(modem, LORA_IRQ_VALID_HEADER);

        modem->active_tasks.rx = false;
        SPI_RELEASE(modem);
        DEBUG("%s: Receiver has been stopped.\n", thread_getname(thread_getpid()));
    }
    return spi_res;
}

int lm_enable_receiver(lora_modem_t *modem, bool clear_rxbuf)
{
    if (SPI_ACQUIRE(modem) == SPI_OK) {
        /* Go to standby to configure the modem */
        lm_set_opmode(modem, LORA_OPMODE_STANDBY);

        /* Configure the modem's fifo */
        uint8_t fiforxbaseaddr = lm_read_reg(modem, REG127X_LORA_FIFORXBASEADDR);
        modem->lora_sniffer_last_rxbyteaddr = fiforxbaseaddr;
        lm_write_reg(modem, REG127X_LORA_FIFOADDRPTR, fiforxbaseaddr);

        /* Clear buffer for a fresh start */
        if (clear_rxbuf) {
            mutex_lock(&(modem->mutex_ringbuf_recv));
            ringbuffer_init(&(modem->ringbuf_recv), modem->buf_recv, LORA_RECEIVE_BUFFER_SIZE);
            modem->frames_dropped = false;
            mutex_unlock(&(modem->mutex_ringbuf_recv));
        }

        /* Enable the interrupt that handles the messages */
        lm_enable_irq(modem, LORA_IRQ_RXDONE_AND_CRC, isr_frame_to_buffer);
        /* Enable valid_header with no-op, so that at least the timestamp will be recoreded */
        lm_enable_irq(modem, LORA_IRQ_VALID_HEADER, NULL);

        /* Go to rx continous */
        lm_set_opmode(modem, LORA_OPMODE_RXCONTINUOUS);
        SPI_RELEASE(modem);
        modem->active_tasks.rx = true;
        /* Mutually exclusive */
        modem->active_tasks.sniffer = false;
        /* Irreconcilable with rxcontinuous */
        modem->active_tasks.tx = false;
        /* Receiving removes jamming preparation, if any */
        modem->jammer_prepared = false;
        return 0;
    }
    return -1;
}

void lm_frame_to_buffer(lora_modem_t *modem)
{
    ringbuffer_t *rb = &(modem->ringbuf_recv);

    if (SPI_ACQUIRE(modem) == SPI_OK) {
        /* Get frame length from the modem */
        uint8_t frame_length = lm_get_explicitheader(modem) ?
            lm_read_reg(modem, REG127X_LORA_RXNBBYTES) :
            lm_read_reg(modem, REG127X_LORA_PAYLOADLENGTH);
        DEBUG("%s: RxNBytes=%d\n", thread_getname(thread_getpid()), frame_length);
        /* Set modem FIFO to start of frame */
        lm_write_reg(modem, REG127X_LORA_FIFOADDRPTR,
            lm_read_reg(modem, REG127X_LORA_RXCURRENTADDR));
        /* Get RX stats */
        lora_rx_stats_t stats;
        lm_get_rx_stats(modem, &stats);
        /* Reset CRC error flag */
        lm_write_reg_masked(modem, REG127X_LORA_IRQFLAGS, VAL127X_LORA_IRQFLAGS_PAYLOADCRCERROR, 0xff);
        /* Store the new rxbyteaddr so that it's available for the jammer */
        modem->lora_sniffer_last_rxbyteaddr =
            lm_read_reg(modem, REG127X_LORA_FIFORXBYTEADDR);

        /* Payload length field + payload + lora_rx_stats size */
        size_t req_buffer_space = 1 + frame_length + sizeof(lora_rx_stats_t);
        DEBUG("%s: Trying to lock ringbuffer\n", thread_getname(thread_getpid()));
        mutex_lock(&(modem->mutex_ringbuf_recv));
        DEBUG("%s: Locked ringbuffer\n", thread_getname(thread_getpid()));
        /* Assure we have enough space by dropping the oldest frames */
        while (ringbuffer_get_free(rb) < req_buffer_space) {
            modem->frames_dropped = true;
            int buf_next_frame_len = ringbuffer_peek_one(rb);
            if (buf_next_frame_len < 0) {
                /* If the buffer is empty and we don't have enough space, we can't
                * do anything but drop the frame. This cannot happen if
                * LORA_RECEIVE_BUFFER_SIZE is > 256+sizeof(lora_rx_stats_t) */
                DEBUG("%s: Cannot store frame, too big for ringbuffer\n",
                    thread_getname(thread_getpid()));
                mutex_unlock(&(modem->mutex_ringbuf_recv));
                SPI_RELEASE(modem);
                return;
            }
            DEBUG("%s: Dropping frame of %d bytes from receive buffer\n",
                thread_getname(thread_getpid()), buf_next_frame_len);
            buf_next_frame_len += 1 + sizeof(lora_rx_stats_t);
            ringbuffer_remove(rb, buf_next_frame_len);
        }

        /* Write payload size to ringbuffer */
        ringbuffer_add_one(rb, (char)frame_length);
        /* Read payload from transceiver and write it to the ringbuffer */
        size_t bytes_remaining = frame_length;
        uint8_t tmpbuf[sizeof(lora_rx_stats_t)];
        while (bytes_remaining > 0) {
            size_t n = (bytes_remaining > sizeof(tmpbuf) ?
                sizeof(tmpbuf) : bytes_remaining);
            memset(tmpbuf, 0, sizeof(tmpbuf));
            lm_read_reg_burst(modem, REG127X_FIFO, tmpbuf, n);
            DEBUG("_isr_frame_to_buffer: tmpbuf[] =");
            for(uint8_t x = 0; x < n; x++) {
                DEBUG(" %02x", tmpbuf[x]);
            }
            DEBUG("\n");
            size_t offset = 0;
            do {
                offset += ringbuffer_add(rb, (char*)&(tmpbuf[offset]), n - offset);
            } while (offset < n);
            bytes_remaining -= n;
            DEBUG("_isr_frame_to_buffer: wrote %d payload bytes to buffer\n", n);
        }

        /* Write rx stats to ringbuffer */
        bytes_remaining = sizeof(tmpbuf);
        memcpy(tmpbuf, &stats, sizeof(tmpbuf));
        size_t offset = 0;
        do {
            size_t n = ringbuffer_add(rb, (char*)(tmpbuf+offset), bytes_remaining-offset);
            DEBUG("_isr_frame_to_buffer: wrote %d rx_stats bytes to buffer\n", n);
            offset += n;
        } while (offset < bytes_remaining);

        DEBUG("%s: Added frame to buffer (%d bytes payload, %d bytes total)\n",
            thread_getname(thread_getpid()), frame_length,
            1 + frame_length + sizeof(lora_rx_stats_t));
        mutex_unlock(&(modem->mutex_ringbuf_recv));
        SPI_RELEASE(modem);
        DEBUG("%s: Released ringbuffer and SPI\n", thread_getname(thread_getpid()));
    }
#ifdef MODULE_PERIPH_GPIO_IRQ
    /* If in tx-prepare mode, restore it */
    if (modem->active_tasks.prepared_tx) {
        lora_frame_t frame;
        frame.payload = modem->gpio_tx_payload;
        frame.length = modem->gpio_tx_len;
        lm_prepare_transmission(modem, &frame);
    }
#endif
}