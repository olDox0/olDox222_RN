#ifndef ORN_OPTIMIZER_H
#define ORN_OPTIMIZER_H

#include "llama.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int reused_tokens;
    int new_tokens;
} orn_reuse_info;

int orn_compute_reuse(
    const llama_token *history,
    int history_len,
    const llama_token *incoming,
    int incoming_len
);

int orn_compute_reuse_simd(
    const llama_token *a,
    const llama_token *b,
    int max_len
);

orn_reuse_info orn_analyze_reuse(
    const llama_token *history,
    int history_len,
    const llama_token *incoming,
    int incoming_len
);

#ifdef __cplusplus
}
#endif

#endif