#include "lora_modem_sniffer.h"
#include "lora_modem_internal.h"
#include "lora_modem_irq.h"
#include "lora_registers_common.h"
#include "lora_modem_jammer.h"

#ifdef MODULE_LORA_MODEM_JAMMER_UDP
#include "net/sock/udp.h"
#endif

#include "periph/spi.h"
#ifdef MODULE_PERIPH_GPIO
#include "periph/gpio.h"
#endif
#include "xtimer.h"

#if ENABLE_DEBUG_MODEM_ALL
#define ENABLE_DEBUG (1)
#else
#define ENABLE_DEBUG (0)
#endif
#include "debug.h"

/** Sniffer timeout, in microseconds */
#define SNIFFER_TIMEOUT (3000000) /* 3s should be sufficient wrt. max mask_len */

static void _signal_jammer(lora_modem_t *modem);

#ifdef MODULE_LORA_MODEM_JAMMER_UDP
static const char jammsg[] = {0x42};
#endif

#if ENABLE_DEBUG
#pragma message("With logging enabled, the performance of the jammer is reduced significantly!")
#endif

int lm_setup_sniffing(lora_modem_t *modem)
{
    /* Activate the valid header interrupt */
    if (SPI_ACQUIRE(modem) != SPI_OK) {
        DEBUG("%s: Activating sniffer failed (SPI)\n", thread_getname(thread_getpid()));
        return LORA_MODEM_ERROR_SPI;
    }
    lm_set_opmode(modem, LORA_OPMODE_STANDBY);
    /* Pushing the modem to standby resets rxbyteaddr, but you cannot read it
     * until you received something.
     */
    modem->lora_sniffer_last_rxbyteaddr =
        lm_read_reg(modem, REG127X_LORA_FIFORXBASEADDR);

    lm_enable_irq(modem, LORA_IRQ_VALID_HEADER, isr_valid_header_to_sniffer);
    if (modem->sniffer_to_rxbuf) {
        lm_enable_irq(modem, LORA_IRQ_RXDONE_AND_CRC, isr_frame_to_buffer);
    }
    else {
        /* Exit condition for the sniffer loop and required to latch the fifo address */
        lm_enable_irq(modem, LORA_IRQ_RXDONE, NULL);
    }

    /* And start the sniffer */
    DEBUG("%s: Going to rx_continuous for sniffing\n", thread_getname(thread_getpid()));
    lm_set_opmode(modem, LORA_OPMODE_RXCONTINUOUS);
    SPI_RELEASE(modem);

    modem->active_tasks.sniffer = true;
    /* Mutually exclusive */
    modem->active_tasks.rx = false;
    /* Irreconcilable with rxcontinuous */
    modem->active_tasks.tx = false;
    /* Receiving removes jamming preparation, if any */
    modem->jammer_prepared = false;
    return 0;
}

void lm_start_sniffing(lora_modem_t *modem)
{
    /* Shortcut: No pattern matching? Signal jammer as fast as possible */
    if (modem->sniffer_mask_len == 0) {
        DEBUG("%s: valid_header + mask_length==0! Jamming!\n", thread_getname(thread_getpid()));
        _signal_jammer(modem);
        /** Receiving is done by the usual rx done callback */
    }
    else {
        int spi_res = SPI_ACQUIRE(modem);
        if (spi_res == SPI_OK) {
            /* true as long as we have something different */
            bool match = true;
            uint8_t bytes_read = 0;
            uint8_t frame[modem->sniffer_mask_len];
            /* Set the FIFO pointer to the next  */
            uint8_t last_fiforxbyteaddr = modem->lora_sniffer_last_rxbyteaddr;
            lm_write_reg(modem, REG127X_LORA_FIFOADDRPTR, last_fiforxbyteaddr);
            SPI_RELEASE(modem);
            DEBUG("%s: REG127X_LORA_FIFOADDRPTR=0x%02x\n", thread_getname(thread_getpid()),
                last_fiforxbyteaddr);
            uint64_t timeout = xtimer_now_usec64() + SNIFFER_TIMEOUT;
            bool timeout_reached = false;
            modem->lora_sniffer_rxdone = false;
            do {
                uint8_t idx = bytes_read;
                /* We _want_ this to overflow, that's why we use uint8_t.
                 * The mask length is limited anyway, so bytes_read will not get
                 * near the maximum value, but the internal FIFO of the modem
                 * has a size of 256 byte, so if RxByteAddr rolls over, we want
                 * that, too.
                 */
                if (SPI_ACQUIRE(modem) == SPI_OK) {
                    last_fiforxbyteaddr = lm_read_reg(modem, REG127X_LORA_FIFORXBYTEADDR);
                    bytes_read = last_fiforxbyteaddr - modem->lora_sniffer_last_rxbyteaddr;
                    /* Using "or" not to unset the flag if the isr has set it */
                    modem->lora_sniffer_rxdone |= (lm_read_reg(modem, REG127X_LORA_IRQFLAGS) &
                        VAL127X_LORA_IRQFLAGS_RXDONE) > 0;
                    if (bytes_read > idx) {
                        DEBUG("%s: bytes_read = %d\n", thread_getname(thread_getpid()), bytes_read);
                        size_t count = bytes_read - idx;
                        if (bytes_read >= sizeof(frame)) {
                            count = sizeof(frame)-idx;
                        }
                        if (count > 0) {
                            lm_read_reg_burst(modem, REG127X_FIFO, &(frame[idx]), count);
                        }
                    }
                    SPI_RELEASE(modem);
                }
                else {
                    DEBUG("%s: Couldn't acquire SPI in sniffer loop\n", thread_getname(thread_getpid()));
                }
                while(idx < bytes_read && idx < modem->sniffer_mask_len) {
                    match = match &&
                        (frame[idx] & modem->sniffer_mask[idx]) == modem->sniffer_pattern[idx];
                    idx += 1;
                }
                timeout_reached = xtimer_now_usec64() > timeout;
            } while(match && bytes_read < modem->sniffer_mask_len &&
                !timeout_reached && !modem->lora_sniffer_rxdone);
            if (timeout_reached) {
                DEBUG("%s: Sniffer timeout reached\n", thread_getname(thread_getpid()));
            }
#if ENABLE_DEBUG
            size_t limit = bytes_read < modem->sniffer_mask_len ? bytes_read : modem->sniffer_mask_len;
            DEBUG("Frame:  ");
            for(size_t n = 0; n < limit; n++) DEBUG(" %02x", frame[n]);
            DEBUG("\nPattern:");
            for(size_t n = 0; n < limit; n++) DEBUG(" %02x", modem->sniffer_pattern[n]);
            DEBUG("\nMask:   ");
            for(size_t n = 0; n < limit; n++) DEBUG(" %02x", modem->sniffer_mask[n]);
            DEBUG("\n");
#endif
            DEBUG("%s: Sniffing done, evaluating...\n", thread_getname(thread_getpid()));
            if (match && bytes_read >= modem->sniffer_mask_len) {
                DEBUG("%s: Pattern matched! Jamming!\n", thread_getname(thread_getpid()));
                _signal_jammer(modem);
                DEBUG("%s: Jamming done, returning to modem event loop\n", thread_getname(thread_getpid()));
            }
            else {
                DEBUG("%s: Pattern mismatched\n", thread_getname(thread_getpid()));
            }
        }
    }
}

int lm_stop_sniffer(lora_modem_t *modem)
{
    int spi_res = SPI_ACQUIRE(modem);
    if (spi_res == SPI_OK) {
        lm_disable_irq(modem, LORA_IRQ_VALID_HEADER);
        lm_disable_irq(modem, LORA_IRQ_RXDONE);
        lm_set_opmode(modem, LORA_OPMODE_STANDBY);
        modem->lora_sniffer_last_rxbyteaddr =
            lm_read_reg(modem, REG127X_LORA_FIFORXBASEADDR);
        modem->active_tasks.sniffer = false;
        SPI_RELEASE(modem);
    }
    else {
        DEBUG("%s: Could not stop sniffer (SPI)\n", thread_getname(thread_getpid()));
    }
    return spi_res;
}

static void _signal_jammer(lora_modem_t *modem)
{
    switch(modem->sniffer_action) {
        case LORA_SNIFFER_ACTION_INTERNAL:
            lm_jammer_jam_frame(modem);
            break;
#ifdef MODULE_PERIPH_GPIO
        case LORA_SNIFFER_ACTION_GPIO:
            gpio_set(modem->gpio_sniffer);
            xtimer_usleep(10000);
            gpio_clear(modem->gpio_sniffer);
            break;
#endif
#ifdef MODULE_LORA_MODEM_JAMMER_UDP
        case LORA_SNIFFER_ACTION_UDP: {
            sock_udp_ep_t remote;
            memcpy(remote.addr.ipv6, modem->sniffer_addr, sizeof(remote.addr.ipv6));
            remote.port = UDP_JAMMER_PORT;
            remote.family = AF_INET6;
            remote.netif = 8;
            int udpres = sock_udp_send(NULL, jammsg, sizeof(jammsg), &remote);
            if (udpres <= 0) {
                DEBUG("%s: udpres returned failure: %d\n",
                    thread_getname(thread_getpid()), udpres);
            }
            }
            break;
#endif
        default:
            break;
    }
}
