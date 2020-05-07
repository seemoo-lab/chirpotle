#ifdef MODULE_ESP_WIFI
#include "if_wifi.h"

#include <stdio.h>

#include "net/gnrc/ipv6.h"
#include "net/gnrc/ipv6/hdr.h"
#include "net/gnrc/netif.h"

#define ENABLE_DEBUG (0)
#include "debug.h"

static char addr_str[IPV6_ADDR_MAX_STR_LEN];

static gnrc_netif_t *esp_wifi_if = NULL;

static ipv6_addr_t static_address;

gnrc_netif_t *find_wifi_interface(void)
{
    /* We assume that there is only one net interface */
    gnrc_netif_t *netif = gnrc_netif_iter(NULL);
    if (gnrc_netif_iter(netif) != NULL) {
        DEBUG("wifi_esp32: Found more than one net interface!\n");
        return NULL;
    }
    return netif;
}

int if_wifi_init(void)
{
    esp_wifi_if = find_wifi_interface();
    if (esp_wifi_if == NULL) {
        DEBUG("wifi_esp32: Could not find esp_wifi interface\n");
        return 1;
    }

#ifdef WIFI_IPV6
    if (ipv6_addr_from_str(&static_address, WIFI_IPV6) == NULL) {
        DEBUG("wifi_esp32: Cannot convert \"%s\" to an IPv6.\n", WIFI_IPV6);
    }
    else {
        if (gnrc_netif_ipv6_addr_add(esp_wifi_if, &static_address, 64,
            GNRC_NETIF_IPV6_ADDRS_FLAGS_STATE_VALID) < 0) {
            DEBUG("wifi_esp32: Adding %s/64 to wifi interface failed.\n", WIFI_IPV6);
        }
        else {
            DEBUG("wifi_esp32: Added %s/64 to wifi interface.\n", WIFI_IPV6);
        }
    }
#endif

    /*
     * TODO:
     * Does esp_wifi have some way of finding out if it's connected?
     */

    return 0;
}

void if_wifi_dumpaddr(void)
{
    ipv6_addr_t addrs[GNRC_NETIF_IPV6_ADDRS_NUMOF];
    int addr_count = gnrc_netif_ipv6_addrs_get(esp_wifi_if,
        addrs, GNRC_NETIF_IPV6_ADDRS_NUMOF * sizeof(ipv6_addr_t)) /
        sizeof(ipv6_addr_t);

    printf("wifi_esp32: Configured addresses:\n");
    for(int idx = 0; idx < addr_count; idx++) {
        printf("  %s\n", ipv6_addr_to_str(addr_str, &(addrs[idx]), sizeof(addr_str)));
    }
}

#else
typedef int dont_be_pedantic;
#endif /* MODULE_ESP_WIFI */