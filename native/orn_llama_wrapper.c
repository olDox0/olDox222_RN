#include "orn_llama_wrapper.h"
#include "orn_optimizer.h"
#include "llama.h"

#include <string.h>
#include <stdlib.h>
#include <time.h>

#define ORN_MAX_PROMPT_TOKENS 8192
#define ORN_MAX_PIECE_BYTES  512

static struct llama_model    * g_model   = NULL;
static struct llama_context  * g_ctx     = NULL;
static struct llama_sampler  * g_smpl    = NULL;
static const struct llama_vocab * g_vocab = NULL;
static int g_ready = 0;

static llama_token g_history_tokens[ORN_MAX_PROMPT_TOKENS];
static int g_history_len = 0;

static int g_saved_n_ctx = 256;
static int g_saved_n_threads = 2;

static struct llama_batch g_batch;
static int g_batch_size = 0;
static int g_batch_ready = 0;

static void orn_silent_log_callback(enum ggml_log_level level, const char * text, void * user_data)
{
    (void)level; (void)text; (void)user_data;
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

    if (g_batch_ready) {
        llama_batch_free(g_batch);
        g_batch_ready = 0;
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

    g_saved_n_ctx = n_ctx;
    g_saved_n_threads = n_threads;

    struct llama_model_params mparams = llama_model_default_params();
    mparams.n_gpu_layers = 0;

    g_model = llama_model_load_from_file(model_path, mparams);
    if (!g_model) { orn_free(); return -1; }

    g_vocab = llama_model_get_vocab(g_model);
    if (!g_vocab) { orn_free(); return -2; }

    struct llama_context_params cparams = llama_context_default_params();
    cparams.n_ctx = (n_ctx > 0) ? n_ctx : 1024;
    cparams.n_batch = 64;
    cparams.n_ubatch = 64;
    cparams.n_threads = (n_threads > 0) ? n_threads : 2;
    cparams.n_threads_batch = cparams.n_threads;
    cparams.flash_attn_type = true;

    g_ctx = llama_init_from_model(g_model, cparams);
    if (!g_ctx) { orn_free(); return -3; }

    struct llama_sampler_chain_params sparams = llama_sampler_chain_default_params();
    g_smpl = llama_sampler_chain_init(sparams);
    if (!g_smpl) { orn_free(); return -4; }

    g_batch_size = (g_saved_n_threads <= 2) ? 32 : 64;

    g_batch = llama_batch_init(g_batch_size, 0, 1);

    if (!g_batch.token || !g_batch.pos || !g_batch.n_seq_id || !g_batch.seq_id || !g_batch.logits) {
        orn_free();
        return -5;
    }

    g_batch_ready = 1;

    llama_sampler_chain_add(g_smpl, llama_sampler_init_penalties(64, 1.15f, 0.0f, 0.0f));
    llama_sampler_chain_add(g_smpl, llama_sampler_init_min_p(0.05f, 1));
    llama_sampler_chain_add(g_smpl, llama_sampler_init_temp(0.40f));
    llama_sampler_chain_add(g_smpl, llama_sampler_init_dist((uint32_t)time(NULL)));

    g_ready = 1;
    return 0;
}

int orn_infer(const char* prompt, int max_tokens, char* output, int output_size)
{
    if (!g_ready || !g_model || !g_smpl || !g_vocab) return -1;
    if (!prompt || !output || output_size <= 1 || max_tokens <= 0) return -2;
    if (!g_batch_ready) return -7;

    output[0] = '\0';

    llama_sampler_reset(g_smpl);

    llama_token prompt_tokens[ORN_MAX_PROMPT_TOKENS];

    int n_tokens = llama_tokenize(
        g_vocab,
        prompt,
        (int)strlen(prompt),
        prompt_tokens,
        ORN_MAX_PROMPT_TOKENS,
        true,
        true
    );

    if (n_tokens <= 0) return -3;

    orn_reuse_info reuse = orn_analyze_reuse(
        g_history_tokens,
        g_history_len,
        prompt_tokens,
        n_tokens
    );

    int n_past = reuse.reused_tokens;

    struct llama_batch *batch = &g_batch;

    for (int i = n_past; i < n_tokens; i += g_batch_size) {
        int chunk = (i + g_batch_size < n_tokens) ? g_batch_size : (n_tokens - i);

        batch->n_tokens = chunk;

        for (int j = 0; j < chunk; ++j) {
            batch->token[j] = prompt_tokens[i + j];
            batch->pos[j] = i + j;
            batch->n_seq_id[j] = 1;
            batch->seq_id[j][0] = 0;
            batch->logits[j] = 0;
        }

        batch->logits[chunk - 1] = 1;

        if (llama_decode(g_ctx, *batch) != 0) {
            return -5;
        }
    }

    int out_pos = 0;

    for (int i = 0; i < max_tokens; ++i) {
        llama_token new_token = llama_sampler_sample(g_smpl, g_ctx, -1);

        if (new_token == llama_vocab_eos(g_vocab)) break;

        char piece[ORN_MAX_PIECE_BYTES];

        int n = llama_token_to_piece(
            g_vocab,
            new_token,
            piece,
            sizeof(piece),
            0,
            true
        );

        if (n > 0 && out_pos + n < output_size - 1) {
            memcpy(output + out_pos, piece, n);
            out_pos += n;
        }

        batch->n_tokens = 1;
        batch->token[0] = new_token;
        batch->pos[0] = n_tokens + i;
        batch->n_seq_id[0] = 1;
        batch->seq_id[0][0] = 0;
        batch->logits[0] = 1;

        if (llama_decode(g_ctx, *batch) != 0) {
            return -6;
        }
    }

int orn_infer_stream(const char* prompt, int max_tokens,
                     orn_token_cb callback, void* user_data)
{
    if (!g_ready || !g_model || !g_smpl || !g_vocab) return -1;
    if (!prompt || !callback || max_tokens <= 0)      return -2;
    if (!g_batch_ready)                                return -7;

    llama_sampler_reset(g_smpl);

    llama_token prompt_tokens[ORN_MAX_PROMPT_TOKENS];
    int n_tokens = llama_tokenize(
        g_vocab, prompt, (int)strlen(prompt),
        prompt_tokens, ORN_MAX_PROMPT_TOKENS, true, true
    );
    if (n_tokens <= 0) return -3;

    orn_reuse_info reuse = orn_analyze_reuse(
        g_history_tokens, g_history_len, prompt_tokens, n_tokens
    );
    int n_past = reuse.reused_tokens;

    /* --- fase de prefill (igual ao orn_infer) --- */
    struct llama_batch *batch = &g_batch;
    for (int i = n_past; i < n_tokens; i += g_batch_size) {
        int chunk = (i + g_batch_size < n_tokens) ? g_batch_size : (n_tokens - i);
        batch->n_tokens = chunk;
        for (int j = 0; j < chunk; ++j) {
            batch->token[j]     = prompt_tokens[i + j];
            batch->pos[j]       = i + j;
            batch->n_seq_id[j]  = 1;
            batch->seq_id[j][0] = 0;
            batch->logits[j]    = 0;
        }
        batch->logits[chunk - 1] = 1;
        if (llama_decode(g_ctx, *batch) != 0) return -5;
    }

    /* --- fase de geração token a token --- */
    char piece[ORN_MAX_PIECE_BYTES];
    int  n_generated = 0;

    for (int i = 0; i < max_tokens; ++i) {
        llama_token tok = llama_sampler_sample(g_smpl, g_ctx, -1);
        if (tok == llama_vocab_eos(g_vocab)) break;

        llama_sampler_accept(g_smpl, tok);

        int n = llama_token_to_piece(g_vocab, tok, piece, sizeof(piece) - 1, 0, true);
        if (n > 0) {
            piece[n] = '\0';
            if (callback(piece, n, user_data) != 0) break; /* interrompido */
        }

        /* decode do token gerado para obter logits do próximo */
        batch->n_tokens      = 1;
        batch->token[0]      = tok;
        batch->pos[0]        = n_tokens + i;
        batch->n_seq_id[0]   = 1;
        batch->seq_id[0][0]  = 0;
        batch->logits[0]     = 1;
        if (llama_decode(g_ctx, *batch) != 0) return -5;

        n_generated++;
    }

    /* atualiza histórico */
    int total = n_tokens + n_generated;
    if (total > ORN_MAX_PROMPT_TOKENS) total = ORN_MAX_PROMPT_TOKENS;
    memcpy(g_history_tokens, prompt_tokens,
           (n_tokens < ORN_MAX_PROMPT_TOKENS ? n_tokens : ORN_MAX_PROMPT_TOKENS)
           * sizeof(llama_token));
    g_history_len = total;

    return 0;
}

    output[out_pos] = '\0';

    if (n_tokens <= ORN_MAX_PROMPT_TOKENS) {
        memcpy(g_history_tokens, prompt_tokens, n_tokens * sizeof(llama_token));
        g_history_len = n_tokens;
    }

    return out_pos;
}