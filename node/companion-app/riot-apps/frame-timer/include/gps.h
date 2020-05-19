#ifndef _BEACON_TOOL_GPS_H
#define _BEACON_TOOL_GPS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/**
 * Enables dumping all received NMEA records to stdout
 */
void gps_enable_dump(bool dump);

/**
 * Returnes the number of currently tracked sattelites
 */
int gps_get_sattelites(void);

/**
 * Returns whether the current data is valid
 */
bool gps_get_valid(void);

/**
 * Returns the current GPS time
 */
uint32_t gps_get_time(void);

/**
 * Converts local time in gps time (given in usec)
 */
uint64_t gps_local2gpstime(uint64_t localtime);

/** GPS thread, updates the current time */
void *thread_gps(void *arg);

#endif