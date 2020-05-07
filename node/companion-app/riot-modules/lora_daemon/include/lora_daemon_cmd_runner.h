#ifndef LORA_DAEMON_CMD_RUNNER_H
#define LORA_DAEMON_CMD_RUNNER_H

#include "lora_daemon.h"
#include "lora_daemon_internal.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Runs a request against the lora_modem and returns the result
 *
 * @param[in]    daemon The daemon to run this command for
 * @param[in]    req    The request object
 * @param[out]   res    The response object (only valid if no error occured)
 */
void lora_daemon_run_cmd(lora_daemon_t *daemon, lora_daemon_req_t *req, lora_daemon_res_t *res);

#ifdef __cplusplus
}
#endif

#endif
