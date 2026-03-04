# -*- coding: utf-8 -*-
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

from typing import Callable

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

Question: {question}"""


# ---------------------------------------------------------------------------
# AutoSearchDecider
# ---------------------------------------------------------------------------

class AutoSearchDecider:
    """Decide se uma pergunta precisa de busca externa antes da inferência.

    OSL-17: Não instancia OrnCrawler nem SiCDoxBridge — recebe callables.
    """

    def decide(self, question: str,
               server_ask_fn: Callable[[str, int], dict | None]) -> str | None:
        """Executa a 1ª pass e retorna o termo de busca ou None.

        Args:
            question:      Pergunta original do usuário.
            server_ask_fn: Função ask() do server_client — injetada pelo CLI.

        Returns:
            str  — termo de busca extraído ("asyncio", "KV-cache", etc.)
            None — modelo decidiu que não precisa de busca, ou falhou.
        """
        if not question.strip():
            return None

        prompt   = _build_decision_prompt(question)
        response = server_ask_fn(prompt, 20)   # max_tokens=20 — barato

        if response is None or response.get("error"):
            return None   # servidor offline ou erro — não bloqueia o pipeline

        raw_text = response.get("output", "")
        return _parse_response(raw_text)


# ---------------------------------------------------------------------------
# Internos — OSL-4: cada função faz uma coisa
# ---------------------------------------------------------------------------

def _build_decision_prompt(question: str) -> str:
    """Monta o prompt da 1ª pass."""
    return _DECISION_PROMPT.format(question=question.strip())


def _parse_response(text: str) -> str | None:
    """Extrai termo de busca da resposta do modelo.

    Parse defensivo — aceita variações razoáveis do Qwen 0.5B:
      "SEARCH:asyncio"      → "asyncio"
      "SEARCH: KV cache"    → "KV cache"
      "search:python list"  → "python list"
      "NO"                  → None
      "No, ..."             → None
      qualquer outra coisa  → None  (fail-safe)

    OSL-5.1: nunca levanta exceção — retorna None em caso de dúvida.
    """
    if not text:
        return None

    normalized = text.strip().lower()

    if not normalized.startswith("search:"):
        return None   # "NO", resposta vaga, alucinação — ignora

    term = text.strip()[len("search:"):].strip()   # preserva case original

    # Rejeita termo vazio ou muito longo (> 5 palavras = modelo alucinando)
    if not term or len(term.split()) > 5:
        return None

    return term