# -*- coding: utf-8 -*-
"""
orn_llama_deep_profiler.py
==========================
Analisa o que o llama_cpp executa INTERNAMENTE durante os ~94s de _call_engine.

Executa na raiz do ORN:
    python orn_llama_deep_profiler.py

Captura (por prompt):
  - t_load_ms       : tempo de load do modelo
  - t_p_eval_ms     : tempo de prefill (avaliação do prompt inteiro)
  - t_eval_ms       : tempo total de geração (todos os tokens)
  - ms_per_token    : custo médio por token gerado
  - prompt_tokens   : tamanho do prompt em tokens
  - completion_tokens: tokens gerados

  - timings internos via llama_get_timings() se disponível
  - captura do stderr (llama_print_timings) como fallback

Gera:
    llama_deep_report.txt   — relatório legível
    llama_deep_events.jsonl — dados brutos por prompt
"""

from __future__ import annotations

# [DOX-UNUSED] import contextlib
import io
import json
# [DOX-UNUSED] import os
import sys
import re
import time
# [DOX-UNUSED] import threading
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Prompts representativos (curto / médio / longo em tokens)
# ---------------------------------------------------------------------------
PROMPTS = [
    # ~10 tokens — mínimo
    "o que é python",
    # ~15 tokens — explicação
    "explique como funciona o softmax",
    # ~20 tokens — geração simples
    "crie uma função python que inverte uma string",
    # ~25 tokens — geração com algo complexo
    "escreva um buffer circular em python",
]

DEEP_FILE   = Path("llama_deep_events.jsonl")
REPORT_FILE = Path("llama_deep_report.txt")

# ---------------------------------------------------------------------------
# Captura de stderr (llama_print_timings vai para stderr com verbose=True)
# ---------------------------------------------------------------------------

class _StderrCapture:
    """Redireciona stderr para uma string durante o bloco with."""
    def __enter__(self):
        self._old = sys.stderr
        self._buf = io.StringIO()
        sys.stderr = self._buf
        return self

    def __exit__(self, *_):
        sys.stderr = self._old

    @property
    def value(self) -> str:
        return self._buf.getvalue()


def _parse_llama_timings(stderr_text: str) -> dict:
    """
    Extrai as métricas do bloco llama_print_timings que o llama.cpp
    escreve no stderr quando verbose=True.

    Formato típico:
      llama_print_timings:     load time =   79234.56 ms
      llama_print_timings:   prompt eval time =    1823.45 ms /   98 tokens (   18.61 ms per token,    53.75 tokens per second)
      llama_print_timings:          eval time =   89234.56 ms /   64 runs   ( 1394.29 ms per token,     0.72 tokens per second)
      llama_print_timings:         total time =   91124.23 ms /  162 tokens
    """
    result = {}

    patterns = {
        "load_ms":            r"load time\s*=\s*([\d.]+)\s*ms",
        "p_eval_ms":          r"prompt eval time\s*=\s*([\d.]+)\s*ms",
        "p_eval_tokens":      r"prompt eval time\s*=.*?/\s*(\d+)\s*tokens",
        "p_eval_ms_per_tok":  r"prompt eval time\s*=.*?\(\s*([\d.]+)\s*ms per token",
        "p_eval_tok_per_s":   r"prompt eval time\s*=.*?,\s*([\d.]+)\s*tokens per second",
        "eval_ms":            r"\beval time\s*=\s*([\d.]+)\s*ms",
        "eval_runs":          r"\beval time\s*=.*?/\s*(\d+)\s*runs",
        "eval_ms_per_tok":    r"\beval time\s*=.*?\(\s*([\d.]+)\s*ms per token",
        "eval_tok_per_s":     r"\beval time\s*=.*?,\s*([\d.]+)\s*tokens per second",
        "total_ms":           r"total time\s*=\s*([\d.]+)\s*ms",
    }

    for key, pat in patterns.items():
        m = re.search(pat, stderr_text)
        if m:
            result[key] = float(m.group(1))

    return result


# ---------------------------------------------------------------------------
# Tenta usar llama_get_timings() da API C (disponível em llama-cpp-python >= 0.2.x)
# ---------------------------------------------------------------------------

def _get_timings_from_api(llm_obj: Any) -> dict | None:
    """Tenta chamar llm._model.timings (ou llm.timings) se existir."""
    for attr_path in (
        ("_model", "timings"),
        ("timings",),
        ("_ctx", "timings"),
    ):
        try:
            obj = llm_obj
            for attr in attr_path:
                obj = getattr(obj, attr)
            if callable(obj):
                obj = obj()
            # Converte struct C para dict se possível
            if hasattr(obj, "__dict__"):
                return {k: v for k, v in obj.__dict__.items()
                        if not k.startswith("_")}
            if isinstance(obj, dict):
                return obj
        except (AttributeError, TypeError):
            continue
    return None


# ---------------------------------------------------------------------------
# Cálculo de operações matemáticas do transformer por token
# ---------------------------------------------------------------------------

def _calc_ops_per_token(
    n_layers: int,
    d_model: int,
    d_ff: int,
    n_heads: int,
    n_kv_heads: int,
    ctx_len: int,
) -> dict:
    """
    Calcula as operações que se REPETEM a cada token gerado no Qwen 0.5B.
    Baseado na arquitetura transformer com GQA (Grouped Query Attention).

    Qwen2.5-Coder-0.5B:
      n_layers  = 24
      d_model   = 896
      d_ff      = 4864   (intermediate_size)
      n_heads   = 14     (num_attention_heads)
      n_kv_heads= 2      (num_key_value_heads) — GQA
      ctx_len   = 768    (n_ctx configurado no bridge)
    """
    d_head = d_model // n_heads

    ops = {}

    # --- Por camada (×n_layers) ---

    # RMS Norm: 2 por camada (pré-attn + pré-ffn) + 1 final = 2*n_layers + 1
    # Operações por RMSNorm: d_model multiplications + d_model divisions + soma
    ops["rms_norm_per_layer"]  = 3 * d_model   # mul + sqrt + div por elemento
    ops["rms_norm_total"]      = (2 * n_layers + 1) * ops["rms_norm_per_layer"]

    # RoPE (Rotary Positional Embedding) — aplicado a Q e K
    # 2 rotações por token: Q e K, cada uma com d_model / 2 cos/sin + mul
    ops["rope_per_token"]      = 2 * (d_model // 2) * 4   # cos, sin, mul, add
    ops["rope_total"]          = n_layers * ops["rope_per_token"]

    # Projeções lineares de atenção (por camada)
    # Q: d_model → d_model          = d_model²
    # K: d_model → n_kv_heads*d_head (GQA, menor que Q)
    # V: d_model → n_kv_heads*d_head
    # O: d_model → d_model
    d_kv = n_kv_heads * d_head
    ops["attn_proj_Q"]         = d_model * d_model
    ops["attn_proj_K"]         = d_model * d_kv
    ops["attn_proj_V"]         = d_model * d_kv
    ops["attn_proj_O"]         = d_model * d_model
    ops["attn_proj_per_layer"] = (ops["attn_proj_Q"] + ops["attn_proj_K"] +
                                   ops["attn_proj_V"] + ops["attn_proj_O"])

    # Attention scores: Q·K^T
    # Cada head: query (1 × d_head) · K^T (d_head × ctx_len) = ctx_len MACs
    # n_heads cabeças, mas K/V são compartilhados (GQA): cada grupo de heads
    # usa o mesmo K,V
    ops["attn_scores_per_layer"] = n_heads * ctx_len * d_head   # Q·K^T
    ops["attn_softmax_per_layer"]= n_heads * ctx_len            # softmax (exp + div)
    ops["attn_values_per_layer"] = n_heads * ctx_len * d_head   # scores·V

    # FFN (SwiGLU / SiLU gate):
    # gate_proj: d_model → d_ff
    # up_proj  : d_model → d_ff
    # silu(gate) * up
    # down_proj: d_ff → d_model
    ops["ffn_gate"]            = d_model * d_ff
    ops["ffn_up"]              = d_model * d_ff
    ops["ffn_silu"]            = d_ff               # elementwise activation
    ops["ffn_mul"]             = d_ff               # gate * up
    ops["ffn_down"]            = d_ff * d_model
    ops["ffn_per_layer"]       = (ops["ffn_gate"] + ops["ffn_up"] +
                                   ops["ffn_silu"] + ops["ffn_mul"] +
                                   ops["ffn_down"])

    # --- Totais por token gerado ---
    ops["total_linear_macs_per_token"] = n_layers * (
        ops["attn_proj_per_layer"] + ops["ffn_per_layer"]
    )
    ops["total_attn_macs_per_token"] = n_layers * (
        ops["attn_scores_per_layer"] + ops["attn_values_per_layer"]
    )
    ops["total_softmax_per_token"]   = n_layers * ops["attn_softmax_per_layer"]
    ops["total_rms_norm_per_token"]  = ops["rms_norm_total"]
    ops["total_rope_per_token"]      = ops["rope_total"]

    ops["grand_total_ops_per_token"] = (
        ops["total_linear_macs_per_token"] +
        ops["total_attn_macs_per_token"]   +
        ops["total_softmax_per_token"]     +
        ops["total_rms_norm_per_token"]    +
        ops["total_rope_per_token"]
    )

    return ops


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------

def main() -> None:
    print("[LLAMA-DEEP] Importando módulos do ORN...")
    try:
        from engine.core.llm_bridge import SiCDoxBridge, BridgeConfig
    except ImportError as e:
        print(f"[ERRO] {e}\n       Execute na raiz do projeto ORN.")
        sys.exit(1)

    # Carrega bridge em modo verbose para capturar llama_print_timings
    print("[LLAMA-DEEP] Carregando bridge com verbose=True (~80s)...")
    cfg = BridgeConfig()

    # Instancia bridge normalmente e força load
    bridge = SiCDoxBridge(config=cfg)
    bridge._get_bridge = lambda: bridge   # self-referência para uso direto

    # Força o load
    bridge._ensure_loaded()
    llm = bridge._llm
    print(f"[LLAMA-DEEP] Modelo carregado: {cfg.model_path.name}")

    # Arquitetura Qwen2.5-Coder-0.5B (extraída do config.json do modelo)
    ARCH = dict(
        n_layers   = 24,
        d_model    = 896,
        d_ff       = 4864,
        n_heads    = 14,
        n_kv_heads = 2,
        ctx_len    = cfg.n_ctx,
    )
    ops_table = _calc_ops_per_token(**ARCH)

    print("[LLAMA-DEEP] Calculando operações por token (arquitetura Qwen 0.5B)...")

    all_events: list[dict] = []

    for idx, prompt in enumerate(PROMPTS, 1):
        print(f"\n  [{idx}/{len(PROMPTS)}] '{prompt[:50]}...' " if len(prompt) > 50
              else f"\n  [{idx}/{len(PROMPTS)}] '{prompt}'")

        # Limpa contexto entre prompts
        bridge._ctx.clear()
        bridge._system_hint = ""

        # Monta prompt completo como faria o ask()
        bridge._ctx.push("user", prompt)

        # Captura stderr durante a inferência (llama_print_timings)
        t0_wall = time.perf_counter()

        with _StderrCapture() as cap:
            # Força verbose=True só nesta chamada
            original_verbose = getattr(llm, "verbose", False)
            try:
                llm.verbose = True
            except (AttributeError, TypeError):
                pass

            # Constrói tokens
            try:
                token_ids = bridge._build_prompt_tokens()
                prompt_input = token_ids if token_ids else bridge._build_prompt()
            except Exception:
                prompt_input = bridge._build_prompt()

            prompt_token_count = (
                len(token_ids) if (token_ids is not None) else
                len(llm.tokenize(bridge._last_prompt.encode("utf-8")))
            )

            # Chama o motor
            t_llm_start = time.perf_counter()
            try:
                output = llm(
                    prompt_input,
                    max_tokens     = cfg.max_tokens,
                    stop           = ["<|im_end|>", "</s>"],
                    echo           = False,
                    temperature    = cfg.temperature,
                    top_p          = cfg.top_p,
                    top_k          = cfg.top_k,
                    repeat_penalty = cfg.repeat_penalty,
                )
            finally:
                try:
                    llm.verbose = original_verbose
                except (AttributeError, TypeError):
                    pass
            t_llm_end = time.perf_counter()

        wall_ms    = (t_llm_end - t_llm_start) * 1000
        stderr_out = cap.value

        # Dados de uso
        usage             = output.get("usage", {}) or {}
        prompt_tokens     = usage.get("prompt_tokens", prompt_token_count)
        completion_tokens = usage.get("completion_tokens", 0)
        generated_text    = output["choices"][0]["text"]

        # Parseia timings do stderr
        timings_stderr = _parse_llama_timings(stderr_out)

        # Tenta API interna
        timings_api = _get_timings_from_api(llm)

        # Usa os melhores dados disponíveis
        p_eval_ms     = timings_stderr.get("p_eval_ms", 0)
        eval_ms       = timings_stderr.get("eval_ms", 0)
        p_ms_per_tok  = timings_stderr.get("p_eval_ms_per_tok", 0)
        g_ms_per_tok  = timings_stderr.get("eval_ms_per_tok", 0)
        g_tok_per_s   = timings_stderr.get("eval_tok_per_s", 0)
        p_tok_per_s   = timings_stderr.get("p_eval_tok_per_s", 0)

        # Se stderr não capturou (verbose bloqueado), estima a partir de wall time
        if not eval_ms and completion_tokens:
            # Assume prefill ≈ 2% do tempo (típico em CPU para prompt curto)
            p_eval_ms    = wall_ms * 0.02
            eval_ms      = wall_ms * 0.98
            g_ms_per_tok = eval_ms / completion_tokens if completion_tokens else 0
            g_tok_per_s  = 1000 / g_ms_per_tok if g_ms_per_tok else 0

        # Ops que se repetem por token gerado
        ops_per_token = ops_table["grand_total_ops_per_token"]
        total_ops     = ops_per_token * completion_tokens

        ev = {
            "prompt_idx"        : idx,
            "prompt"            : prompt,
            "prompt_tokens"     : prompt_tokens,
            "completion_tokens" : completion_tokens,
            "wall_ms"           : round(wall_ms, 2),
            # timings internos llama.cpp
            "prefill_ms"        : round(p_eval_ms, 2),
            "generate_ms"       : round(eval_ms, 2),
            "prefill_ms_per_tok": round(p_ms_per_tok, 2),
            "generate_ms_per_tok": round(g_ms_per_tok, 2),
            "generate_tok_per_s": round(g_tok_per_s, 3),
            "prefill_tok_per_s" : round(p_tok_per_s, 3),
            # ops matemáticas repetidas
            "ops_per_token"     : ops_per_token,
            "total_ops"         : total_ops,
            # raw
            "stderr_timings"    : timings_stderr,
            "api_timings"       : timings_api,
            "output_chars"      : len(generated_text),
        }
        all_events.append(ev)

        print(f"       prompt_tokens      : {prompt_tokens}")
        print(f"       completion_tokens  : {completion_tokens}")
        print(f"       wall_ms            : {wall_ms:.0f}")
        print(f"       prefill_ms         : {p_eval_ms:.0f}   ({p_tok_per_s:.1f} tok/s)")
        print(f"       generate_ms        : {eval_ms:.0f}   ({g_tok_per_s:.3f} tok/s)")
        print(f"       ms_per_token       : {g_ms_per_tok:.0f}")
        print(f"       ops_per_token      : {ops_per_token:,}")
        print(f"       total_ops_run      : {total_ops:,}")
        if stderr_out:
            print("       [stderr capturado — dados llama.cpp disponíveis]")
        else:
            print("       [stderr não capturado — estimativa pelo wall time]")

    # Grava JSONL
    with DEEP_FILE.open("w", encoding="utf-8") as f:
        for ev in all_events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    # Gera relatório
    report = _build_report(all_events, ops_table, ARCH)
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(f"\n[LLAMA-DEEP] Relatório: {REPORT_FILE}")
    print(f"[LLAMA-DEEP] Dados raw: {DEEP_FILE}")
    print()
    print(report)


# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------

def _build_report(events: list[dict], ops: dict, arch: dict) -> str:
    sep = "=" * 72
    lines = [sep,
             "  LLAMA.CPP — ANÁLISE DE OPERAÇÕES INTERNAS POR TOKEN",
             "  Qwen2.5-Coder-0.5B-Q4_K_M  |  CPU Celeron N2808  |  SSE4.2",
             sep, ""]

    # Arquitetura
    lines += [
        "[ ARQUITETURA DO MODELO ]",
        f"  Camadas (n_layers)        : {arch['n_layers']}",
        f"  Dim modelo (d_model)      : {arch['d_model']}",
        f"  Dim FFN (d_ff)            : {arch['d_ff']}",
        f"  Cabeças de atenção        : {arch['n_heads']}  (GQA — KV heads: {arch['n_kv_heads']})",
        f"  Contexto configurado      : {arch['ctx_len']} tokens",
        "",
    ]

    # Operações por token (o que se REPETE a cada token gerado)
    lines += [
        "[ OPERAÇÕES QUE SE REPETEM A CADA TOKEN GERADO ]",
        f"  {'Operação':<40} {'MACs/Ops':>15}  {'Repete onde'}",
        "  " + "-" * 68,
        f"  {'Projeções lineares Q,K,V,O (atenção)':<40} {ops['total_linear_macs_per_token']//ops['attn_proj_per_layer']//arch['n_layers'] * arch['n_layers'] * ops['attn_proj_per_layer']:>15,}  ×{arch['n_layers']} camadas",
        f"  {'FFN gate + up + down (SwiGLU)':<40} {arch['n_layers'] * ops['ffn_per_layer']:>15,}  ×{arch['n_layers']} camadas",
        f"  {'Attention scores (Q·K^T)':<40} {ops['total_attn_macs_per_token']//2:>15,}  ×{arch['n_layers']} camadas ×ctx",
        f"  {'Weighted sum (scores·V)':<40} {ops['total_attn_macs_per_token']//2:>15,}  ×{arch['n_layers']} camadas ×ctx",
        f"  {'Softmax (exp + div) sobre ctx tokens':<40} {ops['total_softmax_per_token']:>15,}  ×{arch['n_layers']} camadas ×{arch['n_heads']} heads",
        f"  {'RMS Norm':<40} {ops['total_rms_norm_per_token']:>15,}  ×{2*arch['n_layers']+1} (2/camada + final)",
        f"  {'RoPE (cos/sin sobre Q e K)':<40} {ops['total_rope_per_token']:>15,}  ×{arch['n_layers']} camadas",
        f"  {'─'*40}  {'─'*15}",
        f"  {'TOTAL POR TOKEN GERADO':<40} {ops['grand_total_ops_per_token']:>15,}",
        "",
    ]

    # Dados por prompt
    lines += ["[ DADOS REAIS DE INFERÊNCIA POR PROMPT ]", ""]
    for ev in events:
        lines += [
            f"  Prompt #{ev['prompt_idx']}: \"{ev['prompt'][:55]}\"",
            f"    prompt_tokens       : {ev['prompt_tokens']}",
            f"    completion_tokens   : {ev['completion_tokens']}",
            f"    prefill (ms)        : {ev['prefill_ms']}",
            f"    generate (ms)       : {ev['generate_ms']}",
            f"    ms por token        : {ev['generate_ms_per_tok']}",
            f"    tok/s               : {ev['generate_tok_per_s']}",
            f"    ops executadas      : {ev['total_ops']:,}",
        ]
        if ev.get("stderr_timings"):
            lines.append("    fonte               : llama_print_timings (preciso)")
        else:
            lines.append("    fonte               : estimativa wall time (aproximado)")
        lines.append("")

    # Resumo agregado
    if events:
        avg_ms_tok = sum(e["generate_ms_per_tok"] for e in events if e["generate_ms_per_tok"]) / len(events)
        avg_tok_s  = sum(e["generate_tok_per_s"]  for e in events if e["generate_tok_per_s"])  / len(events)
        total_comp = sum(e["completion_tokens"] for e in events)
        total_ops_all = sum(e["total_ops"] for e in events)

        lines += [
            "[ RESUMO AGREGADO ]",
            f"  Tokens gerados total      : {total_comp}",
            f"  ms médio por token        : {avg_ms_tok:.0f}",
            f"  tok/s médio               : {avg_tok_s:.3f}",
            f"  Ops totais executadas      : {total_ops_all:,}",
            f"  Ops por segundo (estimado) : {total_ops_all / (sum(e['generate_ms'] for e in events) / 1000):,.0f}" if any(e["generate_ms"] for e in events) else "",
            "",
        ]

    # Candidatos a pré-tabelamento dentro do modelo
    lines += [
        sep,
        "[ OPERAÇÕES CANDIDATAS A PRÉ-TABELAMENTO DENTRO DO MODELO ]",
        sep,
        "",
        "  #1  Softmax sobre scores de atenção",
        f"       Repetições  : {arch['n_layers']} camadas × {arch['n_heads']} heads × ctx_len = {arch['n_layers']*arch['n_heads']*arch['ctx_len']:,} por token",
        "       Cálculo      : exp(x) para cada score + divisão pela soma",
        "       Oportunidade : exp() é custoso em SSE4.2 sem AVX. Tabela de exp()",
        "                      ou lookup em faixa [-10, 0] com resolução 0.01",
        "                      cobre 99%+ dos scores reais (atenção é pré-softmax ≤ 0).",
        "",
        "  #2  RoPE (cos/sin por posição)",
        f"       Repetições  : {arch['n_layers']} camadas × {arch['d_model']//2} pares = {arch['n_layers']*arch['d_model']//2:,} cos/sin por token",
        "       Cálculo      : cos(pos * freq_i) e sin(pos * freq_i) por dimensão",
        "       Oportunidade : pos cresce +1 a cada token. Pré-computar tabela",
        f"                      RoPE[pos][dim] para pos = 0..{arch['ctx_len']}, dim = 0..{arch['d_model']//2}.",
        "                      Tamanho: {:.1f} KB  (float16)".format(
            arch['ctx_len'] * (arch['d_model']//2) * 2 * 2 / 1024),
        "",
        "  #3  RMS Norm",
        f"       Repetições  : {2*arch['n_layers']+1} vezes × {arch['d_model']} elementos = {(2*arch['n_layers']+1)*arch['d_model']:,} ops por token",
        "       Cálculo      : mean(x²) → rsqrt → mul por elemento",
        "       Oportunidade : Os pesos (weight) de cada RMSNorm são fixos.",
        "                      O rsqrt é recalculado a cada token mas depende do",
        "                      input — não é pré-tabelável. O produto weight×scale",
        "                      pode ser fundido em uma operação fused kernel.",
        "",
        "  #4  FFN SiLU activation",
        f"       Repetições  : {arch['n_layers']} camadas × {arch['d_ff']} elementos = {arch['n_layers']*arch['d_ff']:,} por token",
        "       Cálculo      : silu(x) = x * sigmoid(x) = x / (1 + exp(-x))",
        "       Oportunidade : exp(-x) concentrado em [-6, 6]. Tabela de 1200",
        "                      entradas (resolução 0.01) cobre 99% dos casos.",
        "                      Tamanho: ~10 KB. Ganho real em SSE4.2 sem AVX.",
        "",
        "  #5  Q·K^T (scores de atenção) — escala com ctx_len",
        f"       Repetições  : {arch['n_layers']} × {arch['n_heads']} heads × {arch['ctx_len']} ctx = {arch['n_layers']*arch['n_heads']*arch['ctx_len']:,} MACs por token",
        "       Cálculo      : dot product entre q atual e cada k no KV-cache",
        "       Oportunidade : K já está no KV-cache. Apenas o novo q é diferente.",
        "                      Não é pré-tabelável diretamente, mas com n_ctx=384",
        "                      (metade do atual) o custo cai à metade.",
        "",
        sep,
        "  Dados brutos: llama_deep_events.jsonl",
        sep,
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()