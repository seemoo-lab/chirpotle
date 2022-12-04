#include "lora_modem_jammer.h"
#include "lora_modem_internal.h"
#include "lora_modem_irq.h"
#include "lora_registers_common.h"

#ifdef MODULE_LORA_MODEM_JAMMER_UDP
#include "net/sock/udp.h"
#endif

#include "thread.h"

#if ENABLE_DEBUG_MODEM_ALL
#define ENABLE_DEBUG (1)
#else
#define ENABLE_DEBUG (0)
#endif
#include "debug.h"

#ifdef MODULE_LORA_MODEM_JAMMER_UDP
/**
 * Thread function for the UDP jammer. Waits for any UDP packet on port 9001 and
 * once one is received, triggers the jammer.
 *
 * Setting active_tasks.jammer to false on the modem (or selecting another
 * trigger) will automatically stop the thread.
 *
 * Standalone testing using netcat + SDR:
 * echo -n "jam" | ncat -6 -u -n -w1 fd01::1337:1 9001
 */
void *_udp_thread(void *);
#endif

/**
 * Does the actual preparation for the jamming, so that the jammer is ready to
 * jam. Expects SPI to be aquired.
 *
 * @param[in] modem Modem Descriptor
 * @param[in] fstx  If the modem should be send to fstx afterwards
 */
static void _prepare_jamming(lora_modem_t *modem, bool fstx);

void lm_jammer_disable_trigger(lora_modem_t *modem)
{
    /* As the udp thread tracks this value, it will stop. */
    modem->jammer_trigger = LORA_JAMMER_TRIGGER_NONE;
    modem->active_tasks.jammer = false;
    if (modem->jammer_prepared) {
        if (SPI_ACQUIRE(modem)==SPI_OK) {
            lm_set_opmode(modem, LORA_OPMODE_STANDBY);
            SPI_RELEASE(modem);
        }
        modem->jammer_prepared = false;
    }
}

void lm_jammer_enable_trigger(lora_modem_t *modem, lora_jammer_trigger_t trigger)
{
    if (trigger == LORA_JAMMER_TRIGGER_UDP) {
#ifdef MODULE_LORA_MODEM_JAMMER_UDP
        if (modem->udp_thread_pid == KERNEL_PID_UNDEF) {
            memset(modem->udp_thread_stack, 0, sizeof(modem->udp_thread_stack));
            modem->udp_thread_pid = thread_create(
                modem->udp_thread_stack,
                sizeof(modem->udp_thread_stack),
                THREAD_PRIORITY_IDLE - 3,
                0,
                _udp_thread,
                modem,
                "jamudp"
            );
        }
        else {
            DEBUG("%s: Not starting a UDP thread, it already exists",
                thread_getname(thread_getpid()));
        }
#endif
    }
    /** For GPIO, it's sufficient to just set the variable */
    modem->jammer_trigger = trigger;
    modem->active_tasks.jammer = true;
}

void lm_jammer_jam_frame(lora_modem_t *modem)
{
    if (!modem->jammer_active) {
        modem->jammer_active = true;
        if (SPI_ACQUIRE(modem) == SPI_OK) {
            _prepare_jamming(modem, false);
            lm_set_opmode(modem, LORA_OPMODE_TX);
            DEBUG("%s: Jammed!\n", thread_getname(thread_getpid()));
            modem->lora_sniffer_last_rxbyteaddr =
                lm_read_reg(modem, REG127X_LORA_FIFORXBASEADDR);
            SPI_RELEASE(modem);
            modem->jammer_prepared = false;
        }
        else {
            DEBUG("%s: Jamming failed (SPI error)\n", thread_getname(thread_getpid()));
        }
    }
}

void lm_jammer_prepare_jamming(lora_modem_t *modem)
{
    if (modem->active_tasks.jammer == true &&
#ifdef MODULE_PERIPH_GPIO_IRQ
        modem->active_tasks.prepared_tx == false &&
#endif
        modem->active_tasks.rx == false &&
        modem->active_tasks.sniffer == false &&
        modem->active_tasks.tx == false) {
        if (!(modem->jammer_prepared)) {
            DEBUG("%s: Preparing jammer\n", thread_getname(thread_getpid()));
            if (SPI_ACQUIRE(modem) == SPI_OK) {
                _prepare_jamming(modem, true);
                SPI_RELEASE(modem);
                DEBUG("%s: Jammer ready for action\n", thread_getname(thread_getpid()));
            }
            else {
                DEBUG("%s: Couldn't prepare jammer (SPI)\n", thread_getname(thread_getpid()));
            }
        }
    }
    else {
        modem->jammer_prepared = false;
    }
}

static void _prepare_jamming(lora_modem_t *modem, bool fstx)
{
    lm_set_opmode(modem, LORA_OPMODE_STANDBY);
    lm_enable_irq(modem, LORA_IRQ_TXDONE, isr_reset_state_after_tx);
    lm_write_reg(modem, REG127X_LORA_PAYLOADLENGTH, modem->jammer_plength);
    modem->jammer_prepared = true;

    if (fstx) {
        lm_set_opmode(modem, LORA_OPMODE_FSTX);
        /* If it's not fstx we'll go to tx and reset the value after that */
        modem->lora_sniffer_last_rxbyteaddr =
            lm_read_reg(modem, REG127X_LORA_FIFORXBASEADDR);
    }
}

#ifdef MODULE_LORA_MODEM_JAMMER_UDP
void *_udp_thread(void *arg)
{
    lora_modem_t *modem = (lora_modem_t*)arg;

    sock_udp_ep_t local = SOCK_IPV6_EP_ANY;
    sock_udp_t sock;
    local.port = UDP_JAMMER_PORT;

    if (sock_udp_create(&sock, &local, NULL, 0) < 0) {
        DEBUG("%s: Error starting UDP thread\n",
            thread_getname(thread_getpid()));
        return NULL;
    }
    DEBUG("%s: Started UDP thread\n", thread_getname(thread_getpid()));
    uint8_t dummy[50] = { 0 };
    msg_t msg_trigger;
    msg_trigger.type = LORAMODEM_MTYPE_TRIGGER_JAMMER;
    while (modem->active_tasks.jammer &&
        modem->jammer_trigger == LORA_JAMMER_TRIGGER_UDP) {
        int res = sock_udp_recv(&sock, dummy, sizeof(dummy), 1000, NULL);
        if (res > 0 && modem->jammer_trigger == LORA_JAMMER_TRIGGER_UDP) {
            DEBUG("%s: Got UDP trigger\n", thread_getname(thread_getpid()));
            msg_send(&msg_trigger, modem->modem_thread_pid);
        }
        else if (res < 0) {
            bool stop = false;
            switch(res) {
                case -ENOBUFS:
                case -ENOMEM:
                case -EPROTO:
                case -ETIMEDOUT:
                case -EAGAIN:
                    break;
                default:
                    DEBUG("%s: Error during udp_recv(), rc=%d\n",
                        thread_getname(thread_getpid()), res);
            }
            if (stop) {
                break;
            }
        }
    }
    DEBUG("%s: Stop UDP server\n", thread_getname(thread_getpid()));
    sock_udp_close(&sock);
    modem->udp_thread_pid = KERNEL_PID_UNDEF;
    return NULL;
}
#endif
