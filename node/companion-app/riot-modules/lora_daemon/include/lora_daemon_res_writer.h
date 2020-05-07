#ifndef LORA_DAEMON_RES_WRITER_H
#define LORA_DAEMON_RES_WRITER_H

#include "lora_daemon.h"
#include "lora_daemon_internal.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Converts a result object to UBJSON
 *
 * @param[in]    daemon The daemon to run this command for
 * @param[in]    res    The response object
 */
void lora_daemon_write_res(lora_daemon_t *daemon, lora_daemon_res_t *res);

#ifdef __cplusplus
}
#endif

#endif
