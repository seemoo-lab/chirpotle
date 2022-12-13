#include "lora_daemon_cmd_runner.h"

#include <string.h>

#include "lora_modem.h"

#include "xtimer.h"

#define ENABLE_DEBUG (0)
#include "debug.h"

/* Handler function to configure gain and tx power */
static void _cmd_configure_gain(
    lora_modem_t *modem,
    lora_daemon_req_configure_gain_t *req,
    lora_daemon_res_t *res);

/** Handler function enabling the jammer */
static void _cmd_enable_rc_jammer (
    lora_modem_t *modem,
    lora_daemon_req_enable_rc_jammer_t *req,
    lora_daemon_res_t *res);

/** Handler function enabling the sniffer */
static void _cmd_enable_sniffer(
    lora_modem_t *modem,
    lora_daemon_req_enable_sniffer_t *req,
    lora_daemon_res_t *res);

/** Handler function to return frames from the buffer */
static void _cmd_fetch_frame(lora_modem_t *modem, lora_daemon_res_t *res);

/** Handler function for the get_channel command. */
static void _cmd_get_channel(lora_modem_t *modem, lora_daemon_res_t *res);

/** Handler function for get_preamble_length */
static void _cmd_get_preamble_length(lora_modem_t *modem, lora_daemon_res_t *res);

/** Handler function for get_time */
static void _cmd_get_time(lora_daemon_res_t *res);

/** Handler function for get_txcrc */
static void _cmd_get_txcrc(lora_modem_t *modem, lora_daemon_res_t *res);

/** Handler function for the receive command */
static void _cmd_receive(lora_modem_t *modem, lora_daemon_res_t *res);

/** Handler function for the set_channel command. */
static void _cmd_set_jammer_plength(
    lora_modem_t *modem,
    lora_daemon_req_set_jammer_plength_t *req,
    lora_daemon_res_t *res
);

/** Handler function for the set_channel command. */
static void _cmd_set_channel(
    lora_modem_t *modem,
    lora_daemon_req_set_lora_channel_t *req,
    lora_daemon_res_t *res
);

/** Handler function for set_preamble_length */
static void _cmd_set_preamble_length(
    lora_modem_t *modem,
    lora_daemon_req_set_preamble_length_t *req,
    lora_daemon_res_t *res
);

/** Handler function for the set_channel command. */
static void _cmd_set_txcrc(
    lora_modem_t *modem,
    lora_daemon_req_set_txcrc_t *req,
    lora_daemon_res_t *res
);

/** Handler function for the standby command */
static void _cmd_standby(lora_modem_t *modem, lora_daemon_res_t *res);

/** Handler function for the transmit_frame command */
static void _cmd_transmit_frame(
    lora_modem_t *modem,
    lora_daemon_req_transmit_frame_t *req,
    lora_daemon_res_t *res
);

/** Handler function for the transmit_on_gpio_trigger command */
static void _cmd_transmit_on_gpio_trigger(
    lora_modem_t *modem,
    lora_daemon_req_transmit_on_gpio_trigger_t *req,
    lora_daemon_res_t *res
);

/** Writes an error response object to the response */
static void _raise_error(const char* msg, lora_daemon_res_t *res);

/** Writes an status response message */
static void _return_status(const char* msg, int code, lora_daemon_res_t *res);

void lora_daemon_run_cmd(lora_daemon_t *daemon, lora_daemon_req_t *req, lora_daemon_res_t *res) {
    lora_modem_t *modem = daemon->modem;
    /* We dispatch the command to the corresponding handler function */
    switch(req->type) {
        case LORA_DAEMON_REQ_CONFIGURE_GAIN:
            DEBUG("%s: Running command configure_gain\n", daemon->name);
            _cmd_configure_gain(modem, &(req->params.configure_gain), res);
            break;
        case LORA_DAEMON_REQ_ENABLE_RC_JAMMER:
            DEBUG("%s: Running command enable_rc_jammer\n", daemon->name);
            _cmd_enable_rc_jammer(modem, &(req->params.enable_rc_jammer), res);
            break;
        case LORA_DAEMON_REQ_ENABLE_SNIFFER:
            DEBUG("%s: Running command enable_sniffer\n", daemon->name);
            _cmd_enable_sniffer(modem, &(req->params.enable_sniffer), res);
            break;
        case LORA_DAEMON_REQ_FETCH_FRAME:
            DEBUG("%s: Running command fetch_frame\n", daemon->name);
            _cmd_fetch_frame(modem, res);
            break;
        case LORA_DAEMON_REQ_GET_LORA_CHANNEL:
            DEBUG("%s: Running command get_lora_channel\n", daemon->name);
            _cmd_get_channel(modem, res);
            break;
        case LORA_DAEMON_REQ_GET_PREAMBLE_LENGTH:
            DEBUG("%s: Running command get_preamble_length\n", daemon->name);
            _cmd_get_preamble_length(modem, res);
            break;
        case LORA_DAEMON_REQ_GET_TIME:
            DEBUG("%s: Running command get_time\n", daemon->name);
            _cmd_get_time(res);
            break;
        case LORA_DAEMON_REQ_GET_TXCRC:
            DEBUG("%s: Running command get_txcrc\n", daemon->name);
            _cmd_get_txcrc(modem, res);
            break;
        case LORA_DAEMON_REQ_SET_JAMMER_PLENGTH:
            DEBUG("%s: Running command set_jammer_plen\n", daemon->name);
            _cmd_set_jammer_plength(modem, &(req->params.set_jammer_plength), res);
            break;
        case LORA_DAEMON_REQ_SET_LORA_CHANNEL:
            DEBUG("%s: Running command set_lora_channel\n", daemon->name);
            _cmd_set_channel(modem, &(req->params.set_lora_channel), res);
            break;
        case LORA_DAEMON_REQ_SET_PREAMBLE_LENGTH:
            DEBUG("%s: Running command set_preamble_length\n", daemon->name);
            _cmd_set_preamble_length(modem, &(req->params.set_preamble_length), res);
            break;
        case LORA_DAEMON_REQ_SET_TXCRC:
            DEBUG("%s: Running command set_txcrc\n", daemon->name);
            _cmd_set_txcrc(modem, &(req->params.set_txcrc), res);
            break;
        case LORA_DAEMON_REQ_RECEIVE:
            DEBUG("%s: Running command receive\n", daemon->name);
            _cmd_receive(modem, res);
            break;
        case LORA_DAEMON_REQ_STANDBY:
            DEBUG("%s: Running command standby\n", daemon->name);
            _cmd_standby(modem, res);
            break;
        case LORA_DAEMON_REQ_TRANSMIT_FRAME:
            DEBUG("%s: Running command transmit_frame\n", daemon->name);
            _cmd_transmit_frame(modem, &(req->params.transmit_frame), res);
            break;
        case LORA_DAEMON_REQ_TRANSMIT_ON_GPIO_TRIGGER:
            DEBUG("%s: Running command transmit_on_gpio_trigger\n", daemon->name);
            _cmd_transmit_on_gpio_trigger(modem, &(req->params.transmit_on_gpio_trigger), res);
            break;
        default:
            DEBUG("%s: Unknown command, cannot run.\n", daemon->name);
            _raise_error("Unknown command", res);
    }
    DEBUG("%s: Command done\n", daemon->name);
}


static void _cmd_configure_gain(
    lora_modem_t *modem,
    lora_daemon_req_configure_gain_t *req,
    lora_daemon_res_t *res)
{
    if (!req->lna_boost_set) {
        _raise_error("lna_boost not set or invalid", res);
    }
    else if (!req->lna_gain_set) {
        _raise_error("lna_gain not set or invalid", res);
    }
    else if (!req->pwr_out_set) {
        _raise_error("pwr_out_set not set or invalid", res);
    }
    else {
        if (lora_modem_configure_gain(modem, req->lna_gain, req->lna_boost, req->pwr_out)==0) {
            _return_status("gain configured", 0, res);
        }
        else {
            _raise_error("Configuring gain failed", res);
        }
    }
}

static void _cmd_enable_rc_jammer (
    lora_modem_t *modem,
    lora_daemon_req_enable_rc_jammer_t *req,
    lora_daemon_res_t *res)
{
    if (req->trigger == LORA_JAMMER_TRIGGER_NONE) {
        _raise_error("Missing trigger type", res);
        return;
    }

    int rc = lora_modem_enable_rc_jammer(modem, req->trigger);
    if (rc == 0) {
        _return_status("Jammer enabled", 0, res);
    }
    else if (rc == LORA_MODEM_ERROR_UNSUPPORTED_JAMMER_TRIGGER) {
        _raise_error("Jammer trigger not supported", res);
    }
    else {
        _raise_error("Couldn't activate jammer", res);
    }
}

static void _cmd_enable_sniffer(
    lora_modem_t *modem,
    lora_daemon_req_enable_sniffer_t *req,
    lora_daemon_res_t *res)
{
#ifdef MODULE_LORA_MODEM_JAMMER_UDP
    int rc = lora_modem_enable_sniffer(modem, req->pattern, req->mask,
        req->mask_length, req->rxbuf, req->action, &(req->addr));
#else
    int rc = lora_modem_enable_sniffer(modem, req->pattern, req->mask,
        req->mask_length, req->rxbuf, req->action);
#endif
    if (rc == 0) {
        _return_status("Jammer enabled", 0, res);
    }
    else if (rc == LORA_MODEM_ERROR_UNSUPPORTED_SNIFFER_ACTION) {
        _raise_error("Jammer action not supported", res);
    }
    else {
        _raise_error("Couldn't activate jammer", res);
    }
}

static void _cmd_fetch_frame(lora_modem_t *modem, lora_daemon_res_t *res)
{
    res->type = LORA_DAEMON_RES_FRAME_DATA;
    lora_daemon_res_frame_data_t *fd = &(res->data.frame_data);
    memset(fd, 0, sizeof(lora_daemon_res_frame_data_t));
    ssize_t fetch_res = lora_modem_fetch_frame(modem,
        fd->payload,
        &(fd->rx_stats),
        &(fd->has_more),
        &(fd->frames_dropped)
    );
    if (fetch_res < 0) {
        _return_status("No frame available", 0, res);
    }
    fd->length = fetch_res;
}

static void _cmd_get_channel(
    lora_modem_t *modem,
    lora_daemon_res_t *res)
{
    res->type = LORA_DAEMON_RES_LORA_CHANNEL;
    lora_daemon_res_lora_channel_t *cRes = &(res->data.lora_channel);

    int bw = lora_modem_get_bandwidth(modem);
    if (bw == LORA_BANDWIDTH_INVALID) {
        _raise_error("Error reading bandwidth", res);
        return;
    }
    cRes->bandwidth = (uint16_t)bw;

    cRes->frequency = lora_modem_get_frequency(modem);
    if (cRes->frequency == 0) {
        _raise_error("Error reading frequency", res);
        return;
    }

    int cr = lora_modem_get_codingrate(modem);
    if (cr == LORA_CODINGRATE_INVALID) {
        _raise_error("Error reading coding rate", res);
        return;
    }
    cRes->coding_rate = (uint8_t)cr;

    int sf = lora_modem_get_sf(modem);
    if (sf == LORA_SF_INVALID) {
        _raise_error("Error reading spreading factor", res);
        return;
    }
    cRes->spreading_factor = (uint8_t)sf;

    int sw = lora_modem_get_syncword(modem);
    if (sw < 0) {
        _raise_error("Error reading syncword", res);
        return;
    }
    cRes->syncword = sw;

    int invertiqrx = lora_modem_get_invertiqrx(modem);
    int invertiqtx = lora_modem_get_invertiqtx(modem);
    if (invertiqrx < 0 || invertiqtx < 0) {
        _raise_error("Error reading invertiq", res);
        return;
    }
    cRes->invertiqrx = (invertiqrx != 0);
    cRes->invertiqtx = (invertiqtx != 0);

    int explicitheader = lora_modem_get_explicitheader(modem);
    if (explicitheader < 0) {
        _raise_error("Error reading header mode", res);
        return;
    }
    cRes->explicitheader = (explicitheader!=0);
}

static void _cmd_get_preamble_length(lora_modem_t *modem, lora_daemon_res_t *res)
{
    int length = lora_modem_get_preamble_length(modem);
    if (length < 0) {
        _raise_error("Could not read preamble length", res);
    }
    else {
        res->type = LORA_DAEMON_RES_PREAMBLE_LENGTH;
        res->data.preamble_length.len = (uint16_t)length;
    }
}

static void _cmd_get_time(lora_daemon_res_t *res)
{
    res->type = LORA_DAEMON_RES_TIME;
    /* We can answer this here, no need for lora_modem to be involved */
    res->data.time.time = xtimer_now_usec64();
}

static void _cmd_get_txcrc(lora_modem_t *modem, lora_daemon_res_t *res)
{
    res->type = LORA_DAEMON_RES_TXCRC;
    int r = lora_modem_get_txcrc(modem);
    if (r < 0) {
        _raise_error("Couldn't read txcrc", res);
        return;
    }
    res->data.txcrc.txcrc = (r!=0);
}

static void _cmd_receive(lora_modem_t *modem, lora_daemon_res_t *res)
{
    if (lora_modem_receive(modem) != 0) {
        _raise_error("Could not start receiver", res);
    }
    _return_status("Receiving", 0, res);
}

static void _cmd_set_jammer_plength(
    lora_modem_t *modem,
    lora_daemon_req_set_jammer_plength_t *req,
    lora_daemon_res_t *res
)
{
    if (req->length != 0) {
        lora_modem_set_jammer_plength(modem, req->length);
        _return_status("Length changed", 0, res);
    }
    else {
        _raise_error("Invalid payload length", res);
    }
}

static void _cmd_set_channel(
    lora_modem_t *modem,
    lora_daemon_req_set_lora_channel_t *req,
    lora_daemon_res_t *res)
{
    /* Validation */
    if (req->spreading_factor_set && (req->spreading_factor<6 || req->spreading_factor>12)) {
        _raise_error("Invalid SF", res);
        return;
    }
    if (req->bandwidth_set && !(req->bandwidth==125 || req->bandwidth==250 || req->bandwidth==500)) {
        _raise_error("Invalid bandwidth", res);
        return;
    }
    if (req->coding_rate_set && (req->coding_rate<5 || req->coding_rate>8)) {
        _raise_error("Invalid coding rate", res);
        return;
    }

    /* OPMODE=Standby, so we don't change the params during rx/tx */
    lora_modem_set_opmode(modem, LORA_OPMODE_STANDBY);

    /* Frequency */
    if (req->frequency_set) {
        lora_modem_set_frequency(modem, req->frequency);
    }

    /* Bandwidth */
    if (req->bandwidth_set) {
        lora_bandwidth_t bw = LORA_BANDWIDTH_125KHZ;
        switch(req->bandwidth) {
            case 250: bw = LORA_BANDWIDTH_250KHZ; break;
            case 500: bw = LORA_BANDWIDTH_500KHZ; break;
        }
        lora_modem_set_bandwidth(modem, bw);
    }

    /* Spreading Factor */
    if (req->spreading_factor_set) {
        lora_modem_set_sf(modem, (lora_sf_t)(req->spreading_factor));
    }

    /* Coding rate */
    if (req->coding_rate_set) {
        lora_codingrate_t cr = LORA_CODINGRATE_4_5;
        switch(req->coding_rate) {
            case 6: cr = LORA_CODINGRATE_4_6; break;
            case 7: cr = LORA_CODINGRATE_4_7; break;
            case 8: cr = LORA_CODINGRATE_4_8; break;
        }
        lora_modem_set_codingrate(modem, cr);
    }

    /* Sync word */
    if (req->syncword_set) {
        lora_modem_set_syncword(modem, req->syncword);
    }

    /* Polarity */
    if (req->invertiqtx_set) {
        lora_modem_set_invertiqtx(modem, req->invertiqtx);
    }
    if (req->invertiqrx_set) {
        lora_modem_set_invertiqrx(modem, req->invertiqrx);
    }

    /* Header mode */
    if (req->explicitheader_set) {
        lora_modem_set_explicitheader(modem, req->explicitheader);
    }

    /* Use get_channel to fill the response */
    _cmd_get_channel(modem, res);
}

static void _cmd_set_preamble_length(
    lora_modem_t *modem,
    lora_daemon_req_set_preamble_length_t *req,
    lora_daemon_res_t *res
)
{
    if (req->length == 0) {
        _raise_error("Invalid preamble length", res);
        return;
    }
    int r = lora_modem_set_preamble_length(modem, req->length);
    if (r == 0) {
        _cmd_get_preamble_length(modem, res);
    }
    else if (r == LORA_MODEM_ERROR_COMMAND_REQUIRES_STANDBY) {
        _raise_error("Modem not in standby", res);
    }
    else {
        _raise_error("Error setting preamble length", res);
    }
}

static void _cmd_set_txcrc(
    lora_modem_t *modem,
    lora_daemon_req_set_txcrc_t *req,
    lora_daemon_res_t *res
)
{
    if (req->txcrc_set == false) {
        _raise_error("txcrc was not set", res);
    }
    else {
        int r = lora_modem_set_txcrc(modem, req->txcrc);
        if (r == 0) {
            _cmd_get_txcrc(modem, res);
        }
        else if (r == LORA_MODEM_ERROR_COMMAND_REQUIRES_STANDBY) {
            _raise_error("Modem not in standby", res);
        }
        else {
            _raise_error("Error setting txcrc", res);
        }
    }
}

static void _cmd_standby(lora_modem_t *modem, lora_daemon_res_t *res)
{
    if (lora_modem_standby(modem) != 0) {
        _raise_error("Could not go to standby", res);
    }
    _return_status("Standby", 0, res);
}

static void _cmd_transmit_frame(
    lora_modem_t *modem,
    lora_daemon_req_transmit_frame_t *req,
    lora_daemon_res_t *res)
{
    lora_frame_t frame = {
        .payload = req->payload,
        .length = req->length,
    };
    uint64_t time = (req->time_set ? req->time : 0);
    switch(lora_modem_transmit(modem, &frame, time, req->blocking)) {
        case 0:
            _return_status("Frame sent", 0, res);
            break;
        case LORA_MODEM_ERROR_TXQUEUE_FULL:
            _raise_error("tx queue is full", res);
            break;
        default:
            _raise_error("Could not send frame", res);
    }
}

static void _cmd_transmit_on_gpio_trigger(
    lora_modem_t *modem,
    lora_daemon_req_transmit_on_gpio_trigger_t *req,
    lora_daemon_res_t *res)
{
// In case the application is compiled without GPIO IRQ support,
// we cannot trigger a transmission based on that, so we return
// an error directly.
#ifdef MODULE_PERIPH_GPIO_IRQ
    lora_frame_t frame;
    frame.length = req->length;
    frame.payload = req->payload;
    lora_modem_transmit_on_gpio(modem, &frame, req->delay);
    _return_status("Triggered transmission configured", 0, res);
#else
    (void)modem;
    (void)req;
    _raise_error("GPIO IRQ support unavailable", res);
#endif
}

static void _raise_error(const char* msg, lora_daemon_res_t *res)
{
    DEBUG("lora_daemon: Raising error: %s\n", msg);
    res->type = LORA_DAEMON_RES_ERROR;
    strncpy(res->data.error.message, msg, LORA_DAEMON_RES_MSG_MAX_LENGTH);
}

static void _return_status(const char* msg, int code, lora_daemon_res_t *res)
{
    DEBUG("lora_daemon: Returning status %d: %s\n", code, msg);
    res->type = LORA_DAEMON_RES_STATUS;
    strncpy(res->data.status.message, msg, LORA_DAEMON_RES_MSG_MAX_LENGTH);
    res->data.status.code = code;
}
