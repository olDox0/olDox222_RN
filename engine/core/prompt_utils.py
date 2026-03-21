# -*- coding: utf-8 -*-
"""
ORN — PromptUtils
Pré-processamento de prompts antes da inferência.

Dois objetivos:
  1. Remove Redundant Terms  — elimina termos de cortesia e frases
     redundantes que inflatam o token count sem ajudar o modelo.
  2. Compression             — trunca o prompt para caber dentro da
     active_window configurada, preservando a parte mais informativa.

OSL-4:  Cada função faz uma coisa.
OSL-15: Nunca levanta exceção — retorna texto original em caso de erro.
OSL-18: stdlib only (re, unicodedata).
God: Hephaestus — forja o prompt bruto em forma limpa antes de enviar.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# ④ Remove Redundant Terms
# ---------------------------------------------------------------------------

# Frases de cortesia e preâmbulos que não ajudam o modelo a gerar código.
# Calibrado para português (ORN usa pt-BR por padrão).
_FILLER_PT = re.compile(
    r"\b("
    r"por favor|por gentileza|se puder|se possível|obrigado|obrigada|"
    r"gostaria que você|gostaria que voce|quero que você|quero que voce|"
    r"poderia (me |)?(fazer|criar|escrever|gerar)|você poderia|voce poderia|"
    r"você pode|voce pode|pode me (ajudar a|dar|fazer)|"
    r"me ajude a|me dê|me de |me da |"
    r"seria (muito |)?(possível|possivel)|seria (tão |)(gentil|amável|amavel)|"
    r"preciso que você|preciso que voce|preciso de (uma |)(ajuda|help)"
    r")\b",
    re.IGNORECASE,
)

# Palavras repetidas consecutivas: "faça faça" → "faça"
_CONSECUTIVE_WORDS = re.compile(
    r"\b(\w+)\b(\s+\1\b)+",
    re.IGNORECASE,
)

# Pontuação redundante: "...!!!" → "!"
_EXCESS_PUNCT = re.compile(r"([!?.]){2,}")

# Espaços múltiplos após remoções
_MULTI_SPACE = re.compile(r" {2,}")


def remove_redundant_terms(text: str) -> str:
    """Remove filler words e termos redundantes do prompt.

    Não remove palavras técnicas, nomes de variáveis, ou termos de código.
    Opera apenas em padrões de linguagem natural reconhecidamente supérfluos.

    Args:
        text: Prompt original do usuário.

    Returns:
        Prompt limpo. Nunca mais curto que 4 caracteres (proteção de conteúdo).
    """
    if not text or len(text) < 8:
        return text

    try:
        cleaned = _FILLER_PT.sub("", text)
        cleaned = _CONSECUTIVE_WORDS.sub(r"\1", cleaned)
        cleaned = _EXCESS_PUNCT.sub(r"\1", cleaned)
        cleaned = _MULTI_SPACE.sub(" ", cleaned).strip()

        # Segurança: nunca retorna string mais curta que 4 chars
        # (evita destruir prompts muito curtos como "fix")
        return cleaned if len(cleaned) >= 4 else text
    except Exception:
        return text  # OSL-15: falha silenciosa


# ---------------------------------------------------------------------------
# ② Compression — truncagem por orçamento de tokens
# ---------------------------------------------------------------------------

def compress_prompt(text: str, max_chars: int) -> str:
    """Trunca o prompt para caber em max_chars.

    Estratégia (em ordem de preferência):
      1. Se cabe, retorna sem modificação.
      2. Tenta cortar em limite de frase (". " ou "\\n").
      3. Corta em limite de palavra.
      4. Corta hard no limite.

    Args:
        text:      Texto a comprimir.
        max_chars: Limite máximo de caracteres (≥ 16).

    Returns:
        Texto truncado com "[…]" no final se houve corte.
    """
    if not text or len(text) <= max_chars:
        return text

    max_chars = max(16, max_chars)
    budget = max_chars - 5  # reserva espaço para " […]"

    # Tenta cortar em limite de frase (para trás)
    cut = text[:budget]
    for sep in (". ", ".\n", "\n\n", "\n", " "):
        idx = cut.rfind(sep)
        if idx >= max(20, budget // 2):
            return cut[: idx + len(sep)].rstrip() + " […]"

    # Corta em limite de palavra
    idx = cut.rfind(" ")
    if idx > 0:
        return cut[:idx] + " […]"

    return cut + " […]"  # hard cut


# ---------------------------------------------------------------------------
# Pitstop — combina ④ + ② + ajuste de max_tokens
# ---------------------------------------------------------------------------

def pitstop(
    prompt: str,
    max_tokens: int,
    active_window: int = 256,
) -> tuple[str, int]:
    """Pit stop pré-inferência: limpa e comprime o prompt, ajusta max_tokens.

    Combina Remove Redundant Terms e Compression numa única passada.
    Chamado dentro de ask() antes de push no ContextWindow.

    Args:
        prompt:        Texto original do usuário.
        max_tokens:    Limite de tokens de saída solicitado.
        active_window: Tamanho da janela ativa em tokens (BridgeConfig).

    Returns:
        (prompt_limpo, max_tokens_ajustado)
    """
    if not prompt:
        return prompt, max_tokens

    # ④ Remove redundâncias antes de comprimir (reduz tamanho antes do corte)
    cleaned = remove_redundant_terms(prompt)

    # ② Comprime para caber no orçamento
    # Estima: 1 token ≈ 3 chars. Reserva max_tokens para a resposta + 32 de overhead.
    overhead = max_tokens + 32
    prompt_budget_tokens = max(32, active_window - overhead)
    max_chars = prompt_budget_tokens * 3
    cleaned = compress_prompt(cleaned, max_chars)

    # Ajuste de max_tokens: se o prompt ficou muito curto após limpeza,
    # provavelmente é uma pergunta simples — limita a resposta para economizar tempo.
    # Regra: prompts < 40 chars raramente precisam de 192 tokens de saída.
    if len(cleaned) < 40 and max_tokens > 64:
        max_tokens = 64

    return cleaned, max_tokens