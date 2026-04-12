# -*- coding: utf-8 -*-
"""
ORN — PromptUtils
Pré-processamento de prompts antes da inferência.

Responsabilidades (revisão pós-remoção do pitstop):

  1. clean_prompt()       — Remove filler words em pt-BR.
                            NÃO comprime, NÃO altera max_tokens.
                            Substitui o papel ④ do antigo pitstop().

  2. enforce_hard_limit() — Trunca o OUTPUT gerado pela IA se ultrapassar
                            response_hard_limit (BridgeConfig).
                            Aplicado PÓS-inferência, nunca antes.
                            NÃO toca em max_tokens.

  3. remove_redundant_terms() — preservada (usada por clean_prompt e testes).
  4. compress_prompt()        — preservada mas NÃO chamada no pipeline principal.
                                Disponível para uso pontual (ex: context_file).
  5. pitstop()               — mantida por compatibilidade, mas REMOVIDA do ask().
                                Não chamá-la no bridge evita truncagem do prompt.

OSL-4:  Cada função faz uma coisa.
OSL-15: Nunca levanta exceção — retorna texto original em caso de erro.
OSL-18: stdlib only (re).
God: Hephaestus — forja o prompt bruto em forma limpa antes de enviar.
"""

from __future__ import annotations

import re

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
    if not text or len(text) < 4:
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
# Nova API pública — clean_prompt (substitui pitstop no bridge.ask())
# ---------------------------------------------------------------------------

def clean_prompt(prompt: str) -> str:
    """Limpa o prompt removendo filler words. Não comprime, não toca max_tokens.

    Chamado dentro de ask() ANTES de push no ContextWindow.
    Substituiu pitstop() após a remoção da compressão destrutiva.

    Args:
        prompt: Texto original do usuário.

    Returns:
        Prompt limpo. Idêntico ao original se não houver filler words.
    """
    return remove_redundant_terms(prompt)


# ---------------------------------------------------------------------------
# Mecanismo de parada — enforce_hard_limit (aplicado PÓS-inferência)
# ---------------------------------------------------------------------------

# Marcador adicionado quando o output é cortado pelo hard limit.
_HARD_LIMIT_MARKER = "\n\n[ORN] Resposta cortada pelo hard limit de tokens."


def enforce_hard_limit(output: str, response_hard_limit: int) -> str:
    """Trunca o OUTPUT gerado pela IA se ultrapassar response_hard_limit.

    Não usa max_tokens — opera exclusivamente sobre o texto já gerado.
    Corta no limite de palavra mais próximo para não quebrar tokens no meio.

    Posição no pipeline:
        bridge.ask() → _call_engine() → enforce_hard_limit(output) → retorno

    Args:
        output:               Texto gerado pelo LLM.
        response_hard_limit:  Limite máximo de palavras (BridgeConfig).
                              Palavras são usadas como proxy de tokens (≈1:1
                              para código; conservador para prosa).

    Returns:
        Output original se dentro do limite, ou output truncado com marcador.
    """
    if not output or response_hard_limit <= 0:
        return output

    # Estimativa rápida: split por whitespace
    words = output.split()
    if len(words) <= response_hard_limit:
        return output  # dentro do limite — sem tocar

    try:
        # Reconstrói até o limite de palavras preservando espaçamento original
        # Estratégia: encontra a posição do char onde a palavra N termina
        pos = 0
        count = 0
        for i, ch in enumerate(output):
            if ch in (" ", "\t", "\n", "\r"):
                if count >= response_hard_limit:
                    pos = i
                    break
            else:
                # início de uma nova palavra (transição de espaço para char)
                if i == 0 or output[i - 1] in (" ", "\t", "\n", "\r"):
                    count += 1
        else:
            pos = len(output)  # não encontrou limite (nunca deveria chegar aqui)

        truncated = output[:pos].rstrip()
        return truncated + _HARD_LIMIT_MARKER

    except Exception:
        return output  # OSL-15: falha silenciosa — preserva output original


# ---------------------------------------------------------------------------
# ② Compression — truncagem por orçamento de tokens (uso pontual)
# ---------------------------------------------------------------------------

def compress_prompt(text: str, max_chars: int) -> str:
    """Trunca o prompt para caber em max_chars.

    NÃO usada no pipeline principal (ask()). Disponível para uso pontual
    como injeção de context_file ou snippets longos do gaveteiro.

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

    max_chars = max(100000, max_chars)
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
# pitstop — mantida por compatibilidade (NÃO chamar no bridge.ask())
# ---------------------------------------------------------------------------

def pitstop(
    prompt: str,
    active_window: int = 256,
) -> tuple[str, int]:
    return clean_prompt(prompt)
