#include "orn_llama_wrapper.h"
#include "llama.h"

#include <string.h>
#include <stdlib.h>
#include <time.h>

#define ORN_MAX_PROMPT_TOKENS 2048
#define ORN_MAX_PIECE_BYTES    256

static struct llama_model    * g_model   = NULL;
static struct llama_context  * g_ctx     = NULL;
static struct llama_sampler  * g_smpl    = NULL;
static const struct llama_vocab * g_vocab = NULL;
static int g_ready = 0;

// Guarda as configurações para recriar o contexto
static int g_saved_n_ctx = 512;
static int g_saved_n_threads = 2;

static void orn_silent_log_callback(enum ggml_log_level level, const char * text, void * user_data)
{
    (void)level;
    (void)text;
    (void)user_data;
}

static void orn_reset_state(void)
{
    if (g_smpl) {
        llama_sampler_reset(g_smpl);
    }
}

void orn_free(void)
{
    if (g_smpl) {
        llama_sampler_free(g_smpl);
        g_smpl = NULL;
    }
    if (g_ctx) {
        llama_free(g_ctx);
        g_ctx = NULL;
    }
    if (g_model) {
        llama_model_free(g_model);
        g_model = NULL;
    }
    g_vocab = NULL;
    g_ready = 0;
    llama_backend_free();
}

int orn_init(const char* model_path, int n_ctx, int n_threads)
{
    if (!model_path || !model_path[0]) return -10;
    if (g_ready) orn_free();
    
    llama_log_set(orn_silent_log_callback, NULL);
    llama_backend_init();

    // Salva os parametros para usar na recriação
    g_saved_n_ctx = n_ctx;
    g_saved_n_threads = n_threads;

    struct llama_model_params mparams = llama_model_default_params();
    mparams.n_gpu_layers = 0;

    g_model = llama_model_load_from_file(model_path, mparams);
    if (!g_model) { orn_free(); return -1; }

    g_vocab = llama_model_get_vocab(g_model);
    if (!g_vocab) { orn_free(); return -2; }

    struct llama_context_params cparams = llama_context_default_params();
    cparams.n_ctx            = (n_ctx > 0)     ? n_ctx     : 512;
    cparams.n_batch          = 64;
    cparams.n_ubatch         = 64;
    cparams.n_threads        = (n_threads > 0) ? n_threads : 2;
    cparams.n_threads_batch  = cparams.n_threads; 
    cparams.flash_attn_type  = true;

    g_ctx = llama_init_from_model(g_model, cparams);
    if (!g_ctx) { orn_free(); return -3; }

    struct llama_sampler_chain_params sparams = llama_sampler_chain_default_params();
    g_smpl = llama_sampler_chain_init(sparams);
    if (!g_smpl) { orn_free(); return -4; }

    llama_sampler_chain_add(g_smpl, llama_sampler_init_greedy());

    g_ready = 1;
    return 0;
}

int orn_infer(const char* prompt, int max_tokens, char* output, int output_size)
{
    if (!g_ready || !g_model || !g_smpl || !g_vocab) return -1;
    if (!prompt || !output || output_size <= 1 || max_tokens <= 0) return -2;

    // APARECI AQUI E APAGUEI TODO AQUELE BLOCO "RECRIA O CONTEXTO..."

    output[0] = '\0';
    orn_reset_state(); // Apenas limpa a aleatoriedade (sampler)

    llama_token prompt_tokens[ORN_MAX_PROMPT_TOKENS];
    const int n_prompt_bytes = (int)strlen(prompt);
    int n_tokens = llama_tokenize(g_vocab, prompt, n_prompt_bytes,
                                  prompt_tokens, ORN_MAX_PROMPT_TOKENS, true, true);
    if (n_tokens < 0) return -3;
    if (n_tokens == 0) return -4;

    const int N_BATCH = 64;

    // O llama.cpp sobrescreve automaticamente a memória antiga
    // porque estamos mandando batch.pos[j] = i + j (iniciando em zero)
    for (int i = 0; i < n_tokens; i += N_BATCH) {
        int chunk = (i + N_BATCH < n_tokens) ? N_BATCH : (n_tokens - i);
        struct llama_batch batch = llama_batch_init(chunk, 0, 1);
        batch.n_tokens = chunk;
        for (int j = 0; j < chunk; ++j) {
            batch.token[j]     = prompt_tokens[i + j];
            batch.pos[j]       = i + j;
            batch.n_seq_id[j]  = 1;
            batch.seq_id[j][0] = 0;
            batch.logits[j]    = ((i + j) == n_tokens - 1);
        }
        int rc = llama_decode(g_ctx, batch);
        llama_batch_free(batch);
        if (rc != 0) return -5;
    }

    // ... (o resto do código fica igualzinho até o return out_len) ...

    for (int i = 0; i < n_tokens; ++i)
        llama_sampler_accept(g_smpl, prompt_tokens[i]);

    int out_len = 0;
    int pos = n_tokens;
    struct llama_batch step = llama_batch_init(1, 0, 1);

    for (int i = 0; i < max_tokens; ++i) {
        llama_token next = llama_sampler_sample(g_smpl, g_ctx, -1);
        if (llama_vocab_is_eog(g_vocab, next)) break;

        char piece[ORN_MAX_PIECE_BYTES];
        int piece_len = llama_token_to_piece(g_vocab, next, piece, sizeof(piece), 0, true);
        if (piece_len < 0) break;
        if (out_len + piece_len >= output_size - 1) break;

        memcpy(output + out_len, piece, (size_t)piece_len);
        out_len += piece_len;
        output[out_len] = '\0';

        llama_sampler_accept(g_smpl, next);

        step.n_tokens     = 1;
        step.token[0]     = next;
        step.pos[0]       = pos++;
        step.n_seq_id[0]  = 1;
        step.seq_id[0][0] = 0;
        step.logits[0]    = true;
        if (llama_decode(g_ctx, step) != 0) break;
    }
    llama_batch_free(step);

    output[out_len] = '\0';
    return out_len;
}