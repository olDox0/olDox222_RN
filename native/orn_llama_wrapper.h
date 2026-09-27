#ifndef ORN_LLAMA_WRAPPER_H
#define ORN_LLAMA_WRAPPER_H

#ifdef _WIN32
#define ORN_API __declspec(dllexport)
#else
#define ORN_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

ORN_API int orn_init(const char* model_path, int n_ctx, int n_threads);

ORN_API int orn_infer(
    const char* prompt,
    int max_tokens,
    char* output,
    int output_size
);

typedef int (*orn_token_cb)(const char* piece, int n_bytes, void* user_data);

ORN_API int orn_infer_stream(
    const char*    prompt,
    int            max_tokens,
    orn_token_cb   callback,
    void*          user_data
);

ORN_API void orn_free(void);

/* NOVA: Trunca o KV-cache para reutilização de prefixo */
ORN_API void orn_kv_truncate(int keep_tokens);

#ifdef __cplusplus
}
#endif
#endif
