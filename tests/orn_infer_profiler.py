# -*- coding: utf-8 -*-
"""
ORN — Inference Profiler  (coleta dados reais de runtime)
=========================================================
Execute na raiz do projeto ORN:

    python orn_infer_profiler.py

O script:
  1. Faz monkey-patch nas funções-chave do bridge e executive.
  2. Roda N prompts de teste cobrindo os intents disponíveis.
  3. Grava cada evento em  profiler_events.jsonl
  4. Gera um relatório  profiler_report.txt  com ranking de repetições.

Não altera nenhum arquivo do projeto — só lê e instrumenta em memória.
"""

from __future__ import annotations

import functools
import json
# [DOX-UNUSED] import re
import time
import sys
# [DOX-UNUSED] import os
from collections import defaultdict
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

EVENTS_FILE  = Path("profiler_events.jsonl")
REPORT_FILE  = Path("profiler_report.txt")

# Prompts que cobrem os padrões de uso real do sistema
TEST_PROMPTS = [
    # Geração de código simples
    "crie uma função python que inverte uma string",
    "escreva um buffer circular em python",
    "implemente um stack em python",
    # Explicação
    "explique como funciona o softmax",
    "o que é recursão em python",
    "como funciona um dicionário em python",
    # Código C/C++
    "crie uma função em C que soma dois inteiros",
    "escreva um struct em C++ para representar um ponto 2D",
    # Batch script
    "crie um batch script que lista arquivos em um diretório",
    # Repetição intencional (para detectar memo hits)
    "crie uma função python que inverte uma string",   # igual ao 1°
    "explique como funciona o softmax",                 # igual ao 4°
    # Texto puro
    "quais são as diferenças entre python e c++",
    "liste as principais estruturas de dados",
]

# ---------------------------------------------------------------------------
# Store de eventos em memória
# ---------------------------------------------------------------------------

_events: list[dict] = []
_call_counter: dict[str, int] = defaultdict(int)
_prompt_index = 0   # incrementado a cada process_goal


def _emit(name: str, data: dict) -> None:
    ev = {"t": round(time.monotonic(), 6), "prompt_idx": _prompt_index,
          "fn": name, **data}
    _events.append(ev)
    _call_counter[name] += 1


# ---------------------------------------------------------------------------
# Monkey-patchers genéricos
# ---------------------------------------------------------------------------

def _wrap_count(obj: Any, method: str, label: str | None = None) -> None:
    """Wraps obj.method para contar chamadas e medir tempo."""
    label = label or method
    original = getattr(obj, method)

    @functools.wraps(original)
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        result = original(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _emit(label, {"elapsed_ms": round(elapsed_ms, 4)})
        return result

    setattr(obj, method, wrapper)


def _wrap_count_fn(module: Any, fn_name: str, label: str | None = None) -> None:
    """Wraps uma função livre num módulo."""
    label = label or fn_name
    original = getattr(module, fn_name)

    @functools.wraps(original)
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        result = original(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _emit(label, {"elapsed_ms": round(elapsed_ms, 4)})
        return result

    setattr(module, fn_name, wrapper)


# ---------------------------------------------------------------------------
# Patches específicos: executive
# ---------------------------------------------------------------------------

def _patch_executive(executive_module: Any) -> None:
    """Instrumenta as funções do executive.py."""
    from engine.core.blackboard import DoxoBoard  # noqa

    # _decompose_query — conta cada re.search interno
    orig_decompose = executive_module._decompose_query

    def patched_decompose(board, prompt, context):
        t0 = time.perf_counter()
        p = prompt.lower()
        # Conta todos os padrões que seriam testados
        patterns_tested = 0
        for pat in executive_module._LANG_MAP:
            patterns_tested += 1
        for kw in ("_KW_EXPLAIN", "_KW_GENERATE", "_KW_FIX", "_KW_LIST", "_KW_CODE_CONTEXT"):
            if hasattr(executive_module, kw):
                patterns_tested += 1
        result = orig_decompose(board, prompt, context)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _emit("_decompose_query", {
            "elapsed_ms": round(elapsed_ms, 4),
            "regex_patterns_tested": patterns_tested,
            "prompt_len": len(prompt),
        })
        return result

    executive_module._decompose_query = patched_decompose

    # _adaptive_max_tokens
    orig_adaptive = executive_module._adaptive_max_tokens

    def patched_adaptive(prompt: str) -> int:
        t0 = time.perf_counter()
        result = orig_adaptive(prompt)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _emit("_adaptive_max_tokens", {
            "elapsed_ms": round(elapsed_ms, 4),
            "max_tokens_result": result,
            "prompt_len": len(prompt),
        })
        return result

    executive_module._adaptive_max_tokens = patched_adaptive

    # _looks_degenerate_think_output
    orig_degen = executive_module._looks_degenerate_think_output

    def patched_degen(prompt, output):
        t0 = time.perf_counter()
        result = orig_degen(prompt, output)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _emit("_looks_degenerate", {
            "elapsed_ms": round(elapsed_ms, 4),
            "is_degenerate": result,
        })
        return result

    executive_module._looks_degenerate_think_output = patched_degen


# ---------------------------------------------------------------------------
# Patches específicos: llm_bridge
# ---------------------------------------------------------------------------

def _patch_bridge(bridge_instance: Any) -> None:
    """Instrumenta os métodos da instância SiCDoxBridge."""

    # ask — captura chamada completa
    orig_ask = bridge_instance.ask.__func__  # função original

    def patched_ask(self, prompt, max_tokens=None, token_hint=None, system_hint=None):
        t0 = time.perf_counter()
        _emit("ask:start", {
            "prompt_len": len(prompt),
            "max_tokens_in": max_tokens,
            "token_hint": token_hint,
            "has_system_hint": bool(system_hint),
        })
        result = orig_ask(self, prompt, max_tokens=max_tokens,
                          token_hint=token_hint, system_hint=system_hint)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _emit("ask:done", {
            "elapsed_ms": round(elapsed_ms, 4),
            "output_len": len(result) if result else 0,
        })
        return result

    bridge_instance.ask = patched_ask.__get__(bridge_instance)

    # _memo_get
    orig_memo_get = bridge_instance._memo_get.__func__

    def patched_memo_get(self, prompt):
        t0 = time.perf_counter()
        result = orig_memo_get(self, prompt)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _emit("_memo_get", {
            "elapsed_ms": round(elapsed_ms, 4),
            "hit": result is not None,
            "memo_size": len(self._memo),
        })
        return result

    bridge_instance._memo_get = patched_memo_get.__get__(bridge_instance)

    # _memo_put
    orig_memo_put = bridge_instance._memo_put.__func__

    def patched_memo_put(self, prompt, answer):
        t0 = time.perf_counter()
        orig_memo_put(self, prompt, answer)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _emit("_memo_put", {
            "elapsed_ms": round(elapsed_ms, 4),
            "memo_size": len(self._memo),
        })

    bridge_instance._memo_put = patched_memo_put.__get__(bridge_instance)

    # _build_prompt
    orig_build = bridge_instance._build_prompt.__func__

    def patched_build(self):
        t0 = time.perf_counter()
        result = orig_build(self)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _emit("_build_prompt", {
            "elapsed_ms": round(elapsed_ms, 4),
            "prompt_chars": len(result),
            "ctx_turns": len(self._ctx._turns),
        })
        return result

    bridge_instance._build_prompt = patched_build.__get__(bridge_instance)

    # _build_prompt_tokens
    orig_tokens = bridge_instance._build_prompt_tokens.__func__

    def patched_tokens(self):
        t0 = time.perf_counter()
        result = orig_tokens(self)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _emit("_build_prompt_tokens", {
            "elapsed_ms": round(elapsed_ms, 4),
            "token_count": len(result) if result else 0,
            "ctx_turns": len(self._ctx._turns),
            "fallback": result is None,
        })
        return result

    bridge_instance._build_prompt_tokens = patched_tokens.__get__(bridge_instance)

    # _call_engine
    orig_engine = bridge_instance._call_engine.__func__

    def patched_engine(self, prompt, max_tokens):
        t0 = time.perf_counter()
        result = orig_engine(self, prompt, max_tokens)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        usage = result.get("usage", {})
        _emit("_call_engine", {
            "elapsed_ms": round(elapsed_ms, 4),
            "max_tokens": max_tokens,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "llm_call_ms": result.get("llm_call_ms"),
        })
        return result

    bridge_instance._call_engine = patched_engine.__get__(bridge_instance)


# ---------------------------------------------------------------------------
# Patch ContextWindow para contar push/evicções
# ---------------------------------------------------------------------------

def _patch_context_window(ctx: Any) -> None:
    """Instrumenta o ContextWindow da instância."""

    orig_push = ctx.push.__func__

    def patched_push(self, role, content):
        t0 = time.perf_counter()
        count_before = self._count
        turns_before = len(self._turns)
        orig_push(self, role, content)
        turns_after = len(self._turns)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        evictions = max(0, turns_before + 1 - turns_after)  # +1 pelo append
        bit_shift_ops = 1 + evictions  # push + evicções
        _emit("ctx_push", {
            "elapsed_ms": round(elapsed_ms, 4),
            "role": role,
            "content_len": len(content),
            "token_est_added": len(content) >> 2,
            "evictions": evictions,
            "bit_shift_ops": bit_shift_ops,
            "turns_after": turns_after,
            "count_before": count_before,
            "count_after": self._count,
        })

    ctx.push = patched_push.__get__(ctx)


# ---------------------------------------------------------------------------
# Patch pitstop para detectar o bug de dupla chamada
# ---------------------------------------------------------------------------

def _patch_pitstop() -> None:
    try:
        import engine.core.prompt_utils as pu
        orig_pitstop = pu.pitstop
        _pitstop_call_times: list[float] = []

        @functools.wraps(orig_pitstop)
        def patched_pitstop(prompt, max_tokens, **kwargs):
            now = time.monotonic()
            t0 = time.perf_counter()
            result = orig_pitstop(prompt, max_tokens, **kwargs)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            # Detecta chamada dupla (< 50ms após a anterior, mesmo prompt_idx)
            is_duplicate = False
            if _pitstop_call_times and (now - _pitstop_call_times[-1]) < 0.05:
                is_duplicate = True

            _pitstop_call_times.append(now)
            _emit("pitstop", {
                "elapsed_ms": round(elapsed_ms, 4),
                "prompt_len_in": len(prompt),
                "max_tokens_in": max_tokens,
                "max_tokens_out": result[1],
                "is_duplicate_call": is_duplicate,
            })
            return result

        pu.pitstop = patched_pitstop
        print("[PROFILER] pitstop() instrumentado.")
    except Exception as e:
        print(f"[PROFILER] pitstop não acessível: {e}")


# ---------------------------------------------------------------------------
# Geração do relatório
# ---------------------------------------------------------------------------

def _generate_report() -> str:
    if not _events:
        return "Nenhum evento coletado."

    # Agrupa por função
    by_fn: dict[str, list[dict]] = defaultdict(list)
    for ev in _events:
        by_fn[ev["fn"]].append(ev)

    total_prompts = _prompt_index
    lines: list[str] = []
    sep = "=" * 72

    lines.append(sep)
    lines.append("  ORN INFERENCE PROFILER — RELATÓRIO DE REPETIÇÕES")
    lines.append(sep)
    lines.append(f"  Prompts processados : {total_prompts}")
    lines.append(f"  Total de eventos    : {len(_events)}")
    lines.append("")

    # --- Tabela de chamadas por função ---
    lines.append("[ FREQUÊNCIA DE CHAMADAS ]")
    lines.append(f"  {'Função':<35} {'Total':>7} {'Por prompt':>12} {'ms médio':>10} {'ms total':>10}")
    lines.append("  " + "-" * 74)

    ranked = sorted(by_fn.items(), key=lambda kv: len(kv[1]), reverse=True)

    for fn, evs in ranked:
        n = len(evs)
        per_prompt = n / total_prompts if total_prompts else 0
        times = [e.get("elapsed_ms", 0) for e in evs if "elapsed_ms" in e]
        avg_ms = (sum(times) / len(times)) if times else 0
        total_ms = sum(times)
        lines.append(f"  {fn:<35} {n:>7} {per_prompt:>12.2f} {avg_ms:>10.3f} {total_ms:>10.2f}")

    # --- Bit-shift operations (len >> 2) ---
    lines.append("")
    lines.append("[ OPERAÇÕES len >> 2  (estimativa de tokens) ]")
    ctx_evs = by_fn.get("ctx_push", [])
    total_bitshift = sum(e.get("bit_shift_ops", 1) for e in ctx_evs)
    total_evictions = sum(e.get("evictions", 0) for e in ctx_evs)
    lines.append(f"  Total de len >> 2 executados : {total_bitshift}")
    lines.append(f"  Causados por evicções        : {total_evictions}")
    lines.append(f"  Por prompt (média)           : {total_bitshift/total_prompts:.1f}" if total_prompts else "  -")

    # --- Memo hits ---
    lines.append("")
    lines.append("[ MEMO CACHE (pitstop de repetição) ]")
    memo_evs = by_fn.get("_memo_get", [])
    hits = [e for e in memo_evs if e.get("hit")]
    misses = [e for e in memo_evs if not e.get("hit")]
    lines.append(f"  Lookups  : {len(memo_evs)}")
    lines.append(f"  Hits     : {len(hits)}  ({100*len(hits)/len(memo_evs):.1f}%)" if memo_evs else "  Hits: 0")
    lines.append(f"  Misses   : {len(misses)}")

    # --- Pitstop duplicado ---
    lines.append("")
    lines.append("[ BUG: pitstop() DUPLO ]")
    pit_evs = by_fn.get("pitstop", [])
    dups = [e for e in pit_evs if e.get("is_duplicate_call")]
    lines.append(f"  Total de chamadas pitstop : {len(pit_evs)}")
    lines.append(f"  Chamadas duplicadas       : {len(dups)}")
    lines.append(f"  (esperado: 1 dupla por prompt = {total_prompts} duplas)")

    # --- Tokenize por turn ---
    lines.append("")
    lines.append("[ TOKENIZE POR TURN (_build_prompt_tokens) ]")
    tok_evs = by_fn.get("_build_prompt_tokens", [])
    if tok_evs:
        total_toks = sum(e.get("token_count", 0) for e in tok_evs)
        avg_turns = sum(e.get("ctx_turns", 0) for e in tok_evs) / len(tok_evs)
        lines.append(f"  Chamadas              : {len(tok_evs)}")
        lines.append(f"  Tokens gerados total  : {total_toks}")
        lines.append(f"  Turns médios/chamada  : {avg_turns:.1f}")
        lines.append(f"  Tokenizações por call : ~{avg_turns:.0f} (uma por turn)")
    else:
        lines.append("  Nenhuma chamada registrada (fallback para _build_prompt string).")

    # --- Call engine (o custo real da inferência) ---
    lines.append("")
    lines.append("[ _call_engine — CUSTO DE INFERÊNCIA ]")
    eng_evs = by_fn.get("_call_engine", [])
    if eng_evs:
        total_prompt_tok = sum(e.get("prompt_tokens", 0) for e in eng_evs)
        total_comp_tok   = sum(e.get("completion_tokens", 0) for e in eng_evs)
        total_infer_ms   = sum(e.get("elapsed_ms", 0) for e in eng_evs)
        avg_ms           = total_infer_ms / len(eng_evs)
        lines.append(f"  Chamadas                : {len(eng_evs)}")
        lines.append(f"  Prompt tokens total     : {total_prompt_tok}")
        lines.append(f"  Completion tokens total : {total_comp_tok}")
        lines.append(f"  Tempo total inferência  : {total_infer_ms:.0f} ms")
        lines.append(f"  Tempo médio por call    : {avg_ms:.0f} ms")
    else:
        lines.append("  Nenhuma chamada (memo hit em todos os prompts?).")

    # --- Candidatos a pré-tabelamento ---
    lines.append("")
    lines.append(sep)
    lines.append("[ CANDIDATOS A PRÉ-TABELAMENTO ]")
    lines.append(sep)
    lines.append("")

    candidates = []

    # Regex
    regex_total = len(by_fn.get("_decompose_query", [])) + len(by_fn.get("_adaptive_max_tokens", []))
    if regex_total:
        candidates.append((
            "re.search() sobre prompt.lower()",
            regex_total * 9,  # 9 patterns por call pair
            "Cache: dict { frozenset(prompt_words): (lang, task_type, max_tokens) }",
            "Alta — mesmo prompt roda 9 regex em 2 funções separadas",
        ))

    # build_synthesis
    synth_n = len(by_fn.get("_build_prompt", [])) + len(by_fn.get("_build_prompt_tokens", []))
    if synth_n:
        candidates.append((
            "_build_prompt / _build_prompt_tokens por turn",
            synth_n,
            "Cache: token_ids por (role, content_hash) — reutilizar turns imutáveis",
            "Alta — escala com tamanho do histórico",
        ))

    # bit-shift
    if total_bitshift:
        candidates.append((
            "len(content) >> 2 (estimativa tokens)",
            total_bitshift,
            "Cache: dict { id(turn): est } — invalidar só no push/pop",
            "Média — operação barata mas repete em cada evicção",
        ))

    # pitstop duplo
    if dups:
        candidates.append((
            "pitstop() chamado 2x (bug)",
            len(dups),
            "Fix: remover segunda chamada nas linhas ~410-415 de llm_bridge.py",
            "Alta — processa prompt duas vezes desnecessariamente",
        ))

    # memo hits
    if hits:
        candidates.append((
            "_memo_get resultados (já pré-tabelados!)",
            len(hits),
            "Aumentar repetition_memo_size (atual=128) para cobrir mais prompts",
            "Já funcionando — expandir tabela",
        ))

    for i, (name, count, action, priority) in enumerate(candidates, 1):
        lines.append(f"  #{i}  {name}")
        lines.append(f"       Ocorrências   : {count}")
        lines.append(f"       Ação          : {action}")
        lines.append(f"       Prioridade    : {priority}")
        lines.append("")

    lines.append(sep)
    lines.append(f"  Eventos gravados em : {EVENTS_FILE}")
    lines.append(f"  (use os .jsonl para análise fina por prompt_idx)")
    lines.append(sep)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------

def main() -> None:
    global _prompt_index

    print("[PROFILER] Iniciando instrumentação do ORN...")

    # Importa módulos do projeto (deve estar na raiz do ORN)
    try:
        import engine.core.executive as executive_module
        from engine.core.executive import SiCDoxExecutive
    except ImportError as e:
        print(f"[ERRO] Não foi possível importar o executive: {e}")
        print("       Execute este script na raiz do projeto ORN.")
        sys.exit(1)

    # Patcha as funções livres do executive
    _patch_executive(executive_module)
    _patch_pitstop()

    # Cria instância e força carregamento do bridge
    print("[PROFILER] Criando Executive e carregando bridge (pode levar ~80s)...")
    exec_instance = SiCDoxExecutive(persistent=True)

    # Força o load do bridge acessando-o
    bridge = exec_instance._get_bridge()
    print("[PROFILER] Bridge carregado. Instrumentando instâncias...")

    # Patcha instâncias
    _patch_bridge(bridge)
    _patch_context_window(bridge._ctx)

    print(f"[PROFILER] Rodando {len(TEST_PROMPTS)} prompts de teste...\n")

    results_summary: list[dict] = []

    for idx, prompt in enumerate(TEST_PROMPTS):
        _prompt_index = idx + 1
        print(f"  [{idx+1:02d}/{len(TEST_PROMPTS)}] {prompt[:60]}...")

        t0 = time.monotonic()
        result = exec_instance.process_goal("think", prompt)
        elapsed = time.monotonic() - t0

        status = "OK" if result.success else f"FAIL:{result.errors}"
        results_summary.append({
            "idx": idx + 1,
            "prompt": prompt,
            "status": status,
            "elapsed_s": round(elapsed, 2),
            "output_len": len(result.output),
        })
        print(f"         → {status}  ({elapsed:.1f}s)  output: {len(result.output)} chars")

        # Limpa contexto entre prompts (simula uso real da CLI)
        try:
            bridge._ctx.clear()
        except Exception:
            pass

    # Grava eventos brutos
    with EVENTS_FILE.open("w", encoding="utf-8") as f:
        for ev in _events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print(f"\n[PROFILER] {len(_events)} eventos gravados em {EVENTS_FILE}")

    # Gera relatório
    report = _generate_report()
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(f"[PROFILER] Relatório gravado em {REPORT_FILE}")
    print()
    print(report)


if __name__ == "__main__":
    main()