# -*- coding: utf-8 -*-
"""
orn_analyze_events.py — Analisa profiler_events.jsonl depois de rodar o profiler.

Uso:
    python orn_analyze_events.py                  # lê profiler_events.jsonl
    python orn_analyze_events.py outro_arquivo.jsonl

Gera:
    profiler_pretable.json   — tabela de candidatos a pré-computação, por frequência
    profiler_by_prompt.txt   — detalhe por prompt (quais cálculos cada um disparou)
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------

EVENTS_FILE    = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("profiler_events.jsonl")
PRETABLE_FILE  = Path("profiler_pretable.json")
BY_PROMPT_FILE = Path("profiler_by_prompt.txt")

# ---------------------------------------------------------------------------

def load_events(path: Path) -> list[dict]:
    events = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def analyze(events: list[dict]) -> None:
    total_prompts = max((e["prompt_idx"] for e in events), default=0)

    # Agrupa por função
    by_fn: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        by_fn[ev["fn"]].append(ev)

    # Agrupa por prompt_idx
    by_prompt: dict[int, list[dict]] = defaultdict(list)
    for ev in events:
        by_prompt[ev["prompt_idx"]].append(ev)

    # -----------------------------------------------------------------------
    # 1. Tabela de pré-computação
    # -----------------------------------------------------------------------

    pretable: list[dict] = []

    # --- regex ---
    n_decompose = len(by_fn.get("_decompose_query", []))
    n_adaptive  = len(by_fn.get("_adaptive_max_tokens", []))
    regex_ops   = n_decompose * 6 + n_adaptive * 3  # padrões por função
    if regex_ops:
        pretable.append({
            "rank": 0,
            "name": "re.search() múltiplos sobre prompt.lower()",
            "total_operations": regex_ops,
            "calls_per_prompt": round(regex_ops / total_prompts, 2),
            "avg_ms": _avg_ms(by_fn.get("_decompose_query", []) +
                              by_fn.get("_adaptive_max_tokens", [])),
            "source_functions": ["_decompose_query (6 patterns)", "_adaptive_max_tokens (3 patterns)"],
            "cache_strategy": "dict { hash(prompt.lower()): (lang, task_type, max_tokens) }",
            "savings": "Elimina 8 de 9 varreduras regex por call",
        })

    # --- bit-shift / estimativa tokens ---
    ctx_evs     = by_fn.get("ctx_push", [])
    total_bs    = sum(e.get("bit_shift_ops", 1) for e in ctx_evs)
    total_evict = sum(e.get("evictions", 0) for e in ctx_evs)
    if total_bs:
        pretable.append({
            "rank": 0,
            "name": "len(content) >> 2  (estimativa de tokens)",
            "total_operations": total_bs,
            "calls_per_prompt": round(total_bs / total_prompts, 2),
            "avg_ms": _avg_ms(ctx_evs),
            "source_functions": ["ContextWindow.push()", "ContextWindow._compact_old_turns()"],
            "breakdown": {
                "push_ops": len(ctx_evs),
                "eviction_ops": total_evict,
                "compact_recalcs": sum(1 for e in ctx_evs if e.get("evictions", 0) > 0),
            },
            "cache_strategy": "Cache { turn_id: est } — invalida só no push; sum incremental",
            "savings": f"Elimina {total_evict} recálculos desnecessários em evicções",
        })

    # --- tokenize por turn ---
    tok_evs = by_fn.get("_build_prompt_tokens", [])
    if tok_evs:
        total_token_calls = sum(e.get("ctx_turns", 0) for e in tok_evs)
        pretable.append({
            "rank": 0,
            "name": "llm.tokenize() por turn (reconstrói inteiro a cada ask)",
            "total_operations": total_token_calls,
            "calls_per_prompt": round(total_token_calls / total_prompts, 2),
            "avg_ms": _avg_ms(tok_evs),
            "source_functions": ["SiCDoxBridge._build_prompt_tokens()"],
            "breakdown": {
                "prompt_token_builds": len(tok_evs),
                "avg_turns_per_build": round(total_token_calls / len(tok_evs), 1) if tok_evs else 0,
            },
            "cache_strategy": "Token cache incremental: { sha256(role+content): token_ids } — appenda só turns novos",
            "savings": "Elimina re-tokenização de turns imutáveis do histórico",
        })

    # --- pitstop duplo ---
    pit_evs = by_fn.get("pitstop", [])
    dups    = [e for e in pit_evs if e.get("is_duplicate_call")]
    if dups:
        pretable.append({
            "rank": 0,
            "name": "pitstop() chamado 2× por call (BUG)",
            "total_operations": len(dups),
            "calls_per_prompt": round(len(dups) / total_prompts, 2),
            "avg_ms": _avg_ms(dups),
            "source_functions": ["SiCDoxBridge.ask() linhas ~410-415"],
            "cache_strategy": "N/A — é um bug. Remover segunda chamada.",
            "savings": "Elimina 100% de um pitstop() por call",
        })

    # --- build_synthesis duplicado ---
    synth_evs = by_fn.get("build_synthesis_block", [])
    if synth_evs:
        pretable.append({
            "rank": 0,
            "name": "build_synthesis_block() chamado 2× em _run_think",
            "total_operations": len(synth_evs),
            "calls_per_prompt": round(len(synth_evs) / total_prompts, 2),
            "avg_ms": _avg_ms(synth_evs),
            "source_functions": ["SiCDoxExecutive._run_think()"],
            "cache_strategy": "Condicional: reconstruir só se DrawerRouter.hit alterou o board",
            "savings": "Elimina 50% das chamadas a build_synthesis_block",
        })

    # --- memo hits (já pré-tabelado internamente) ---
    memo_evs = by_fn.get("_memo_get", [])
    hits     = [e for e in memo_evs if e.get("hit")]
    if hits:
        pretable.append({
            "rank": 0,
            "name": "_memo cache (já ativo) — hit rate",
            "total_operations": len(hits),
            "calls_per_prompt": round(len(hits) / total_prompts, 2),
            "avg_ms": _avg_ms(memo_evs),
            "source_functions": ["SiCDoxBridge._memo_get()"],
            "cache_strategy": "Já implementado. Aumentar repetition_memo_size para > 128.",
            "savings": f"Hit rate atual: {100*len(hits)/len(memo_evs):.1f}% — "
                       f"{len(hits)} inferências completas evitadas",
        })

    # Ordena por total_operations desc e atribui rank
    pretable.sort(key=lambda x: x["total_operations"], reverse=True)
    for i, entry in enumerate(pretable, 1):
        entry["rank"] = i

    # Salva JSON
    PRETABLE_FILE.write_text(
        json.dumps({"meta": {"total_prompts": total_prompts,
                              "total_events": len(events)},
                     "candidates": pretable},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[ANÁLISE] Tabela de pré-cômputo salva em: {PRETABLE_FILE}")

    # -----------------------------------------------------------------------
    # 2. Detalhe por prompt
    # -----------------------------------------------------------------------

    lines: list[str] = []
    lines.append("DETALHE POR PROMPT\n" + "=" * 60)

    for pidx in sorted(by_prompt.keys()):
        evs = by_prompt[pidx]
        fn_counts: dict[str, int] = defaultdict(int)
        fn_ms: dict[str, float] = defaultdict(float)
        for ev in evs:
            fn_counts[ev["fn"]] += 1
            fn_ms[ev["fn"]] += ev.get("elapsed_ms", 0)

        # Recupera dados úteis
        ask_start = next((e for e in evs if e["fn"] == "ask:start"), {})
        ask_done  = next((e for e in evs if e["fn"] == "ask:done"), {})
        engine_ev = next((e for e in evs if e["fn"] == "_call_engine"), {})
        memo_hit  = any(e.get("hit") for e in evs if e["fn"] == "_memo_get")

        lines.append(f"\n[Prompt #{pidx}]")
        lines.append(f"  prompt_len    : {ask_start.get('prompt_len', '?')} chars")
        lines.append(f"  memo hit      : {memo_hit}")
        lines.append(f"  output_len    : {ask_done.get('output_len', '?')} chars")
        lines.append(f"  total_ms ask  : {ask_done.get('elapsed_ms', '?')}")
        if engine_ev:
            lines.append(f"  prompt_tokens : {engine_ev.get('prompt_tokens', '?')}")
            lines.append(f"  comp_tokens   : {engine_ev.get('completion_tokens', '?')}")
            lines.append(f"  llm_call_ms   : {engine_ev.get('llm_call_ms', '?')}")

        # Funções chamadas, ordenadas por count
        lines.append("  Chamadas:")
        for fn, count in sorted(fn_counts.items(), key=lambda x: x[1], reverse=True):
            ms = fn_ms[fn]
            lines.append(f"    {fn:<35} ×{count}   ({ms:.2f} ms total)")

    BY_PROMPT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"[ANÁLISE] Detalhe por prompt salvo em: {BY_PROMPT_FILE}")

    # -----------------------------------------------------------------------
    # 3. Print resumo no terminal
    # -----------------------------------------------------------------------

    print()
    print("=" * 60)
    print("  CANDIDATOS A PRÉ-TABELAMENTO (por volume)")
    print("=" * 60)
    for entry in pretable:
        print(f"  #{entry['rank']}  {entry['name']}")
        print(f"       Operações totais : {entry['total_operations']}")
        print(f"       Por prompt       : {entry['calls_per_prompt']}")
        print(f"       Estratégia       : {entry['cache_strategy']}")
        print()


def _avg_ms(evs: list[dict]) -> float:
    times = [e.get("elapsed_ms", 0) for e in evs if "elapsed_ms" in e]
    return round(sum(times) / len(times), 4) if times else 0.0


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not EVENTS_FILE.exists():
        print(f"[ERRO] Arquivo não encontrado: {EVENTS_FILE}")
        print("       Execute primeiro: python orn_infer_profiler.py")
        sys.exit(1)

    print(f"[ANÁLISE] Carregando {EVENTS_FILE} ...")
    events = load_events(EVENTS_FILE)
    print(f"[ANÁLISE] {len(events)} eventos carregados.")
    analyze(events)