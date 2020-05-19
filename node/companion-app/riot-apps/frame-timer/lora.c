#include "lora.h"

#include <string.h>

#include "xtimer.h"
#include "msg.h"

#include "lora_modem.h"
#include "appconfig.h"
#include "gps.h"

#define FREQ_DEFAULT (868300000U)
#define BW_DEFAULT (LORA_BANDWIDTH_125KHZ)
#define SF_DEFAULT (LORA_SF_12)

#define MTYPE_SET_SF   0x100
#define MTYPE_SET_BW   0x101
#define MTYPE_SET_FREQ 0x102
#define MTYPE_ACK      0x103
#define MTYPE_DOWNLINK 0x104
#define MTYPE_UPLINK   0x105

#define MSG_QUEUE_SIZE 8

/*
 * We use the following principle to capture rx2 during the attack. A upcoming
 * rx 2 transmission can be predicted by observing consecutive uplinks with the
 * same payload on the same frequency (first is upload by end device, second is
 * replay by attacker - which will then wait for the rx1 response and replay
 * that response in rx2)
 *
 *        same frame arrives twice
 *                ↓     ↓                 v- back to rx1 uplink
 * mdm_up   --[frm]-[frm]--------==[frm]==--------------
 *                      |-<3 sec-|   ^- switch to rx2 for 2.5 sec
 * mdm_down -----------------[frm]----------------------
 *                               ↑
 *                   downlink max. 3 secs after last uplink
 */

/* The modems */
static lora_modem_t modems[2] = {
    {
        .bus         = LORA_SPI_BUS,
        .cs          = LORA1_SPI_CS,
        .gpio_reset  = LORA1_GPIO_RESET,
        .gpio_dio0   = LORA1_GPIO_DIO0,
        .gpio_dio3   = LORA1_GPIO_DIO3,
        .gpio_jammer = GPIO_UNDEF,
    },{
        .bus         = LORA_SPI_BUS,
        .cs          = LORA2_SPI_CS,
        .gpio_reset  = LORA2_GPIO_RESET,
        .gpio_dio0   = LORA2_GPIO_DIO0,
        .gpio_dio3   = LORA2_GPIO_DIO3,
        .gpio_jammer = GPIO_UNDEF,
    }
}; /* modem down, modem up */

static kernel_pid_t modem_pid[2] = {KERNEL_PID_UNDEF, KERNEL_PID_UNDEF};

/** LoRa Threads */
static char lora_thread_stack[2][THREAD_STACKSIZE_MEDIUM +
    THREAD_EXTRA_STACKSIZE_PRINTF];

static void *thread_lora(void *arg);

static int lora_setup_modem(lora_modem_t* modem, char *stack,
    const char *thread_name, bool downlink);

int lora_setup(void)
{
    int res_down = lora_setup_modem(&modems[0], lora_thread_stack[0], "modem_down", true);
    if (res_down != 0) {
        printf("Configuring modem 1 failed: %d\n", res_down);
    }

    int res_up = lora_setup_modem(&modems[1], lora_thread_stack[1], "modem_up", false);
    if (res_up != 0) {
        printf("Configuring modem 2 failed: %d\n", res_up);
    }

    return res_down == 0 && res_up == 0 ? 0 : 1;
}

int lora_set_sf(uint8_t sf)
{
    msg_t msg = { .type = MTYPE_SET_SF };
    msg.content.value = sf;
    for(size_t n = 0; n < 2; n++) {
        msg_send(&msg, modem_pid[n]);
    }
    return 0;
}

int lora_set_bw(uint32_t bw)
{
    msg_t msg = { .type = MTYPE_SET_BW };
    msg.content.value = bw;
    for(size_t n = 0; n < 2; n++) {
        msg_send(&msg, modem_pid[n]);
    }
    return 0;
}

int lora_set_freq(uint32_t freq)
{
    msg_t msg = { .type = MTYPE_SET_FREQ };
    msg.content.value = freq;
    for(size_t n = 0; n < 2; n++) {
        msg_send(&msg, modem_pid[n]);
    }
    return 0;
}

static int lora_setup_modem(lora_modem_t* modem, char *stack,
    const char *thread_name, bool downlink)
{
    modem->gpio_sniffer  = GPIO_UNDEF;
    modem->reset_on_high = false;
    int res = lora_modem_init(modem);
    if (res == LORA_MODEM_INIT_OK) {
        if (lora_modem_set_frequency(modem, FREQ_DEFAULT) != 0) return -1;
        if (lora_modem_set_bandwidth(modem, BW_DEFAULT) != 0) return -1;
        if (lora_modem_set_sf(modem, SF_DEFAULT) != 0) return -1;
        if (lora_modem_set_codingrate(modem, LORA_CODINGRATE_4_5) != 0) return -1;
        if (lora_modem_set_preamble_length(modem, 8) != 0) return -1;
        if (lora_modem_set_syncword(modem, 0x34) != 0) return -1;
        if (lora_modem_set_invertiqrx(modem, downlink) != 0) return -1;
        if (lora_modem_set_txcrc(modem, true) != 0) return -1;
        if (lora_modem_set_explicitheader(modem, true) != 0) return -1;
    }
    kernel_pid_t *pid = modem==&modems[0] ? &modem_pid[0] : &modem_pid[1];
    *(pid) = thread_create(
        stack, THREAD_STACKSIZE_MEDIUM + THREAD_EXTRA_STACKSIZE_PRINTF,
        THREAD_PRIORITY_IDLE - 1, THREAD_CREATE_STACKTEST,
        thread_lora, modem, thread_name);
    return 0;
}

static void *thread_lora(void *arg)
{
    /* Message Queue */
    msg_t rcv_queue[MSG_QUEUE_SIZE];
    msg_init_queue(rcv_queue, MSG_QUEUE_SIZE);

    /* Thread parameters */
    lora_modem_t *modem = (lora_modem_t*)arg;
    bool is_modem_up = modem == &(modems[1]);
    bool mode_rx2 = false;
    bool repeated_payload = false;
    msg_t uplink_msg = {.type = MTYPE_UPLINK};
    xtimer_t back_to_uplink_timer;
    uint64_t last_frame = 0;
    uint32_t frequency = FREQ_DEFAULT;
    lora_bandwidth_t bandwidth = BW_DEFAULT;
    lora_sf_t spreadingfactor = SF_DEFAULT;

    /* Startup */
    lora_modem_receive(modem);

    /* Variables for receiving frames */
    uint8_t payload[2][LORA_PAYLOAD_MAX_LENGTH];
    ssize_t payload_size[2] = {-1, -1};
    size_t payload_idx = 0;
    lora_rx_stats_t rx_stats;
    bool has_more = false;
    bool frames_dropped = false;
    memset(payload, 0, 2*LORA_PAYLOAD_MAX_LENGTH);
    memset(&rx_stats, 0, sizeof(lora_rx_stats_t));

    while(true) {
        /* Receive */
        payload_size[payload_idx] = lora_modem_fetch_frame(modem,
            payload[payload_idx], &rx_stats, &has_more, &frames_dropped);
        if (payload_size[payload_idx] >= 0) {
            if (!is_modem_up) {
                msg_t msg = {.type=MTYPE_DOWNLINK};
                msg_send(&msg, modem_pid[1]);
            }
            printf("\n{\"rx\": {\"payload\": [");
            for(ssize_t n = 0; n < payload_size[payload_idx]; n++) {
                printf("%s%u", n>0?", ":"", payload[payload_idx][n]);
            }
            printf("], \"local_time\": %llu, \"direction\": \"",
                rx_stats.time_rxdone);
            if (is_modem_up) {
                if (mode_rx2) {
                    printf("rx2");
                } else {
                    printf("up");
                }
            } else {
                printf("down");
            }
            printf("\", \"frequency\": %u, \"bandwidth\": %u, \"spreadingfactor\": %u",
                frequency, (unsigned int)bandwidth, (unsigned int)spreadingfactor);
            if (gps_get_valid()) {
                uint64_t gpstime = gps_local2gpstime(rx_stats.time_rxdone);
                printf(", \"gps_time\": %llu", gpstime);
            }
            printf("}}\n");
            memset(&rx_stats, 0, sizeof(lora_rx_stats_t));
            payload_idx = (payload_idx + 1) & 1;
            printf("payload_size=[%d, %d]\n", payload_size[0], payload_size[1]);
        }
        /* Check for duplicate payload */
        if (payload_size[payload_idx] > -1 && payload_size[0] == payload_size[1]) {
            puts("Checking for repeated payload");
            repeated_payload = memcmp(payload[0], payload[1], payload_size[0])==0;
            if (repeated_payload) {
                last_frame = xtimer_now_usec64();
                puts("Got 2 equal frames, downlink will trigger rx2 mode");
            }
        }
        if (payload_size[payload_idx] > -1) {
            memset(payload[payload_idx], 0, LORA_PAYLOAD_MAX_LENGTH);
            payload_size[payload_idx] = -1;
        }

        /* Process messages */
        msg_t msg;
        if (msg_try_receive(&msg)==1) {
            switch(msg.type) {
                case MTYPE_SET_BW: {
                    bandwidth = (lora_bandwidth_t)(msg.content.value/1000);
                    msg.content.value = (uint32_t)lora_modem_set_bandwidth(
                        modem, bandwidth);
                    lora_modem_receive(modem);
                    break;
                }
                case MTYPE_SET_FREQ: {
                    frequency = msg.content.value;
                    msg.content.value = (uint32_t)lora_modem_set_frequency(
                        modem, frequency);
                    lora_modem_receive(modem);
                    break;
                }
                case MTYPE_SET_SF: {
                    spreadingfactor = (lora_sf_t)(msg.content.value);
                    msg.content.value = (uint32_t)lora_modem_set_sf(modem,
                        spreadingfactor);
                    lora_modem_receive(modem);
                    break;
                }
                case MTYPE_DOWNLINK: {
                    if (is_modem_up && repeated_payload) {
                        uint64_t now = xtimer_now_usec64();
                        if (now < last_frame + 3000000u) {
                            mode_rx2 = true;
                            lora_modem_set_frequency(modem, 869525000);
                            lora_modem_set_bandwidth(modem, LORA_BANDWIDTH_125KHZ);
                            lora_modem_set_sf(modem, LORA_SF_12);
                            lora_modem_set_invertiqrx(modem, true);
                            lora_modem_receive(modem);
                            xtimer_set_msg64(&back_to_uplink_timer, 2500000u,
                                &uplink_msg, modem_pid[1]);
                            puts("Uplink modem starts observing rx2");
                        }
                    }
                    break;
                }
                case MTYPE_UPLINK: {
                    if (is_modem_up) {
                        mode_rx2 = false;
                        lora_modem_set_frequency(modem, frequency);
                        lora_modem_set_bandwidth(modem, bandwidth);
                        lora_modem_set_sf(modem, spreadingfactor);
                        lora_modem_set_invertiqrx(modem, false);
                        lora_modem_receive(modem);
                        puts("Uplink modem is back from rx2");
                    }
                    break;
                }
                default:
                    printf("Modem thread got unknown mtype: %u\n", msg.type);
            }
        }

        thread_yield();
    }
    return NULL;
}
