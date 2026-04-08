// native/orn_varint.c
#include <stdint.h>
#include <stddef.h>

#if defined(_WIN32)
#define ORN_API __declspec(dllexport)
#else
#define ORN_API
#endif

ORN_API size_t orn_encode_varint_u64(uint64_t value, uint8_t *out) {
    size_t n = 0;
    while (value >= 0x80) {
        out[n++] = (uint8_t)((value & 0x7F) | 0x80);
        value >>= 7;
    }
    out[n++] = (uint8_t)value;
    return n;
}