#include "lora_daemon_req_parser.h"

#include <string.h>

#include "msg.h"
#include "ubjson.h"

#define ENABLE_DEBUG (0)
#include "debug.h"

/**
 * Selects the _set_param_[mtype] function required for the message type
 * and passes the parameter to it.
 */
void _set_parameter(
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_t *req,
    const char * param_name,
    const ubjson_type_t type,
    const ssize_t content);

void _set_param_configure_gain (
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_configure_gain_t *params,
    const char * param_name,
    ubjson_type_t type,
    ssize_t content);

void _set_param_enable_rc_jammer(
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_enable_rc_jammer_t *req,
    const char * param_name,
    const ubjson_type_t type,
    const ssize_t content);

void _set_param_enable_sniffer(
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_enable_sniffer_t *req,
    const char * param_name,
    const ubjson_type_t type,
    const ssize_t content);

void _set_param_jammer_set_plength(
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_set_jammer_plength_t *params,
    const char * param_name,
    ubjson_type_t type,
    ssize_t content);

void _set_param_lora_set_channel(
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_set_lora_channel_t *params,
    const char * param_name,
    ubjson_type_t type,
    ssize_t content);

void _set_param_set_preamble_length (
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_set_preamble_length_t *params,
    const char * param_name,
    ubjson_type_t type,
    ssize_t content);

void _set_param_set_txcrc (
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_set_txcrc_t *params,
    const char * param_name,
    ubjson_type_t type,
    ssize_t content);

void _set_param_transmit_frame(
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_transmit_frame_t *req,
    const char * param_name,
    const ubjson_type_t type,
    const ssize_t content);

/**
 * Tries to read the command name from the parameter and to set the type in req
 * accordingly. Returns 0 if a valid command name was used
 */
int _set_reqtype(lora_daemon_req_t *req, char *command_name);

/**
 * Callback function that is called for each entity that is parsed by the UBJSON
 * implementation
 */
ubjson_read_callback_result_t _ubjson_entity_callback(
    ubjson_cookie_t *__restrict cookie,
    ubjson_type_t type1,
    ssize_t content1,
    ubjson_type_t type2,
    ssize_t content2);

/**
 * Helper function that is used as ubjson_callback within an array parameter
 * to simplify the logic
 */
static ubjson_read_callback_result_t _ubjson_parse_array_param(
    ubjson_cookie_t *__restrict__ cookie,
    ubjson_type_t type1,
    ssize_t content1,
    ubjson_type_t type2,
    ssize_t content2);

/**
 * Function to parse an array of uint8_t from a ubjson document.
 *
 * @param[inout] dest    The buffer to write to
 * @param[inout] len     The current position in the buffer/length of data written
 * @param[in]    max_len Size of the buffer
 */
static void _ubjson_parse_array(
    ubjson_cookie_t *__restrict__ cookie,
    uint8_t *dest,
    size_t *len,
    size_t max_len);

/**
 * Helper function to parse the inner parts of the command container
 *
 * Basically, we are within the outermost { and } when this function is called
 * for each key
 */
static inline ubjson_read_callback_result_t _ubjson_parse_container(
    ubjson_cookie_t *__restrict__ cookie,
    lora_daemon_parser_state_t *pState,
    ubjson_type_t type1,
    ssize_t content1,
    ubjson_type_t type2,
    ssize_t content2);

/**
 * Parse a single param entity within the container
 */
static inline ubjson_read_callback_result_t _ubjson_parse_param(
    ubjson_cookie_t *__restrict__ cookie,
    lora_daemon_parser_state_t *pState,
    ubjson_type_t type1,
    ssize_t content1,
    ubjson_type_t type2,
    ssize_t content2);

/**
 * Helper function to handle the root of the command.
 *
 * Checks for the container being an object (not array or primitive)
 */
static inline ubjson_read_callback_result_t _ubjson_parse_root(
    ubjson_cookie_t *__restrict__ cookie,
    lora_daemon_parser_state_t *pState,
    ubjson_type_t type1,
    ssize_t content1);

/**
 * Skips the next entities / container.
 *
 * Make sure to set the state to UBJ_SKIP before if you pass a container
 */
void _ubjson_skip_entity(
    ubjson_cookie_t *__restrict cookie,
    ubjson_type_t type,
    ssize_t content);

/**
 * Callback function that is used by the UBJSON parser to retrieve more data
 */
ssize_t _ubjson_read(ubjson_cookie_t *__restrict cookie, void *buf, size_t max_len);

int lora_daemon_parse_cmd(lora_daemon_t *daemon, lora_daemon_req_t *req)
{
    req->type = LORA_DAEMON_REQ_UNDEF;
    /* Create a parsing state and store it in the daemon */
    lora_daemon_parser_state_t pState = {
        .req = req,
        .ubj_state = UBJ_CONTAINER_INIT,
        .parser_failure = false,
        .input_finished = false,
        .ack_pid = KERNEL_PID_UNDEF,
    };
    daemon->parser_state = &pState;

    DEBUG("%s: ubjson_read()\n", daemon->name);
    ubjson_read_callback_result_t ubjson_res = ubjson_read(
        &(daemon->ubjson_cookie),
        _ubjson_read,
        _ubjson_entity_callback
    );

    /* Check / Wait for the stop message */
    DEBUG("%s: ubjson_read() returned, waiting for MTYPE_STOP.\n", daemon->name);
    bool success = !(pState.parser_failure || ubjson_res != UBJSON_OKAY);
    while (pState.input_finished != true) {
        msg_t msg;
        msg_receive(&msg);
        if (msg.type == LORA_DAEMON_MTYPE_ABORT) {
            DEBUG("%s: ERROR: Got MTYPE_ABORT\n", daemon->name);
            pState.input_finished = true;
            pState.parser_failure = true;
        }
        else if (msg.type == LORA_DAEMON_MTYPE_STOP) {
            DEBUG("%s: Received MTYPE_STOP\n", daemon->name);
            pState.input_finished = true;
            msg_t msg_ack;
            msg_ack.type = success ? LORA_DAEMON_MTYPE_DATA_ACK : LORA_DAEMON_MTYPE_DATA_ERR;
            msg_reply(&msg, &msg_ack);
        }
        success = !(pState.parser_failure || ubjson_res != UBJSON_OKAY);
    }
    DEBUG("%s: Parsing done.\n", daemon->name);

    /* Clear the pointer before it becomes invalid */
    daemon->parser_state = NULL;

    return success ? 0 : 1;
}

void _set_parameter(
    ubjson_cookie_t *__restrict__ cookie,
    lora_daemon_req_t *req,
    const char * param_name,
    const ubjson_type_t type,
    const ssize_t content)
{
#ifdef ENABLE_DEBUG
    lora_daemon_t *daemon = container_of(cookie, lora_daemon_t, ubjson_cookie);
    DEBUG("%s: Processing parameter \"%s\"\n", daemon->name, param_name);
#endif
    switch(req->type) {
        case LORA_DAEMON_REQ_CONFIGURE_GAIN:
            _set_param_configure_gain(cookie, &(req->params.configure_gain), param_name, type, content);
            break;
        case LORA_DAEMON_REQ_ENABLE_RC_JAMMER:
            _set_param_enable_rc_jammer(cookie, &(req->params.enable_rc_jammer), param_name, type, content);
            break;
        case LORA_DAEMON_REQ_ENABLE_SNIFFER:
            _set_param_enable_sniffer(cookie, &(req->params.enable_sniffer), param_name, type, content);
            break;
        case LORA_DAEMON_REQ_SET_JAMMER_PLENGTH:
            _set_param_jammer_set_plength(cookie,&(req->params.set_jammer_plength), param_name, type, content);
            break;
        case LORA_DAEMON_REQ_SET_LORA_CHANNEL:
            _set_param_lora_set_channel(cookie, &(req->params.set_lora_channel), param_name, type, content);
            break;
        case LORA_DAEMON_REQ_SET_PREAMBLE_LENGTH:
            _set_param_set_preamble_length(cookie, &(req->params.set_preamble_length), param_name, type, content);
            break;
        case LORA_DAEMON_REQ_SET_TXCRC:
            _set_param_set_txcrc(cookie, &(req->params.set_txcrc), param_name, type, content);
            break;
        case LORA_DAEMON_REQ_TRANSMIT_FRAME:
            _set_param_transmit_frame(cookie, &(req->params.transmit_frame), param_name, type, content);
            break;
        case LORA_DAEMON_REQ_FETCH_FRAME:
        case LORA_DAEMON_REQ_GET_LORA_CHANNEL:
        case LORA_DAEMON_REQ_GET_PREAMBLE_LENGTH:
        case LORA_DAEMON_REQ_GET_TIME:
        case LORA_DAEMON_REQ_GET_TXCRC:
        case LORA_DAEMON_REQ_RECEIVE:
        case LORA_DAEMON_REQ_STANDBY:
            /* body-less requests */
            _ubjson_skip_entity(cookie, type, content);
            break;
        case LORA_DAEMON_REQ_UNDEF:
            UNREACHABLE();
            break;
    }
}


void _set_param_configure_gain (
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_configure_gain_t *params,
    const char * param_name,
    ubjson_type_t type,
    ssize_t content)
{
    if (strcmp("lna_boost", param_name)==0 && type == UBJSON_TYPE_BOOL) {
        ubjson_get_bool(cookie, content, &(params->lna_boost));
        params->lna_boost_set = true;
    }
    else if (strcmp("lna_gain", param_name)==0 && type == UBJSON_TYPE_INT32) {
        int32_t val = 0;
        ubjson_get_i32(cookie, content, &val);
        if (0 < val && val <= 6) {
            params->lna_gain = (lora_lna_gain_t)val;
            params->lna_gain_set = true;
        }
    }
    else if (strcmp("pwr_out", param_name)==0 && type == UBJSON_TYPE_INT32) {
        int32_t val = 0;
        ubjson_get_i32(cookie, content, &val);
        if (val < 3 ) {
            params->pwr_out = LORA_PWR_OUT_0DBM;
        }
        else if (val < 8) {
            params->pwr_out = LORA_PWR_OUT_5DBM;
        }
        else if (val < 13) {
            params->pwr_out = LORA_PWR_OUT_10DBM;
        }
        else if (val <= 15) {
            params->pwr_out = LORA_PWR_OUT_15DBM;
        }
        else {
            params->pwr_out = LORA_PWR_OUT_MAX;
        }
        params->pwr_out_set=true;
    }
    else {
        _ubjson_skip_entity(cookie, type, content);
    }
}


void _set_param_enable_rc_jammer(
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_enable_rc_jammer_t *req,
    const char * param_name,
    const ubjson_type_t type,
    const ssize_t content)
{
    if (strcmp("trigger", param_name) == 0 && type == UBJSON_TYPE_INT32) {
        int32_t trigger = LORA_JAMMER_TRIGGER_NONE;
        ubjson_get_i32(cookie, content, &trigger);
        switch(trigger) {
            case LORA_JAMMER_TRIGGER_GPIO:
                req->trigger = LORA_JAMMER_TRIGGER_GPIO;
                break;
            case LORA_JAMMER_TRIGGER_UDP:
                req->trigger = LORA_JAMMER_TRIGGER_UDP;
                break;
            default:
                req->trigger = LORA_JAMMER_TRIGGER_NONE;
        }
    }
    else {
        _ubjson_skip_entity(cookie, type, content);
    }
}

void _set_param_enable_sniffer(
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_enable_sniffer_t *req,
    const char * param_name,
    const ubjson_type_t type,
    const ssize_t content)
{
    if(strcmp("pattern", param_name) == 0 && type == UBJSON_ENTER_ARRAY) {
        size_t dummy = 0;
        _ubjson_parse_array(cookie, req->pattern, &dummy,
            LORA_DAEMON_SNIFFER_PATTERN_MAX_LENGTH);
    }
    else if(strcmp("mask", param_name) == 0 && type == UBJSON_ENTER_ARRAY) {
        req->mask_length = 0;
        _ubjson_parse_array(cookie, req->mask, &(req->mask_length),
            LORA_DAEMON_SNIFFER_PATTERN_MAX_LENGTH);
    }
    else if(strcmp("rxbuf", param_name) == 0 && type == UBJSON_TYPE_BOOL) {
        ubjson_get_bool(cookie, content, &(req->rxbuf));
    }
    else if (strcmp("action", param_name) == 0 && type == UBJSON_TYPE_INT32) {
        int32_t action = LORA_SNIFFER_ACTION_NONE;
        ubjson_get_i32(cookie, content, &action);
        switch(action) {
            case LORA_SNIFFER_ACTION_GPIO:
                req->action = LORA_SNIFFER_ACTION_GPIO;
                break;
            case LORA_SNIFFER_ACTION_INTERNAL:
                req->action = LORA_SNIFFER_ACTION_INTERNAL;
                break;
            case LORA_SNIFFER_ACTION_UDP:
                req->action = LORA_SNIFFER_ACTION_UDP;
                break;
            default:
                req->action = LORA_SNIFFER_ACTION_NONE;
        }
    }
#ifdef MODULE_LORA_MODEM_JAMMER_UDP
    else if (strcmp("addr", param_name) == 0 &&
        type == UBJSON_TYPE_STRING && content < (ssize_t)IPV6_ADDR_MAX_STR_LEN) {
        char addr_str[IPV6_ADDR_MAX_STR_LEN];
        addr_str[content] = 0;
        ubjson_get_string(cookie, content, addr_str);
        if (ipv6_addr_from_str(&(req->addr), addr_str) == NULL) {
            DEBUG("lora_daemon: Could not parse jammer IPv6 from \"%s\"\n", addr_str);
        }
    }
#endif
    else {
        _ubjson_skip_entity(cookie, type, content);
    }
}

void _set_param_jammer_set_plength(
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_set_jammer_plength_t *params,
    const char * param_name,
    ubjson_type_t type,
    ssize_t content)
{
    if (strcmp("len", param_name)==0 && type == UBJSON_TYPE_INT32) {
        int32_t val = 0;
        ubjson_get_i32(cookie, content, &val);
        params->length = (uint8_t)val;
    }
    else {
        _ubjson_skip_entity(cookie, type, content);
    }
}

void _set_param_lora_set_channel(
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_set_lora_channel_t *params,
    const char * param_name,
    const ubjson_type_t type,
    const ssize_t content)
{
    /* Most parameters are numbers that will be mapped to TYPE_INT32, so we can
     * do typecheking once */
    if (type == UBJSON_TYPE_INT32) {
        int32_t val = 0;
        ubjson_get_i32(cookie, content, &val);

        if(strcmp("frequency", param_name) == 0) {
            params->frequency = (uint32_t)val;
            params->frequency_set = true;
        }
        else if (strcmp("bandwidth", param_name) == 0) {
            params->bandwidth = (uint16_t)val;
            params->bandwidth_set = true;
        }
        else if (strcmp("spreadingfactor", param_name) == 0) {
            params->spreading_factor = (uint8_t)val;
            params->spreading_factor_set = true;
        }
        else if (strcmp("syncword", param_name) == 0) {
            params->syncword = (uint8_t)val;
            params->syncword_set = true;
        }
        else if (strcmp("codingrate", param_name) == 0) {
            params->coding_rate = (uint8_t)val;
            params->coding_rate_set = true;
        }
    }
    else if (type == UBJSON_TYPE_BOOL) {
        if (strcmp("invertiqrx", param_name) == 0) {
            ubjson_get_bool(cookie, content, &(params->invertiqrx));
            params->invertiqrx_set = true;
        }
        else if (strcmp("invertiqtx", param_name) == 0) {
            ubjson_get_bool(cookie, content, &(params->invertiqtx));
            params->invertiqtx_set = true;
        }
        else if (strcmp("explicitheader", param_name) == 0) {
            ubjson_get_bool(cookie, content, &(params->explicitheader));
            params->explicitheader_set = true;
        }
    }
    else {
        _ubjson_skip_entity(cookie, type, content);
    }
}

void _set_param_set_preamble_length (
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_set_preamble_length_t *params,
    const char * param_name,
    ubjson_type_t type,
    ssize_t content)
{
    if (strcmp("len", param_name)==0 && type == UBJSON_TYPE_INT32) {
        int32_t val = 0;
        ubjson_get_i32(cookie, content, &val);
        params->length = (uint16_t)val;
    }
    else {
        _ubjson_skip_entity(cookie, type, content);
    }
}

void _set_param_set_txcrc (
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_set_txcrc_t *params,
    const char * param_name,
    ubjson_type_t type,
    ssize_t content)
{
    if (strcmp("txcrc", param_name)==0 && type == UBJSON_TYPE_BOOL) {
        params->txcrc_set = true;
        ubjson_get_bool(cookie, content, &(params->txcrc));
    }
    else {
        _ubjson_skip_entity(cookie, type, content);
    }
}

void _set_param_transmit_frame(
    ubjson_cookie_t *__restrict cookie,
    lora_daemon_req_transmit_frame_t *req,
    const char * param_name,
    const ubjson_type_t type,
    const ssize_t content)
{
    if(strcmp("payload", param_name) == 0 && type == UBJSON_ENTER_ARRAY) {
        req->length = 0;
        _ubjson_parse_array(cookie, req->payload, &(req->length), LORA_PAYLOAD_MAX_LENGTH);
    }
    else if(strcmp("time", param_name) == 0) {
        if (type == UBJSON_TYPE_INT32) {
            int32_t val = 0;
            ubjson_get_i32(cookie, content, &val);
            req->time_set = true;
            req->blocking = false;
            req->time = (uint64_t)val;
        }
        else if (type == UBJSON_TYPE_INT64) {
            int64_t val = 0;
            ubjson_get_i64(cookie, content, &val);
            req->time_set = true;
            req->blocking = false;
            req->time = (uint64_t)val;
        }
        else {
            _ubjson_skip_entity(cookie, type, content);
        }
    }
    else if (strcmp("blocking", param_name) == 0 && type == UBJSON_TYPE_BOOL) {
        req->time_set = false;
        ubjson_get_bool(cookie, content, &(req->blocking));
    }
    else {
        _ubjson_skip_entity(cookie, type, content);
    }
}

int _set_reqtype(lora_daemon_req_t *req, char *command_name)
{
    if (strcmp("configure_gain", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_CONFIGURE_GAIN;
        memset(&(req->params.configure_gain), 0, sizeof(req->params.configure_gain));
    }
    else if (strcmp("enable_rc_jammer", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_ENABLE_RC_JAMMER;
        memset(&(req->params.enable_rc_jammer), 0, sizeof(req->params.enable_rc_jammer));
        req->params.enable_rc_jammer.trigger = LORA_JAMMER_TRIGGER_NONE;
    }
    else if (strcmp("enable_sniffer", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_ENABLE_SNIFFER;
        memset(&(req->params.enable_sniffer), 0, sizeof(req->params.enable_sniffer));
        req->params.enable_sniffer.action = LORA_SNIFFER_ACTION_NONE;
    }
    else if (strcmp("fetch_frame", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_FETCH_FRAME;
    }
    else if (strcmp("get_lora_channel", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_GET_LORA_CHANNEL;
    }
    else if (strcmp("get_preamble_length", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_GET_PREAMBLE_LENGTH;
    }
    else if (strcmp("get_time", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_GET_TIME;
    }
    else if (strcmp("get_txcrc", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_GET_TXCRC;
    }
    else if (strcmp("set_jammer_plen", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_SET_JAMMER_PLENGTH;
        req->params.set_jammer_plength.length = 0;
    }
    else if (strcmp("set_lora_channel", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_SET_LORA_CHANNEL;
        memset(&(req->params.set_lora_channel), 0,
            sizeof(req->params.set_lora_channel));
    }
    else if (strcmp("set_preamble_length", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_SET_PREAMBLE_LENGTH;
        req->params.set_preamble_length.length = 0;
    }
    else if (strcmp("set_txcrc", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_SET_TXCRC;
        req->params.set_txcrc.txcrc_set = false;
    }
    else if (strcmp("receive", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_RECEIVE;
    }
    else if (strcmp("standby", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_STANDBY;
    }
    else if (strcmp("transmit_frame", command_name) == 0) {
        req->type = LORA_DAEMON_REQ_TRANSMIT_FRAME;
        req->params.transmit_frame.length = 0;
        req->params.transmit_frame.time_set = false;
    }
    else {
        return 1;
    }
    return 0;
}

ubjson_read_callback_result_t _ubjson_entity_callback(
    ubjson_cookie_t *__restrict__ cookie,
    ubjson_type_t type1,
    ssize_t content1,
    ubjson_type_t type2,
    ssize_t content2)
{
    lora_daemon_t *daemon = container_of(cookie, lora_daemon_t, ubjson_cookie);
    lora_daemon_parser_state_t *pState = (lora_daemon_parser_state_t*)(daemon->parser_state);

    /* Handle NOOP centrally: Skip this entity */
    if (type1 != UBJSON_TYPE_NOOP) {
        if (pState->ubj_state == UBJ_PARAMS) {
            _ubjson_parse_param(cookie, pState, type1, content1, type2, content2);
        }
        else if (pState->ubj_state == UBJ_CONTAINER_INIT) {
            /* Parse the root (check if it's an object and dive into it) */
            _ubjson_parse_root(cookie, pState, type1, content1);
        }
        else if (pState->ubj_state == UBJ_CONTAINER) {
            /* Parse the main container */
            _ubjson_parse_container(cookie, pState, type1, content1, type2, content2);
        }
        else if (pState->ubj_state == UBJ_SKIP) {
            /* We are skipping the current element/container */
            if (type1 == UBJSON_KEY || type1 == UBJSON_INDEX) {
                /* Container entry */
                ubjson_peek_value(cookie, &type2, &content2);
                _ubjson_skip_entity(cookie, type2, content2);
            }
            else {
                /* Primitive */
                _ubjson_skip_entity(cookie, type1, content1);
            }
        }
    }

    return UBJSON_OKAY;
}

static void _ubjson_parse_array(
    ubjson_cookie_t *__restrict__ cookie,
    uint8_t *dest,
    size_t *len,
    size_t max_len)
{
    lora_daemon_t *daemon = container_of(cookie, lora_daemon_t, ubjson_cookie);
    lora_daemon_parser_state_t *pState = (lora_daemon_parser_state_t*)(daemon->parser_state);
    DEBUG("%s: Start parsing of array parameter\n", daemon->name);
    pState->arr_buffer = dest;
    pState->arr_idx = len;
    pState->arr_len = max_len;
    /* We temporarily replace the callback to not interfere with the
     * overall parsing process */
    ubjson_read_callback_t prevCallback = cookie->callback.read;
    cookie->callback.read = _ubjson_parse_array_param;
    /* Read the array (all element calls will go to ubjson_parse_array_param) */
    ubjson_read_array(cookie);
    /* Restore the callback */
    cookie->callback.read = prevCallback;
    DEBUG("%s: Finish parsing of array parameter, read %d bytes.\n", daemon->name, *len);
}

static ubjson_read_callback_result_t _ubjson_parse_array_param(
    ubjson_cookie_t *__restrict__ cookie,
    ubjson_type_t type1,
    ssize_t content1,
    ubjson_type_t type2,
    ssize_t content2)
{
    lora_daemon_t *daemon = container_of(cookie, lora_daemon_t, ubjson_cookie);
    lora_daemon_parser_state_t *pState = (lora_daemon_parser_state_t*)(daemon->parser_state);
    if (pState->ubj_state == UBJ_SKIP) {
        /* Skipping is the same as in _ubjson_entity_callback. We need to
         * provide the skipping code here too, as this is the current handler
         * callback, and _ubjson_skip_entity relies on this */
        DEBUG("%s: Skipping inner element in array parameter\n", daemon->name);
        if (type1 == UBJSON_KEY || type1 == UBJSON_INDEX) {
            ubjson_peek_value(cookie, &type2, &content2);
            _ubjson_skip_entity(cookie, type2, content2);
        }
        else {
            _ubjson_skip_entity(cookie, type1, content1);
        }
        return UBJSON_OKAY;
    }
    else if (type1 == UBJSON_INDEX && ubjson_peek_value(cookie, &type2, &content2) == UBJSON_OKAY) {
        size_t idx = *(pState->arr_idx);
        if (idx < pState->arr_len) {
            int32_t val = 0;
            if (type2 == UBJSON_TYPE_INT32) {
                ubjson_get_i32(cookie, content2, &val);
                DEBUG("%s: Got array element: 0x%02x\n", daemon->name, (uint8_t)val);
            }
            else {
                DEBUG("%s: Got non-numeric array element: 0x00\n", daemon->name);
                _ubjson_skip_entity(cookie, type2, content2);
            }
            pState->arr_buffer[idx] = (uint8_t)val;
            *(pState->arr_idx) = idx+1;
        }
        else {
            DEBUG("%s: Array exceeds max length of %d.\n", daemon->name, pState->arr_len);
            pState->parser_failure = true;
        }
        return UBJSON_OKAY;
    }
    else {
        DEBUG("%s: Parsing array parameter, but got other primary type than index\n", daemon->name);
        pState->parser_failure = true;
        return UBJSON_INVALID_DATA;
    }
}

static inline ubjson_read_callback_result_t _ubjson_parse_container(
    ubjson_cookie_t *__restrict__ cookie,
    lora_daemon_parser_state_t *pState,
    ubjson_type_t type1,
    ssize_t content1,
    ubjson_type_t type2,
    ssize_t content2)
{
    lora_daemon_t *daemon = container_of(cookie, lora_daemon_t, ubjson_cookie);
    DEBUG("%s: Parsing container content\n", daemon->name);
    if (type1 == UBJSON_KEY) {
        char key[content1 + 1];
        memset(key, 0, content1 + 1);
        ubjson_get_string(cookie, content1, key);
        DEBUG("%s: Got key \"%s\"\n", daemon->name, key);

        /* Get type of the second field */
        ubjson_peek_value(cookie, &type2, &content2);
        if (type2 == UBJSON_ENTER_OBJECT) {
            if (_set_reqtype(pState->req, key) == 0) {
                /* Start parsing parameters */
                pState->ubj_state = UBJ_PARAMS;
                ubjson_read_object(cookie);
                pState->ubj_state = UBJ_CONTAINER_DONE;
            }
            else {
                /* Discard the value and all children */
                DEBUG("%s: WARN: Unknown command: %s\n", daemon->name, key);
                pState->ubj_state = UBJ_SKIP;
                ubjson_read_object(cookie);
                pState->ubj_state = UBJ_CONTAINER;
            }
        }
        else {
            /* Discard the value and all children */
            DEBUG("%s: Unexpected top-level object\n", daemon->name);
            _ubjson_skip_entity(cookie, type2, content2);
        }
    }
    else {
        DEBUG("%s: Parsing object, but got other entity than key\n", daemon->name);
        pState->parser_failure = true;
    }
    return UBJSON_OKAY;
}

static inline ubjson_read_callback_result_t _ubjson_parse_param(
    ubjson_cookie_t *__restrict__ cookie,
    lora_daemon_parser_state_t *pState,
    ubjson_type_t type1,
    ssize_t content1,
    ubjson_type_t type2,
    ssize_t content2)
{
    /* We're only interested in strings */
    if (type1 == UBJSON_KEY) {
        char param_name[content1 + 1];
        memset(param_name, 0, content1 + 1);
        ubjson_get_string(cookie, content1, param_name);

        ubjson_peek_value(cookie, &type2, &content2);
        if (type2 == UBJSON_ENTER_OBJECT) {
            /* Skip the container */
            _ubjson_skip_entity(cookie, type2, content2);
        }
        else {
            /* Real parameter or array */
            _set_parameter(cookie, pState->req, param_name, type2, content2);
        }
    }
    else {
        _ubjson_skip_entity(cookie, type1, content1);
    }
    return UBJSON_OKAY;
}

static inline ubjson_read_callback_result_t _ubjson_parse_root(
    ubjson_cookie_t *__restrict__ cookie,
    lora_daemon_parser_state_t *pState,
    ubjson_type_t type1,
    ssize_t content1)
{
#ifdef ENABLE_DEBUG
    lora_daemon_t *daemon = container_of(cookie, lora_daemon_t, ubjson_cookie);
    DEBUG("%s: Parsing container\n", daemon->name);
#endif
    if (type1 == UBJSON_ENTER_OBJECT) {
        pState->ubj_state = UBJ_CONTAINER;
        ubjson_read_object(cookie);
        /* If we are not in UBJ_CONTAINER now, we have no command and the
            * container has been parsed completely without result */
        if (pState->ubj_state != UBJ_CONTAINER_DONE) {
#ifdef ENABLE_DEBUG
            DEBUG("%s: ERROR: Request container incomplete\n", daemon->name);
#endif
            pState->parser_failure = true;
        }
    }
    else  {
        /* Top-Level Array? Or primitive? Nope. */
#ifdef ENABLE_DEBUG
            DEBUG("%s: ERROR: Invalid top-level object in request\n", daemon->name);
#endif
        pState->parser_failure = true;
        pState->ubj_state = UBJ_SKIP;
        if (type1 == UBJSON_ENTER_ARRAY) {
            ubjson_read_array(cookie);
        }
        else {
            _ubjson_skip_entity(cookie, type1, content1);
        }
    }
    return UBJSON_OKAY;
}

void _ubjson_skip_entity(
    ubjson_cookie_t *__restrict cookie,
    ubjson_type_t type,
    ssize_t content)
{
    switch (type) {
        case UBJSON_ENTER_ARRAY:
        case UBJSON_ENTER_OBJECT: {
            lora_daemon_t *daemon = container_of(cookie, lora_daemon_t, ubjson_cookie);
            lora_daemon_parser_state_t *pState = (lora_daemon_parser_state_t*)(daemon->parser_state);
            lora_daemon_parser_stateflag_t ubj_state_before = pState->ubj_state;
            pState->ubj_state = UBJ_SKIP;
            if (type == UBJSON_ENTER_ARRAY) {
                ubjson_read_array(cookie);
            }
            else {
                ubjson_read_object(cookie);
            }
            pState->ubj_state = ubj_state_before;
            break;
        }
        case UBJSON_TYPE_BOOL: {
            bool b;
            ubjson_get_bool(cookie, content, &b);
            break;
        }
        case UBJSON_TYPE_DOUBLE: {
            double d;
            ubjson_get_double(cookie, content, &d);
            break;
        }
        case UBJSON_TYPE_FLOAT: {
            float f;
            ubjson_get_float(cookie, content, &f);
            break;
        }
        case UBJSON_TYPE_INT32: {
            int32_t i;
            ubjson_get_i32(cookie, content, &i);
            break;
        }
        case UBJSON_TYPE_INT64: {
            int64_t i;
            ubjson_get_i64(cookie, content, &i);
            break;
        }
        case UBJSON_KEY:
        case UBJSON_TYPE_STRING: {
            /* As strings may have arbitrary length, we manually skip them in small portions */
            ssize_t bytes_remaining = content;
            uint8_t buf[16];
            do {
                ssize_t res = cookie->rw.read(cookie, buf, (ssize_t)sizeof(buf) < bytes_remaining ?
                     (ssize_t)sizeof(buf) : bytes_remaining);
                bytes_remaining -= (res < 0) ? bytes_remaining : res;
            } while(bytes_remaining > 0);
        }
        case UBJSON_INDEX:
        case UBJSON_TYPE_NOOP:
        case UBJSON_TYPE_NULL:
        case UBJSON_ABSENT:
            break;
    }
}

ssize_t _ubjson_read(ubjson_cookie_t *__restrict cookie, void *buf, size_t max_len)
{
    lora_daemon_t *daemon = container_of(cookie, lora_daemon_t, ubjson_cookie);
    lora_daemon_parser_state_t *pState = (lora_daemon_parser_state_t*)(daemon->parser_state);

    DEBUG("%s: _ubjson_read(%i bytes) (queue: %i msgs)\n",
        daemon->name, max_len, msg_avail());

    msg_t msg_in;
    msg_receive(&msg_in);
    if (msg_in.type == LORA_DAEMON_MTYPE_DATA) {
        lora_daemon_msg_data_t *data = msg_in.content.ptr;
        DEBUG("%s: _ubjson_read got MTYPE_DATA (%i bytes)\n", daemon->name, data->size);
        if (data->size <= max_len) {
            /* We can write the whole message content at once */
            memcpy(buf, data->data, data->size);

            msg_t msg_ack;
            msg_ack.type = LORA_DAEMON_MTYPE_DATA_ACK;
            DEBUG("%s: _ubjson_read send MTYPE_ACK to PID %" PRIkernel_pid "\n",
                daemon->name, data->ack_to);
            msg_send(&msg_ack, data->ack_to);

            return data->size;
        }
        else {
            /* Write as much data as we can, then send the message to ourselves
             * for the next call to _ubjson_read, so eventually, the message will
             * be processed completely */
            memcpy(buf, data->data, max_len);
            msg_t msg_forward;
            msg_forward.type = LORA_DAEMON_MTYPE_DATA;
            msg_forward.content.ptr = data;
            data->data += max_len;
            data->size -= max_len;
            DEBUG("%s: _ubjson_read self-send MTYPE_DATA (%i bytes remain)\n",
                daemon->name, data->size);
            msg_send_to_self(&msg_forward);
            return max_len;
        }
    }
    else if (msg_in.type == LORA_DAEMON_MTYPE_ABORT || LORA_DAEMON_MTYPE_STOP) {
        /* This is an early abort caused by releasing the daemon to early. If
         * a complete object is parsed, the UBJson implementation itself will
         * stop calling _ubjson_read */
        pState->input_finished = true;
        pState->parser_failure = true;
        if (msg_in.type == LORA_DAEMON_MTYPE_STOP) {
            DEBUG("%s: ERROR: Got MTYPE_STOP to early\n", daemon->name);
            msg_t msg_out;
            msg_out.type = LORA_DAEMON_MTYPE_DATA_ACK;
            msg_reply(&msg_in, &msg_out);
        }
        else {
            DEBUG("%s: ERROR Got MTYPE_ABORT\n", daemon->name);
        }
        return -1;
    }
    else {
        DEBUG("%s: _ubjson_read - Unexpected msg_type: %d\n",
            daemon->name, msg_in.type);
        return 0;
    }
}