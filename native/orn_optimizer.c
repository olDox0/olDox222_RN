#include "orn_optimizer.h"
#include <immintrin.h>

int orn_compute_reuse(
    const llama_token *history,
    int history_len,
    const llama_token *incoming,
    int incoming_len
) {
    int i = 0;
    while (i < history_len && i < incoming_len && history[i] == incoming[i]) {
        i++;
    }
    return i;
}

int orn_compute_reuse_simd(
    const llama_token *a,
    const llama_token *b,
    int max_len
) {
    int i = 0;

    for (; i + 4 <= max_len; i += 4) {
        __m128i va = _mm_loadu_si128((const __m128i*)&a[i]);
        __m128i vb = _mm_loadu_si128((const __m128i*)&b[i]);

        __m128i cmp = _mm_cmpeq_epi32(va, vb);
        int mask = _mm_movemask_epi8(cmp);

        if (mask != 0xFFFF) break;
    }

    while (i < max_len && a[i] == b[i]) i++;

    return i;
}

orn_reuse_info orn_analyze_reuse(
    const llama_token *history,
    int history_len,
    const llama_token *incoming,
    int incoming_len
) {
    orn_reuse_info info;

    int max_len = history_len < incoming_len ? history_len : incoming_len;

    int reused = orn_compute_reuse_simd(history, incoming, max_len);

    info.reused_tokens = reused;
    info.new_tokens = incoming_len - reused;

    return info;
}