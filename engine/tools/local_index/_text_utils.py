# -*- coding: utf-8 -*-
# engine/tools/local_index/_text_utils.py
"""
ORN — LocalIndex / Text Utilities
Funções puras de transformação e normalização de texto.

Grupos de responsabilidade:
  § Normalização       — normalize_text_for_match, trigrams_for,
                         similarity_ratio, normalize_math_text
  § HTML → texto       — strip_html, extract_code_blocks,
                         restore_code_placeholders
  § Limpeza de corpo   — clean_body, like_escape
  § Compressão         — compress, decompress
  § Código (busca)     — extract_code_blocks_for_search,
                         canonical_query_languages,
                         score_code_only_match, format_code_only_body
  § Formatação CLI     — format_snippet_for_terminal

OSL-4:  Cada função faz uma coisa. Sem efeitos colaterais.
OSL-15: Funções de parse nunca levantam — retornam "" / [] / set() em falha.
OSL-18: stdlib + rapidfuzz opcional; pyzstd e pyzim importados lazy.
"""

from __future__ import annotations

import difflib
import html as _html_lib
import logging
import re
import unicodedata
from typing import Optional

logger = logging.getLogger("engine.tools.local_index.text_utils")

# ---------------------------------------------------------------------------
# Aliases de linguagem (compartilhados com _search.py)
# ---------------------------------------------------------------------------

LANGUAGE_ALIASES: dict[str, str] = {
    "py": "python",   "python": "python",
    "js": "javascript", "javascript": "javascript",
    "ts": "typescript", "typescript": "typescript",
    "java": "java",
    "c": "c",
    "cpp": "cpp",     "c++": "cpp",
    "csharp": "csharp", "cs": "csharp",
    "go": "go",       "golang": "go",
    "rust": "rust",
    "rb": "ruby",     "ruby": "ruby",
    "php": "php",
    "swift": "swift",
    "kotlin": "kotlin",
    "scala": "scala",
}

# ---------------------------------------------------------------------------
# Regexes de módulo (compiladas uma vez)
# ---------------------------------------------------------------------------

_RE_SCRIPT  = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_RE_NAV     = re.compile(
    r'<[^>]*(navbox|mw-toc|mw-jump|sidebar|reflist)[^>]*>.*?</\w+>',
    re.DOTALL | re.IGNORECASE,
)
_RE_CODE    = re.compile(
    r"(?P<open><(?P<tag>pre|code|syntaxhighlight|source|math|math-display)"
    r"(?P<attrs>[^>]*)>)(?P<body>.*?)(?P<close></(?P=tag)>)",
    re.DOTALL | re.IGNORECASE,
)
_RE_TAG     = re.compile(r"<[^>\n]+>")
_RE_ENTITY  = re.compile(r"&(?:[a-zA-Z]{2,8}|#\d{1,6});")
_RE_MULTI   = re.compile(r"[ \t]{2,}")
_RE_NEWL    = re.compile(r"\n{3,}")
_RE_URL     = re.compile(r"https?://\S+")

_CODE_BLOCK_SEARCH_RE = re.compile(
    r"\[CODE-BEGIN\s*(?P<lang>[^\]\n]*)\]\n?(?P<body>.*?)\n?\[CODE-END\]",
    re.DOTALL | re.IGNORECASE,
)

# rapidfuzz é opcional — fallback para difflib
try:
    from rapidfuzz import fuzz as _fuzz
    _HAS_RAPIDFUZZ = True
except Exception:
    _fuzz = None
    _HAS_RAPIDFUZZ = False


# ===========================================================================
# § Normalização
# ===========================================================================

def normalize_text_for_match(s: str) -> str:
    """Lowercase + strip de acentos + colapso de espaços.

    Nunca levanta — retorna "" para entrada inválida.
    """
    if not s:
        return ""
    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s)


def trigrams_for(s: str) -> set[str]:
    """Conjunto de trigramas de `s` (normalizado com padding de bordas)."""
    s = normalize_text_for_match(s)
    if not s:
        return set()
    padded = f"  {s} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def similarity_ratio(a: str, b: str) -> float:
    """Razão de similaridade [0.0, 1.0] entre duas strings."""
    if _HAS_RAPIDFUZZ:
        return _fuzz.token_sort_ratio(a, b) / 100.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def normalize_math_text(text: str) -> str:
    """Compacta fórmulas LaTeX/MathML para exibição em terminal."""
    if not text:
        return ""
    compact = " ".join(ln.strip() for ln in text.splitlines() if ln.strip())
    compact = re.sub(r"\s+", " ", compact).strip()
    m = re.search(r"\{\\displaystyle\s*(.+)\}\s*$", compact)
    if m and m.group(1).strip():
        compact = m.group(1).strip()
    compact = re.sub(r"\s+([\)\]\}])", r"\1", compact)
    compact = re.sub(r"([\(\[\{])\s+",  r"\1", compact)
    return compact


# ===========================================================================
# § HTML → texto
# ===========================================================================

def extract_code_blocks(html: str) -> tuple[str, list[tuple[str, str]]]:
    """Substitui blocos <pre>/<code>/<math> por placeholders.

    Returns:
        (html_sem_blocos, [(placeholder, representação_textual), ...])
    """
    code_blocks: list[tuple[str, str]] = []
    out_parts: list[str] = []
    last = 0

    for idx, m in enumerate(_RE_CODE.finditer(html)):
        start, end = m.span()
        tag   = m.group("tag").lower()
        attrs = m.group("attrs") or ""
        body  = m.group("body") or ""

        body_clean = _html_lib.unescape(re.sub(r"<[^>]+>", "", body))

        if tag in ("math", "math-display"):
            ph   = f"__MATH_BLOCK_{idx}__"
            repr_ = f"\n[MATH-BEGIN]\n{body_clean.strip()}\n[MATH-END]\n"
        else:
            lang = _extract_lang_from_attrs(attrs)
            ph   = f"__CODE_BLOCK_{idx}__"
            lang_str = f" {lang}" if lang else ""
            repr_ = f"\n[CODE-BEGIN{lang_str}]\n{body_clean.strip()}\n[CODE-END]\n"

        code_blocks.append((ph, repr_))
        out_parts.append(html[last:start])
        out_parts.append(ph)
        last = end

    out_parts.append(html[last:])
    return "".join(out_parts), code_blocks


def _extract_lang_from_attrs(attrs: str) -> str:
    """Extrai nome de linguagem dos atributos de uma tag <pre>/<code>."""
    data_lang = re.search(r'data-lang=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
    if data_lang:
        return data_lang.group(1).lower()

    cls_m = re.search(r'class=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
    if cls_m:
        parts = re.split(r"[^\w+-]+", cls_m.group(1))
        for p in reversed(parts):
            if p and len(p) <= 20 and re.match(r"^[a-zA-Z0-9_+-]+$", p):
                return p.lower()
    return ""


def restore_code_placeholders(text: str, code_blocks: list[tuple[str, str]]) -> str:
    for ph, code in code_blocks:
        text = text.replace(ph, code)
    return text


def strip_html(html_str: str, max_chars: int = 64000) -> str:
    """Converte HTML em texto limpo, preservando blocos de código/math.

    Pipeline:
      1. Isola blocos <code>/<math> com placeholders.
      2. Tenta strip via DLL C (10× mais rápido); fallback Python.
      3. Decodifica entidades HTML.
      4. Restaura placeholders.
      5. Trunca em max_chars sem cortar blocos abertos.
    """
    if not html_str:
        return ""

    extracted_html, code_blocks = extract_code_blocks(html_str)

    try:
        from engine.native.html_helper import strip_html_fast  # lazy — OSL-3
        text = strip_html_fast(extracted_html.encode("utf-8", errors="replace"))
        if not text:
            raise ValueError("DLL C retornou vazio")
    except Exception:
        text = _RE_NAV.sub(" ", extracted_html)
        text = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = _RE_TAG.sub(" ", text)

    text = _RE_ENTITY.sub(" ", text)
    text = _html_lib.unescape(text)
    text = _RE_URL.sub(" ", text)
    text = _RE_NEWL.sub("\n\n", text).strip()

    if code_blocks:
        text = restore_code_placeholders(text, code_blocks)

    if len(text) > max_chars:
        text = _truncate_respecting_blocks(text, max_chars)

    return text


def _truncate_respecting_blocks(text: str, max_chars: int) -> str:
    """Corta em max_chars sem deixar blocos [CODE-BEGIN] ou [MATH-BEGIN] abertos."""
    cut = text[:max_chars]
    for open_tag, close_tag in (("[CODE-BEGIN", "[CODE-END]"), ("[MATH-BEGIN", "[MATH-END]")):
        last_open  = cut.rfind(open_tag)
        last_close = cut.rfind(close_tag)
        if last_open > last_close:
            actual_end = text.find(close_tag, max_chars)
            return text[:actual_end + len(close_tag)] if actual_end != -1 else cut
    return cut


# ===========================================================================
# § Limpeza de corpo de documento
# ===========================================================================

def clean_body(text: str, max_chars: int = 100_000) -> str:
    """Normaliza espaçamento, remove caracteres de controle e duplicatas no topo.

    Mantém integridade de blocos [CODE-BEGIN] / [MATH-BEGIN].
    """
    if not text:
        return ""
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return ""

    # Caracteres de controle e normalização de quebras
    text = "".join(ch for ch in text if ch >= " " or ch in ("\n", "\t"))
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")

    lines = [ln.rstrip() for ln in text.split("\n")]

    # Remove linhas iniciais em branco
    while lines and not lines[0].strip():
        lines.pop(0)

    # Remove repetições da primeira linha (títulos duplicados por templates)
    lines = _deduplicate_heading(lines)

    # Remove duplicatas curtas nas primeiras 40 linhas
    lines = _deduplicate_short_top(lines, window=40)

    # Trunca respeitando blocos abertos
    lines = _truncate_lines(lines, max_chars)

    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _norm_key(s: str) -> str:
    return re.sub(r"[^\w\s]", "", s or "").strip().lower()


def _deduplicate_heading(lines: list[str]) -> list[str]:
    if not lines:
        return lines
    first = lines[0].strip()
    if not (0 < len(first) <= 120) or "[CODE-BEGIN" in first or "[MATH-BEGIN" in first:
        return lines
    fk = _norm_key(first)
    i = 1
    while i < min(len(lines), 30):
        if _norm_key(lines[i]) == fk:
            lines.pop(i)
            continue
        if lines[i].strip() == "" and i + 1 < len(lines) and _norm_key(lines[i + 1]) == fk:
            lines.pop(i)
            lines.pop(i)
            continue
        i += 1
    return lines


def _deduplicate_short_top(lines: list[str], window: int = 40) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ln in lines[:window]:
        key = ln.strip().lower()
        is_block_marker = any(m in key for m in ("[code-begin", "[code-end]", "[math-begin", "[math-end]"))
        if key and len(key) <= 120 and not is_block_marker:
            if key in seen:
                continue
            seen.add(key)
        out.append(ln)
    return out + lines[window:]


def _truncate_lines(lines: list[str], max_chars: int) -> list[str]:
    out: list[str] = []
    total = 0
    in_block = False
    for ln in lines:
        if "[CODE-BEGIN" in ln or "[MATH-BEGIN" in ln:
            in_block = True
        elif "[CODE-END]" in ln or "[MATH-END]" in ln:
            in_block = False
        out.append(ln)
        total += len(ln) + 1
        if total > max_chars and not in_block:
            out.append("...")
            break
    return out


def like_escape(s: str) -> str:
    """Escapa caracteres especiais para uso em SQL LIKE."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ===========================================================================
# § Compressão (pyzstd opcional)
# ===========================================================================

def compress(data: bytes) -> bytes:
    """Comprime com pyzstd (flag=0x01) ou armazena raw (flag=0x00)."""
    try:
        import pyzstd
        return b"\x01" + pyzstd.compress(data)
    except Exception:
        logger.debug("pyzstd indisponível; armazenando payload raw (flag=0x00)")
        return b"\x00" + data


def decompress(data: bytes) -> bytes:
    """Descomprime payload gerado por compress().

    Raises:
        RuntimeError: flag desconhecida ou pyzstd ausente para payload comprimido.
    """
    if not data:
        return data
    flag    = data[0:1]
    payload = data[1:]

    if flag == b"\x00":
        return payload

    if flag == b"\x01":
        try:
            import pyzstd
            return pyzstd.decompress(payload)
        except Exception:
            raise RuntimeError("Falha ao descomprimir payload zstd: pyzstd ausente ou corrompido")

    # Compatibilidade: blobs antigos sem flag mas com magic zstd
    if len(data) >= 5 and data[1:5] == b"\x28\xb5\x2f\xfd":
        try:
            import pyzstd
            return pyzstd.decompress(payload)
        except Exception:
            raise RuntimeError("Formato desconhecido e pyzstd indisponível")

    return payload  # fallback: assume raw


# ===========================================================================
# § Blocos de código para busca (modo --code-only)
# ===========================================================================

def extract_code_blocks_for_search(body_text: str) -> list[tuple[str, str]]:
    """Extrai pares (lang, code) dos marcadores [CODE-BEGIN lang]...[CODE-END]."""
    blocks: list[tuple[str, str]] = []
    for m in _CODE_BLOCK_SEARCH_RE.finditer(body_text or ""):
        lang = (m.group("lang") or "").strip().lower()
        body = (m.group("body") or "").strip()
        blocks.append((lang, body))
    return blocks


def canonical_query_languages(qwords: list[str]) -> set[str]:
    """Mapeia palavras da query para linguagens canônicas via LANGUAGE_ALIASES."""
    return {
        LANGUAGE_ALIASES[w.lower().strip()]
        for w in qwords
        if w.lower().strip() in LANGUAGE_ALIASES
    }


def score_code_only_match(body: str, query: str) -> float:
    blocks = extract_code_blocks_for_search(body)
    if not blocks:
        return 0.0

    q_lower = query.lower()
    q_words = re.findall(r"[a-z0-9_+#]+", q_lower)

    target_langs = set()
    search_terms = []

    # Separa o que é linguagem do que é termo de busca
    for w in q_words:
        if w in LANGUAGE_ALIASES:
            target_langs.add(LANGUAGE_ALIASES[w])
        else:
            search_terms.append(w)

    best_score = 0.0

    for lang, code in blocks:
        canonical_block_lang = LANGUAGE_ALIASES.get(lang, lang)

        # 1. Verifica match de linguagem
        lang_match = False
        if not target_langs:
            lang_match = True
        elif canonical_block_lang in target_langs:
            lang_match = True

        if not lang_match:
            continue

        # 2. Verifica se OS TERMOS existem DENTRO do código
        terms_found = 0
        code_lower = code.lower()
        for term in search_terms:
            if term in code_lower:
                terms_found += 1

        # FIX: Se o usuário digitou um termo e ele NÃO está no código, o bloco é inútil
        if search_terms and terms_found == 0:
            continue

        # Calcula a pontuação final do bloco
        score = 10.0 if target_langs else 1.0
        score += (terms_found * 50.0)
        
        # Bônus se TODOS os termos estiverem no código
        if search_terms and terms_found == len(search_terms):
            score += 100.0

        if score > best_score:
            best_score = score

    return best_score


def format_code_only_body(body: str, query: str) -> str:
    blocks = extract_code_blocks_for_search(body)
    if not blocks:
        return ""

    q_lower = query.lower()
    q_words = re.findall(r"[a-z0-9_+#]+", q_lower)

    target_langs = set()
    search_terms = []

    for w in q_words:
        if w in LANGUAGE_ALIASES:
            target_langs.add(LANGUAGE_ALIASES[w])
        else:
            search_terms.append(w)

    matched_blocks = []

    for lang, code in blocks:
        canonical_block_lang = LANGUAGE_ALIASES.get(lang, lang)

        lang_match = False
        if not target_langs:
            lang_match = True
        elif canonical_block_lang in target_langs:
            lang_match = True

        if not lang_match:
            continue

        terms_found = 0
        code_lower = code.lower()
        for term in search_terms:
            if term in code_lower:
                terms_found += 1

        # Ignora no output final os blocos que não contém o termo
        if search_terms and terms_found == 0:
            continue

        matched_blocks.append(f"```{lang}\n{code}\n```")

    return "\n\n".join(matched_blocks)


# ===========================================================================
# § Formatação para terminal
# ===========================================================================

def format_snippet_for_terminal(snippet: str) -> str:
    """Converte marcadores internos em markdown legível no CLI."""
    if not snippet:
        return ""

    def _code_repl(m: re.Match) -> str:
        lang = (m.group("lang") or "").strip()
        body = (m.group("body") or "").rstrip()
        return f"\n```{lang}\n{body}\n```\n"

    def _math_repl(m: re.Match) -> str:
        body = normalize_math_text(m.group("body") or "")
        return f"\n$$\n{body}\n$$\n" if body else ""

    rendered = re.sub(
        r"\[CODE-BEGIN\s*(?P<lang>[^\]\n]*)\]\n?(?P<body>.*?)\n?\[CODE-END\]",
        _code_repl,
        snippet,
        flags=re.DOTALL | re.IGNORECASE,
    )
    rendered = re.sub(
        r"\[MATH-BEGIN\]\n?(?P<body>.*?)\n?\[MATH-END\]",
        _math_repl,
        rendered,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return re.sub(r"\n{3,}", "\n\n", rendered).strip()