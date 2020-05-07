#ifndef LORA_IF_H
#define LORA_IF_H

#include "lora_daemon.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
    /** Setup went well */
    LORA_INTERFACE_SETUP_OK,
    /** Setup failed */
    LORA_INTERFACE_SETUP_FAIL,
    /** Missing device (e.g. network or uart interface) */
    LORA_INTERFACE_DEV_MISSING,
};

/** Return values used for escape sequences used in the stream */
enum {
    /** Escapes a binary zero: 0x00 (data) <-> 0x00 0x00 (stream) */
    ESCSEQ_ZERO = 0x00,
    /** Used immediately before the start of an object. 0x00 0x01 (stream) */
    ESCSEQ_OBJ_START = 0x101,
    /** Used immediately after the end of an object. 0x00 0x02 (stream) */
    ESCSEQ_OBJ_END   = 0x102,
    /** Heartbeat request */
    ESCSEQ_PING      = 0x103,
    /** Heartbeat response */
    ESCSEQ_PONG      = 0x104,
};

typedef struct lora_interface {
    /** Callback used to initialize this interface */
    int (*init)(lora_daemon_t *daemon);
    /** Callback used to start this interface */
    void (*start)(void);
} lora_interface_t;

#ifdef __cplusplus
}
#endif

#endif