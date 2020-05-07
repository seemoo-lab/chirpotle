#include "stdio_null.h"

void stdio_init(void)
{

}

ssize_t stdio_read(void* buffer, size_t max_len)
{
    (void)buffer;
    (void)max_len;
    return 0;
}

ssize_t stdio_write(const void* buffer, size_t len)
{
    (void)buffer;
    return len;
}