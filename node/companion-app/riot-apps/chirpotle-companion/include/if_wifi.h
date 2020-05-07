#ifndef IF_WIFI_H
#define IF_WIFI_H

#ifdef WITH_WIFI

#include "net/gnrc/netif.h"

#ifdef __cplusplus
extern "C" {
#endif

/** Returns the wifi interface that is used */
gnrc_netif_t *find_wifi_interface(void);

/**
 * Initializes the WiFi module to use it with the if_tcp
 *
 * @return 0    if setting up the interface worked
 * @return !=0  if there was an error
 */
int if_wifi_init(void);

/**
 * Dumps all wifi addresses to the standard output
 */
void if_wifi_dumpaddr(void);

#ifdef __cplusplus
}
#endif

#endif /* def(WITH_WIFI) */

#endif