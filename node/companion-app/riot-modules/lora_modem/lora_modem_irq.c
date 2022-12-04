#include "lora_modem.h"
#include "lora_modem_irq.h"
#include "lora_modem_jammer.h"
#include "lora_registers_common.h"

#include <string.h>

#if ENABLE_DEBUG_MODEM_ALL
#define ENABLE_DEBUG (1)
#else
#define ENABLE_DEBUG (0)
#endif
#include "debug.h"

/** Used to create unique names for threads */
static uint8_t irq_thread_count = 0;

/** All IRQs used by this app */
#define IRQMASK ( VAL127X_LORA_IRQFLAGS_VALIDHEADER |\
        VAL127X_LORA_IRQFLAGS_RXDONE |\
        VAL127X_LORA_IRQFLAGS_TXDONE |\
        VAL127X_LORA_IRQFLAGS_PAYLOADCRCERROR )

#ifdef MODULE_PERIPH_GPIO
/**
 * Configures a GPIO line either as interrupt or as input
 *
 * @param[in]    gpio   GPIO line to configure
 * @param[out]   mode   Field to store the configuration result
 * @param[in]    cb     Callback to use as ISR
 * @param[in]    cbarg  Parameter for the ISR callback
 */
static void _init_gpio(gpio_t gpio, lora_dio_mode_t *mode, gpio_cb_t cb, void *cbarg);
#endif

/** Function for the interrupt handler thread. */
static void *_irqthread(void *arg);

/** Proxy function used by the irqthread to detect and handle rxdone interrupts */
static inline void _irqthread_handle_rxdone(lora_modem_t *modem,
    lora_irq_cb cb, uint64_t irqtime, uint8_t irqflags);

/** Proxy function used by the irqthread to detect and handle txdone interrupts */
static inline void _irqthread_handle_txdone(lora_modem_t *modem,
    lora_irq_cb cb, uint64_t irqtime, uint8_t irqflags);

/** Proxy function used by the irqthread to detect and handle validheader interrupts */
static inline void _irqthread_handle_validheader(lora_modem_t *modem,
    lora_irq_cb cb, uint64_t irqtime, uint8_t irqflags);

/**
 * If the GPIO module is availabe, we define a handler function for each
 * interrupt line of the transceiver (_isr_dioX). With hardware interrupts being
 * available, these functions are registered as interrupt handlers. Without
 * hardware interrupts (but with general GPIO access), we start the irqthread
 * and poll those lines and then call the handlers manually.
 *
 * Some boards, like the LoPy 4, map multiple DIO pins of the transceiver to a
 * single pin of the microcontroller. In that case, we can only register a
 * generic ISR (_isr_dio_all), but need to read the IRQFLAGS register via SPI
 * to determine what actually fired.
 *
 * An important thing to note is that the event (like RxDone, TxDone, ...) is
 * dynamically mapped to the DIO pin. So the functions below are all dispatcher
 * functions which identify the event that has been fired and then call the
 * event-based interrupt functions that are currently configured in the modem's
 * irq_config field.
 *
 * For all interrupts, the final action is to send a message to the modem
 * thread, which will then perform the relevant actions without being in ISR
 * context. The thread is scheduled in a way that it becomes first priority
 * after the ISR is left and the message that has been sent makes it runnable
 * again.
 */
#ifdef MODULE_PERIPH_GPIO
/* Interrupt dispatcher for DIO0 interrupts */
static void _isr_dio0(void *arg);
/* Interrupt dispatcher for DIO3 interrupts */
static void _isr_dio3(void *arg);
/* Interrupt dispatcher used if all DIOs are mapped to the same input pin */
static void _isr_dio_all(void *arg);
#endif

#ifdef MODULE_PERIPH_GPIO_IRQ
/* Interrupt routine that triggers the jammer by external input */
static void _isr_trigger_jammer(void *arg);
/* Interrupt routine that is used to schedule frame transmission */
static void _isr_trigger_transmission(void *arg);
#endif

/**
 * like lm_disable_irq but internal without locking, e.g. if called
 * within lm_enable_irq
 */
static void _lm_disable_irq_nolock(lora_modem_t *modem, lora_irq_t type);

#if ENABLE_DEBUG
static void _lm_dump_isr_config(lora_modem_t *modem);
#endif

void isr_frame_to_buffer(void *arg)
{
    lora_modem_t *modem = (lora_modem_t*)arg;
    msg_t msg;
    msg.type = LORAMODEM_MTYPE_FRAME_TO_BUF;
    msg.content.ptr = NULL;
    int msg_res = msg_send(&msg, modem->modem_thread_pid);
    if (msg_res == 1) {
        DEBUG("%s: Sent FRAME_TO_BUF (pid=%d)\n",
            thread_getname(thread_getpid()), modem->modem_thread_pid);
    }
    else if (msg_res == 0) {
        DEBUG("%s: Sending FRAME_TO_BUF failed (pid=%d)\n",
            thread_getname(thread_getpid()), modem->modem_thread_pid);
    }
    else {
        DEBUG("%s: Invalid PID, cannot process FRAME_TO_BUF (pid=%d)\n",
            thread_getname(thread_getpid()), modem->modem_thread_pid);
    }
}

void isr_reset_state_after_tx(void *arg)
{
    lora_modem_t *modem = (lora_modem_t*)arg;
    /* okay, as SPI is acquired */
    lm_disable_irq(modem, LORA_IRQ_TXDONE);
    modem->active_tasks.tx = false;
    modem->jammer_active = false;
    /* Send message to main thread */
    msg_t msg;
    msg.type = LORAMODEM_MTYPE_TX_RESTORE;
    msg.content.ptr = NULL;
    int msg_res = msg_send(&msg, modem->modem_thread_pid);
    if (msg_res == 1) {
        DEBUG("%s: Sent TX_RESTORE (pid=%d)\n",
            thread_getname(thread_getpid()), modem->modem_thread_pid);
    }
    else if (msg_res == 0) {
        DEBUG("%s: Sending TX_RESTORE failed (pid=%d)\n",
            thread_getname(thread_getpid()), modem->modem_thread_pid);
    }
    else {
        DEBUG("%s: Invalid PID, cannot process TX_RESTORE (pid=%d)\n",
            thread_getname(thread_getpid()), modem->modem_thread_pid);
    }
    /* If transmit_now is blocking, wake it up */
    if (modem->tx_done_ack_pid != KERNEL_PID_UNDEF) {
        thread_wakeup(modem->tx_done_ack_pid);
        modem->tx_done_ack_pid = KERNEL_PID_UNDEF;
    }
}


void isr_valid_header_to_sniffer(void *arg)
{
    lora_modem_t *modem = arg;
    msg_t msg;
    msg.type = LORAMODEM_MTYPE_SIGNAL_SNIFFER;
    msg.content.ptr = NULL;
    int msg_res = msg_send(&msg, modem->modem_thread_pid);
    if (msg_res == 1) {
        DEBUG("%s: Sent SIGNAL_SNIFFER (pid=%d)\n",
            thread_getname(thread_getpid()), modem->modem_thread_pid);
    }
    else if (msg_res == 0) {
        DEBUG("%s: Sending SIGNAL_SNIFFER failed (pid=%d)\n",
            thread_getname(thread_getpid()), modem->modem_thread_pid);
    }
    else {
        DEBUG("%s: Invalid PID, cannot process SIGNAL_SNIFFER (pid=%d)\n",
            thread_getname(thread_getpid()), modem->modem_thread_pid);
    }
}

void lm_enable_irq(lora_modem_t *modem, lora_irq_t type, lora_irq_cb cb)
{
    mutex_lock(&(modem->mutex_irq_config));
    DEBUG("%s: Entered enable_irq, locked\n", thread_getname(thread_getpid()));
    uint8_t irqflagmask = 0;
    uint8_t reg_dio_map = REG127X_DIO_MAPPING1;
    uint8_t msk_dio_map = 0x00;
    uint8_t val_dio_map = 0x00;
    DEBUG("%s: Callback address to set: 0x%lx\n", thread_getname(thread_getpid()),
        (unsigned long int)cb);
    switch(type) {
        case LORA_IRQ_RXDONE:
        case LORA_IRQ_RXDONE_AND_CRC:
            DEBUG("%s: Enabling IRQ_RXDONE\n", thread_getname(thread_getpid()));
            irqflagmask = VAL127X_LORA_IRQFLAGS_RXDONE;
            if (type == LORA_IRQ_RXDONE_AND_CRC) {
                DEBUG("%s: Enabling payload CRC check\n", thread_getname(thread_getpid()));
                irqflagmask |= VAL127X_LORA_IRQFLAGS_PAYLOADCRCERROR;
            }
            modem->irq_config.rx_done = cb;
            msk_dio_map = MSK127X_DIO_MAPPING1_DIO0;
            val_dio_map = VAL127X_DIO_MAPPING1_DIO0_RXDONE;
            /* Rx/Tx Done are on the same pin */
            _lm_disable_irq_nolock(modem, LORA_IRQ_TXDONE);
            break;
        case LORA_IRQ_TXDONE:
            DEBUG("%s: Enabling IRQ_TXDONE\n", thread_getname(thread_getpid()));
            irqflagmask = VAL127X_LORA_IRQFLAGS_TXDONE;
            modem->irq_config.tx_done = cb;
            msk_dio_map = MSK127X_DIO_MAPPING1_DIO0;
            val_dio_map = VAL127X_DIO_MAPPING1_DIO0_TXDONE;
            /* Rx/Tx Done are on the same pin */
            _lm_disable_irq_nolock(modem, LORA_IRQ_RXDONE);
            break;
        case LORA_IRQ_VALID_HEADER:
            DEBUG("%s: Enabling IRQ_VALID_HEADER\n", thread_getname(thread_getpid()));
            irqflagmask = VAL127X_LORA_IRQFLAGS_VALIDHEADER;
            modem->irq_config.valid_header = cb;
            msk_dio_map = MSK127X_DIO_MAPPING1_DIO3;
            val_dio_map = VAL127X_DIO_MAPPING1_DIO3_VALIDHEADER;
            break;
    }
    /* Enable the interrupts on the transceiver */
    lm_write_reg_masked(modem, REG127X_LORA_IRQFLAGSMASK, irqflagmask, 0);
    lm_write_reg_masked(modem, reg_dio_map, msk_dio_map, val_dio_map);
    modem->dio_mapping1 = lm_read_reg(modem, REG127X_DIO_MAPPING1);
    modem->dio_mapping2 = lm_read_reg(modem, REG127X_DIO_MAPPING2);
    mutex_unlock(&(modem->mutex_irq_config));
    DEBUG("%s: Left enable_irq, unlocked\n", thread_getname(thread_getpid()));
#if ENABLE_DEBUG
    _lm_dump_isr_config(modem);
#endif
}

lora_irq_cb lm_get_irq_cb(lora_modem_t *modem, lora_irq_t type)
{
    mutex_lock(&(modem->mutex_irq_config));
    lora_irq_cb cb = NULL;
    switch(type) {
        case LORA_IRQ_RXDONE:
        case LORA_IRQ_RXDONE_AND_CRC:
            cb = modem->irq_config.rx_done;
            break;
        case LORA_IRQ_TXDONE:
            cb = modem->irq_config.tx_done;
            break;
        case LORA_IRQ_VALID_HEADER:
            cb = modem->irq_config.valid_header;
            break;
    }
    mutex_unlock(&(modem->mutex_irq_config));
    DEBUG("%s: Returning callback address: 0x%lx\n",
        thread_getname(thread_getpid()), (long unsigned int)cb);
    return cb;
}

void lm_disable_irq(lora_modem_t *modem, lora_irq_t type)
{
    mutex_lock(&(modem->mutex_irq_config));
    DEBUG("%s: Entered disable_irq, locked\n", thread_getname(thread_getpid()));
    _lm_disable_irq_nolock(modem, type);
    mutex_unlock(&(modem->mutex_irq_config));
    DEBUG("%s: Left disable_irq, unlocked\n", thread_getname(thread_getpid()));
#if ENABLE_DEBUG
    _lm_dump_isr_config(modem);
#endif
}

void lm_init_gpios(lora_modem_t *modem)
{
    if (modem->gpio_reset != GPIO_UNDEF) {
        gpio_init(modem->gpio_reset, GPIO_OUT);
    }

    /** Do we need to start an interrupt handler thread? */
    bool needs_thread = false;
#ifdef MODULE_PERIPH_GPIO
    if (modem->gpio_dio0 == modem->gpio_dio3 && modem->gpio_dio0 != GPIO_UNDEF) {
        /* All interrupts are mapped to the same pin on the CPU -> generic ISR */
        _init_gpio(modem->gpio_dio0, &(modem->dio0_mode), _isr_dio_all, modem);
        modem->dio3_mode = modem->dio0_mode;
        DEBUG("lora_modem: DIO0+DIO3 <-> Pin 0x%lx, Mode: 0x%02x\n",
            (unsigned long int)(modem->gpio_dio0), modem->dio0_mode);
    }
    else {
        /* Separate pin for each interrupt, so we can use the faster, specific ISRs */
        _init_gpio(modem->gpio_dio0, &(modem->dio0_mode), _isr_dio0, modem);
        DEBUG("lora_modem: DIO0 <-> Pin 0x%lx, Mode: 0x%02x\n",
            (unsigned long int)(modem->gpio_dio0), modem->dio0_mode);

        _init_gpio(modem->gpio_dio3, &(modem->dio3_mode), _isr_dio3, modem);
        DEBUG("lora_modem: DIO3 <-> Pin 0x%lx, Mode: 0x%02x\n",
            (unsigned long int)(modem->gpio_dio3), modem->dio3_mode);
    }

    needs_thread =
        (modem->dio0_mode != DIO_MODE_IRQ) ||
        (modem->dio3_mode != DIO_MODE_IRQ);

#ifdef MODULE_PERIPH_GPIO_IRQ
    if (modem->gpio_jammer != GPIO_UNDEF) {
        if(gpio_init_int(modem->gpio_jammer, GPIO_IN, GPIO_RISING,
            _isr_trigger_jammer, modem) != 0) {
            DEBUG("lora_modem: Could not setup IRQ on external jammer trigger line\n");
            modem->gpio_jammer = GPIO_UNDEF;
        }
        else {
            DEBUG("lora_modem: Configured external jammer trigger line\n");
        }
    }
    else {
        DEBUG("lora_modem: Jammer GPIO trigger unavailable: no line configured\n");
    }
    if (modem->gpio_trigger_tx != GPIO_UNDEF) {
        if(gpio_init_int(modem->gpio_trigger_tx, GPIO_IN, GPIO_RISING,
            _isr_trigger_transmission, modem) != 0) {
            DEBUG("lora_modem: Cloud not setup IRQ on external transmission trigger\n");
            modem->gpio_trigger_tx = GPIO_UNDEF;
        } else {
            DEBUG("lora_modem: Configured external transmission trigger\n");
        }
    } else {
        DEBUG("lora_modem: External transmission trigger unavailable, no line configured\n");
    }
#else
    /* Without GPIO_IRQ by hardware no external trigger */
    modem->gpio_jammer = GPIO_UNDEF;
#endif
    if (modem->gpio_sniffer != GPIO_UNDEF) {
        if (gpio_init(modem->gpio_sniffer, GPIO_OUT) == 0) {
            gpio_clear(modem->gpio_sniffer);
            DEBUG("lora_modem: Configured external sniffer signal line\n");
        }
        else {
            DEBUG("lora_modem: Could not setup sniffer's external trigger line\n");
            modem->gpio_sniffer = GPIO_UNDEF;
        }
    }
    else {
        DEBUG("lora_modem: Sniffer GPIO action unavailable: no line configured\n");
    }

#else
    DEBUG("lora_modem: Board does not support GPIOs, using IRQ thread.\n");
    needs_thread = true;
#endif

    if (needs_thread) {
        /* If we start a thread, it will take care of calling the handler
         * functions for each event */
        sprintf(modem->irq_thread_name, "modemirq:%d", irq_thread_count++);
        DEBUG("lora_modem: Starting IRQ thread: %s\n", modem->irq_thread_name);

        memset(modem->irq_thread_stack, 0, sizeof(modem->irq_thread_stack));
        modem->irq_thread_pid = thread_create(
            modem->irq_thread_stack,
            sizeof(modem->irq_thread_stack),
            THREAD_PRIORITY_IDLE - 1,
            0,
            _irqthread,
            modem,
            modem->irq_thread_name
        );
    }
    else {
        DEBUG("lora_modem: All IRQ are available as HW interrupt, starting no thread.\n");
    }
}

#ifdef MODULE_PERIPH_GPIO
static void _init_gpio(gpio_t gpio, lora_dio_mode_t *mode, gpio_cb_t cb, void *cbarg) {
    (*mode) = DIO_MODE_UNUSED;
#if FORCE_IRQ_THREAD
    DEBUG("Forcing creation of irqthread (FORCE_IRQ_THREAD==1)\n");
    (void)gpio;
    (void)cbarg;
    (void)cb;
#else
    if (gpio != GPIO_UNDEF) {
#ifdef MODULE_PERIPH_GPIO_IRQ
        /* With IRQs: Try to enable IRQ first */
        if (gpio_init_int(gpio, GPIO_IN, GPIO_RISING, cb, cbarg)==0) {
            DEBUG("lora_modem: Configured pin 0x%lx as interrupt.\n",
                (unsigned long int)gpio);
            (*mode) = DIO_MODE_IRQ;
        }
        else {
            DEBUG("lora_modem: Couldn't configure HW IRQ on pin 0x%lx\n",
                (unsigned long int)gpio);
            if (gpio_init(gpio, GPIO_IN)==0) {
                (*mode) = DIO_MODE_INPUT;
            }
            else {
                DEBUG("lora_modem: Couldn't configure pin 0x%lx as input\n",
                    (unsigned long int)gpio);
            }
        }
#else
        DEBUG("lora_modem: Missing PERIPH_GPIO_IRQ feature\n");
        /* Without IRQs: Only set input for pin */
        (void)cb;
        (void)cbarg;
        if (gpio_init(gpio, GPIO_IN)==0) {
            (*mode) = DIO_MODE_INPUT;
        }
        else {
            DEBUG("lora_modem: Couldn't configure pin 0x%lx as input\n",
                (unsigned long int)gpio);
        }
#endif // ifdef MODULE_PERIPH_GPIO_IRQ
    }
#endif // if FORCE_IRQ_THREAD
}
#endif

static void *_irqthread(void *arg)
{
    lora_modem_t *modem = (lora_modem_t*)arg;
    while (true) {
        if (SPI_ACQUIRE(modem) == SPI_OK) {
            uint64_t irqtime = xtimer_now_usec64();
            uint8_t irqflags = lm_read_reg(modem, REG127X_LORA_IRQFLAGS);

            if (irqflags & VAL127X_LORA_IRQFLAGS_VALIDHEADER) {
                DEBUG("%s: Handling valid_header\n", thread_getname(thread_getpid()));
                _irqthread_handle_validheader(modem,
                    lm_get_irq_cb(modem, LORA_IRQ_VALID_HEADER), irqtime, irqflags);
            }

            if (irqflags & VAL127X_LORA_IRQFLAGS_RXDONE) {
                DEBUG("%s: Handling rx_done\n", thread_getname(thread_getpid()));
                _irqthread_handle_rxdone(modem,
                    lm_get_irq_cb(modem, LORA_IRQ_RXDONE), irqtime, irqflags);
                modem->lora_sniffer_last_rxbyteaddr =
                    lm_read_reg(modem, REG127X_LORA_FIFORXBYTEADDR);
            }

            if (irqflags & VAL127X_LORA_IRQFLAGS_TXDONE) {
                DEBUG("%s: Handling txdone\n", thread_getname(thread_getpid()));
                _irqthread_handle_txdone(modem,
                    lm_get_irq_cb(modem, LORA_IRQ_TXDONE), irqtime, irqflags);
            }
            SPI_RELEASE(modem);
        }
        else {
            DEBUG("%s: Couldn't acquire SPI\n", thread_getname(thread_getpid()));
        }
        DEBUG("%s: yielding\n", thread_getname(thread_getpid()));
        thread_yield();
    }
    return NULL;
}

static inline void _irqthread_handle_rxdone(lora_modem_t *modem, lora_irq_cb cb,
    uint64_t irqtime, uint8_t irqflags)
{
    modem->t_rxdone = irqtime;
    modem->lora_sniffer_rxdone = true;
    DEBUG("%s: irqthread rxdone irq\n", thread_getname(thread_getpid()));
    if (cb != NULL) {
        DEBUG("%s: Calling 0x%lx\n", thread_getname(thread_getpid()),
            (long unsigned int)cb);
        cb(modem);
        DEBUG("%s: rxdone callback done\n", thread_getname(thread_getpid()));
    }
    else {
        DEBUG("%s: no rxdone callback\n", thread_getname(thread_getpid()));
    }
    lm_write_reg(modem, REG127X_LORA_IRQFLAGS, VAL127X_LORA_IRQFLAGS_RXDONE);
    if (irqflags & VAL127X_LORA_IRQFLAGS_PAYLOADCRCERROR) {
        DEBUG("%s: Clearing CRC payload error", thread_getname(thread_getpid()));
        lm_write_reg(modem, REG127X_LORA_IRQFLAGS,
            VAL127X_LORA_IRQFLAGS_PAYLOADCRCERROR);
    }
}

static inline void _irqthread_handle_txdone(lora_modem_t *modem, lora_irq_cb cb,
    uint64_t irqtime, uint8_t irqflags)
{
    (void)irqtime;
    (void)irqflags;
    DEBUG("%s: irqthread txdone irq\n", thread_getname(thread_getpid()));
    if (cb != NULL) {
        DEBUG("%s: Calling 0x%lx\n", thread_getname(thread_getpid()),
            (long unsigned int)cb);
        cb(modem);
        DEBUG("%s: txdone callback done\n", thread_getname(thread_getpid()));
    }
    else {
        DEBUG("%s: no txdone callback\n", thread_getname(thread_getpid()));
    }
    lm_write_reg(modem, REG127X_LORA_IRQFLAGS, VAL127X_LORA_IRQFLAGS_TXDONE);
}

static inline void _irqthread_handle_validheader(lora_modem_t *modem,
    lora_irq_cb cb, uint64_t irqtime, uint8_t irqflags)
{
    (void)irqflags;
    modem->t_valid_header = irqtime;
    DEBUG("%s: irqthread validheader irq\n", thread_getname(thread_getpid()));
    if (cb != NULL) {
        DEBUG("%s: Calling 0x%lx\n", thread_getname(thread_getpid()),
            (long unsigned int)cb);
        cb(modem);
        DEBUG("%s: validheader callback done\n", thread_getname(thread_getpid()));
    }
    else {
        DEBUG("%s: no validheader callback\n", thread_getname(thread_getpid()));
    }
    lm_write_reg(modem, REG127X_LORA_IRQFLAGS, VAL127X_LORA_IRQFLAGS_VALIDHEADER);
}

#ifdef MODULE_PERIPH_GPIO
static void _isr_dio0(void *arg)
{
    uint64_t irqtime = xtimer_now_usec64();
    lora_modem_t *modem = (lora_modem_t*)arg;
    DEBUG("lora_modem: dio0 HW IRQ\n");
    uint8_t irqflags = 0;
    if (SPI_ACQUIRE(modem)==SPI_OK) {
        if ((modem->dio_mapping1 & MSK127X_DIO_MAPPING1_DIO0) == VAL127X_DIO_MAPPING1_DIO0_RXDONE) {
            modem->t_rxdone = irqtime;
            modem->lora_sniffer_rxdone = true;
            // RXDone interrupt
            lora_irq_cb rxdone = lm_get_irq_cb(modem, LORA_IRQ_RXDONE);
            do {
                irqflags = lm_write_reg(modem, REG127X_LORA_IRQFLAGS,
                    VAL127X_LORA_IRQFLAGS_RXDONE);
                if (irqflags & VAL127X_LORA_IRQFLAGS_RXDONE && rxdone != NULL) {
                    rxdone(modem);
                }
                else {
                    DEBUG("%s: Got RXDONE IRQ, but flag isn't set.\n", thread_getname(thread_getpid()));
                }
                if (irqflags & VAL127X_LORA_IRQFLAGS_PAYLOADCRCERROR) {
                    DEBUG("%s: Clearing CRC payload error", thread_getname(thread_getpid()));
                    irqflags = lm_write_reg(modem, REG127X_LORA_IRQFLAGS,
                        VAL127X_LORA_IRQFLAGS_PAYLOADCRCERROR);
                }
                modem->lora_sniffer_last_rxbyteaddr =
                    lm_read_reg(modem, REG127X_LORA_FIFORXBYTEADDR);

                irqflags = lm_read_reg(modem, REG127X_LORA_IRQFLAGS);
            } while(irqflags & (VAL127X_LORA_IRQFLAGS_RXDONE | VAL127X_LORA_IRQFLAGS_PAYLOADCRCERROR));
        }

        if ((modem->dio_mapping1 & MSK127X_DIO_MAPPING1_DIO0) == VAL127X_DIO_MAPPING1_DIO0_TXDONE) {
            // TXDone interrupt
            lora_irq_cb txdone = lm_get_irq_cb(modem, LORA_IRQ_TXDONE);
            do {
                irqflags = lm_write_reg(modem, REG127X_LORA_IRQFLAGS,
                    VAL127X_LORA_IRQFLAGS_TXDONE);
                if (irqflags & VAL127X_LORA_IRQFLAGS_TXDONE && txdone != NULL) {
                    txdone(modem);
                }
                irqflags = lm_read_reg(modem, REG127X_LORA_IRQFLAGS);
            } while(irqflags & VAL127X_DIO_MAPPING1_DIO0_TXDONE);
        }

        if (irqflags & (IRQMASK)) {
            lm_write_reg(modem, REG127X_LORA_IRQFLAGS, IRQMASK);
        }
        SPI_RELEASE(modem);
    }
    else {
        DEBUG("%s: Got dio0 IRQ, but cannot acquire SPI.\n", thread_getname(thread_getpid()));
    }
}

static void _isr_dio3(void *arg)
{
    uint64_t irqtime = xtimer_now_usec64();
    lora_modem_t *modem = (lora_modem_t*)arg;
    DEBUG("%s: dio3 HW IRQ\n", thread_getname(thread_getpid()));
    if ((modem->dio_mapping1 & MSK127X_DIO_MAPPING1_DIO3) == VAL127X_DIO_MAPPING1_DIO3_VALIDHEADER) {
        modem->t_valid_header = irqtime;
        /* Valid-Header interrupt */
        lora_irq_cb validheader = lm_get_irq_cb(modem, LORA_IRQ_VALID_HEADER);
        if (SPI_ACQUIRE(modem)==SPI_OK) {
            uint8_t irqflags = lm_write_reg(modem, REG127X_LORA_IRQFLAGS,
                VAL127X_LORA_IRQFLAGS_VALIDHEADER);
            while(irqflags & VAL127X_LORA_IRQFLAGS_VALIDHEADER) {
                irqflags = lm_write_reg(modem, REG127X_LORA_IRQFLAGS,
                    VAL127X_LORA_IRQFLAGS_VALIDHEADER);
                if (validheader != NULL) {
                    validheader(modem);
                }
                irqflags = lm_read_reg(modem, REG127X_LORA_IRQFLAGS);
            }
            if (irqflags & IRQMASK) {
                printf("IRQ set but not requested: 0x%02x\n", irqflags);
                lm_write_reg(modem, REG127X_LORA_IRQFLAGS, IRQMASK);
            }
            SPI_RELEASE(modem);
        }
        else {
            DEBUG("%s: Got VALID_HEADER IRQ, but cannot acquire SPI.\n", thread_getname(thread_getpid()));
        }
    }
}

static void _isr_dio_all(void *arg)
{
    uint64_t irqtime = xtimer_now_usec64();
    lora_modem_t *modem = (lora_modem_t*)arg;
    DEBUG("%s: generic HW IRQ\n", thread_getname(thread_getpid()));

    /* We do only handle these interrupts: */

    if (SPI_ACQUIRE(modem)==SPI_OK) {
        uint8_t irqflags = lm_read_reg(modem, REG127X_LORA_IRQFLAGS);
        while (irqflags & IRQMASK) {

            DEBUG("%s: generic HW IRQ: irqflags=%02x\n", thread_getname(thread_getpid()), irqflags);

            /* Valid header (check this first, as it is most critical for jamming) */
            if (irqflags & VAL127X_LORA_IRQFLAGS_VALIDHEADER) {
                lm_write_reg_masked(modem, REG127X_LORA_IRQFLAGS,
                    VAL127X_LORA_IRQFLAGS_VALIDHEADER, 0xff);
                modem->t_valid_header = irqtime;
                lora_irq_cb validheader = lm_get_irq_cb(modem, LORA_IRQ_VALID_HEADER);
                if (validheader != NULL) {
                    DEBUG("%s: generic HW IRQ: Calling validheader()\n", thread_getname(thread_getpid()));
                    validheader(modem);
                }
            }

            /* RXDone interrupt */
            if (irqflags & VAL127X_LORA_IRQFLAGS_RXDONE) {
                lm_write_reg_masked(modem, REG127X_LORA_IRQFLAGS,
                    VAL127X_LORA_IRQFLAGS_RXDONE, 0xff);
                modem->t_rxdone = irqtime;
                modem->lora_sniffer_rxdone = true;
                lora_irq_cb rxdone = lm_get_irq_cb(modem, LORA_IRQ_RXDONE);
                if (rxdone != NULL) {
                    DEBUG("%s: generic HW IRQ: Calling rxdone()\n", thread_getname(thread_getpid()));
                    rxdone(modem);
                }
                modem->lora_sniffer_last_rxbyteaddr =
                    lm_read_reg(modem, REG127X_LORA_FIFORXBYTEADDR);
            }

            /* TXDone interrupt */
            if (irqflags & VAL127X_LORA_IRQFLAGS_TXDONE) {
                lm_write_reg_masked(modem, REG127X_LORA_IRQFLAGS,
                    VAL127X_LORA_IRQFLAGS_TXDONE, 0xff);
                lora_irq_cb txdone = lm_get_irq_cb(modem, LORA_IRQ_TXDONE);
                if (txdone != NULL) {
                    DEBUG("%s: generic HW IRQ: Calling txdone()\n", thread_getname(thread_getpid()));
                    txdone(modem);
                }
            }

            if (irqflags & VAL127X_LORA_IRQFLAGS_PAYLOADCRCERROR) {
                DEBUG("%s: Clearing CRC payload error", thread_getname(thread_getpid()));
                lm_write_reg(modem, REG127X_LORA_IRQFLAGS,
                    VAL127X_LORA_IRQFLAGS_PAYLOADCRCERROR);
            }

            /* Check again before leaving, otherwise dio0 stays high and
             * we'll never see a rising edge again (so no more interrupts)
             */
            irqflags = lm_read_reg(modem, REG127X_LORA_IRQFLAGS);
        }
        /* Just make sure no other flags are set */
        irqflags = lm_write_reg(modem, REG127X_LORA_IRQFLAGS, 0xff);
        SPI_RELEASE(modem);

        if (irqflags) {
            /* This is an error. We want to see this. Even without debugger. */
            printf("IRQ-flags was 0x%02x after isr_dio_all!\n", irqflags);
        }
        else {
            DEBUG("%s: IRQFLAGS after generic HW IRQ handling: 0x%02x\n",
                thread_getname(thread_getpid()), irqflags);
        }
    }
    else {
        DEBUG("%s: Got generic interrupt, but cannot acquire SPI.\n", thread_getname(thread_getpid()));
    }
}
#endif

#ifdef MODULE_PERIPH_GPIO_IRQ
static void _isr_trigger_jammer(void *arg)
{
    lora_modem_t *modem = arg;
    DEBUG("%s: isr_trigger_jammer enter\n", thread_getname(thread_getpid()));
    if (modem->jammer_trigger == LORA_JAMMER_TRIGGER_GPIO) {
        msg_t msg;
        msg.type = LORAMODEM_MTYPE_TRIGGER_JAMMER;
        int msg_res = msg_send(&msg, modem->modem_thread_pid);
        if (msg_res == 1) {
            DEBUG("%s: Sent TRIGGER_JAMMER (pid=%d)\n",
                thread_getname(thread_getpid()), modem->modem_thread_pid);
        }
        else if (msg_res == 0) {
            DEBUG("%s: Sending TRIGGER_JAMMER failed (pid=%d)\n",
                thread_getname(thread_getpid()), modem->modem_thread_pid);
        }
        else {
            DEBUG("%s: Invalid PID, cannot process TRIGGER_JAMMER (pid=%d)\n",
                thread_getname(thread_getpid()), modem->modem_thread_pid);
        }
    }
    DEBUG("%s: isr_trigger_jammer leave\n", thread_getname(thread_getpid()));
}

static void _isr_trigger_transmission(void *arg)
{
    lora_modem_t *modem = arg;
    if (modem->active_tasks.prepared_tx) {
        // If a frame is configured, schedule the message.
        // We check for preparation when the message is received.
        xtimer_set_msg64(
            &(modem->gpio_tx_trigtimer),
            modem->gpio_tx_delay,
            &(modem->gpio_tx_trigmsg),
            modem->modem_thread_pid);
    }
}
#endif

static void _lm_disable_irq_nolock(lora_modem_t *modem, lora_irq_t type)
{
    uint8_t irqflagmask = 0;
    switch(type) {
        case LORA_IRQ_RXDONE:
        case LORA_IRQ_RXDONE_AND_CRC:
            DEBUG("%s: Disabling IRQ_RXDONE\n", thread_getname(thread_getpid()));
            irqflagmask = VAL127X_LORA_IRQFLAGS_RXDONE &
                          VAL127X_LORA_IRQFLAGS_PAYLOADCRCERROR;
            modem->irq_config.rx_done = NULL;
            break;
        case LORA_IRQ_TXDONE:
            DEBUG("%s: Disabling IRQ_TXDONE\n", thread_getname(thread_getpid()));
            irqflagmask = VAL127X_LORA_IRQFLAGS_TXDONE;
            modem->irq_config.tx_done = NULL;
            break;
        case LORA_IRQ_VALID_HEADER:
            DEBUG("%s: Disabling IRQ_VALID_HEADER\n", thread_getname(thread_getpid()));
            irqflagmask = VAL127X_LORA_IRQFLAGS_VALIDHEADER;
            modem->irq_config.valid_header = NULL;
            break;
    }
    lm_write_reg_masked(modem, REG127X_LORA_IRQFLAGSMASK, irqflagmask, 0xff);
    lm_write_reg_masked(modem, REG127X_LORA_IRQFLAGS, irqflagmask, 0xff);
}

#if ENABLE_DEBUG
static void _lm_dump_isr_config(lora_modem_t *modem)
{
    DEBUG("%s: ISR-CONFIG:\n", thread_getname(thread_getpid()));
    DEBUG("   TX_DONE: 0x%lx\n", (unsigned long int)lm_get_irq_cb(modem, LORA_IRQ_TXDONE));
    DEBUG("   RX_DONE: 0x%lx\n", (unsigned long int)lm_get_irq_cb(modem, LORA_IRQ_RXDONE));
    DEBUG("   VHEADER: 0x%lx\n", (unsigned long int)lm_get_irq_cb(modem, LORA_IRQ_VALID_HEADER));
}
#endif
