#ifndef LORA_DAEMON_REQ_PARSER_H
#define LORA_DAEMON_REQ_PARSER_H

#include <stdint.h>
#include <stdbool.h>

#include "lora_daemon.h"
#include "lora_daemon_internal.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    /* First call to the parser callback */
    UBJ_CONTAINER_INIT,
    /* We're in the top-level container */
    UBJ_CONTAINER,
    /* Still in the container, but we had at least one valid key */
    UBJ_CONTAINER_DONE,
    /* Parse params */
    UBJ_PARAMS,
    /* Skip a container */
    UBJ_SKIP,
} lora_daemon_parser_stateflag_t;

typedef struct lora_daemon_parser_state {
    /** The request to parse into */
    lora_daemon_req_t * req;
    /** Position in parsing the the object */
    lora_daemon_parser_stateflag_t ubj_state;
    /** If the parser failed */
    bool parser_failure;
    /** If the parser received the MTYPE_STOP message */
    bool input_finished;
    /** PID of the process that is waiting for ACK */
    kernel_pid_t ack_pid;
    /** Array parsing information: Buffer */
    uint8_t *arr_buffer;
    /** Array parsing information: Buffer index */
    size_t *arr_idx;
    /** Array parsing information: Buffer size */
    size_t arr_len;
} lora_daemon_parser_state_t;

/**
 * @brief Parses a request object into the req parameter
 *
 * @param[inout] daemon The daemon to use
 * @param[out]   req    The request object
 *
 * @return 0     Success
 * @return 1     Parsing failed
 */
int lora_daemon_parse_cmd(lora_daemon_t *daemon, lora_daemon_req_t *req);

#ifdef __cplusplus
}
#endif

#endif