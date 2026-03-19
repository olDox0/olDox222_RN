# -*- coding: utf-8 -*-
# engine/tools/auto_search.py
"""
ORN — AutoSearch Decider (Hermes)
Decide autonomamente se uma pergunta precisa de contexto externo.

Fluxo two-pass (só modo servidor):
  1ª pass: decision_prompt → modelo → "SEARCH:<termo>" ou "NO"
  2ª pass: contexto do crawler + [TASK] + question → modelo → resposta final

OSL-4:  Três métodos curtos, cada um com uma responsabilidade.
OSL-5.1: parse defensivo — qualquer resposta inesperada vira None.
OSL-7:  decide() retorna str | None — chamador sempre verifica.
OSL-15: Falha no crawler não derruba o pipeline — avisa e continua.
OSL-17: Não chama o modelo diretamente — recebe server_ask_fn como injeção.
God: Hermes — mensageiro que decide o que buscar antes de entregar.
"""

from __future__ import annotations

from typing import Any, Callable

# ---------------------------------------------------------------------------
# Prompt de decisão — calibrado para Qwen 0.5B (max_tokens=20)
# ---------------------------------------------------------------------------

_DECISION_PROMPT = """\
You are a search decision engine.
Read the question and decide:
- If it requires CURRENT data, news, prices, or OBSCURE facts: respond ONLY with SEARCH:<term>
- For algorithms, syntax, standard library, well-known concepts: respond ONLY with NO

Examples of NO (never search these):
- bubble sort, quicksort, binary search
- Python syntax, C pointers, loops
- KV-cache explanation, recursion, Big O
- standard library functions

Examples of SEARCH:
- current version of library X
- recent news about Y
- price of Z

Rules:
- SEARCH:<term> must be 1-3 words max
- No explanation, no extra text

Question: {question}
"""


# ---------------------------------------------------------------------------
# AutoSearchDecider
# ---------------------------------------------------------------------------

class AutoSearchDecider:
    def decide(self, question: str, server_ask: Callable[[str, int], Any]) -> str | None:
        """
        Retorna um termo de busca ou None.
        Espera que server_ask(prompt, max_tokens=...) devolva dict JSON ou str.
        """
        if not _should_auto_search(question):
            return None

        decision_prompt = _build_decision_prompt(question)

        try:
            response = server_ask(decision_prompt, 20)
        except TypeError:
            # fallback caso a função injetada aceite só 1 argumento
            response = server_ask(decision_prompt)

        if response is None:
            return None

        if isinstance(response, str):
            text = response
        elif isinstance(response, dict):
            if response.get("error"):
                return None
            text = str(response.get("output", "")).strip()
        else:
            text = str(response).strip()

        return _parse_response(text)


# ---------------------------------------------------------------------------
# Internos — OSL-4: cada função faz uma coisa
# ---------------------------------------------------------------------------

def _build_decision_prompt(question: str) -> str:
    """Monta o prompt da 1ª pass."""
    return _DECISION_PROMPT.format(question=(question or "").strip())


def _parse_response(text: str) -> str | None:
    """Extrai termo de busca da resposta do modelo.

    Parse defensivo — aceita variações razoáveis do Qwen 0.5B:
      "SEARCH:asyncio"      → "asyncio"
      "SEARCH: KV cache"     → "KV cache"
      "search:python list"   → "python list"
      "NO"                  → None
      "No, ..."             → None
      qualquer outra coisa   → None  (fail-safe)
    """
    if not text:
        return None

    raw = text.strip()
    low = raw.lower()

    if low == "no":
        return None

    if not low.startswith("search:"):
        return None

    term = raw[len("search:"):].strip()

    if not term:
        return None

    if len(term.split()) > 3:
        return None

    bad_prefixes = (
        "i'm sorry",
        "sorry",
        "hello",
        "hi",
        "sure",
        "of course",
        "i can't",
        "i cannot",
    )
    low_term = term.lower()
    if any(low_term.startswith(p) for p in bad_prefixes):
        return None

    return term


def _should_auto_search(question: str) -> bool:
    q = (question or "").strip()
    if not q:
        return False
    if q.isdigit():
        return False
    if len(q) < 8:
        return False
    if len(q.split()) < 3:
        return False
    return True