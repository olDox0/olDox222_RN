# -*- coding: utf-8 -*-
# engine/tools/local_index.py

from __future__ import annotations

import argparse
import array
import concurrent.futures
import difflib
import hashlib
import html as _html_lib
import logging
import os
import re
import sqlite3
import struct
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Iterator, List, Optional, Tuple

from engine.tools.inverted_index import InvertedIndexBuilder, InvertedIndexSearcher
from engine.telemetry.core import orn_span, GLOBAL_TELEMETRY

# ---------------------------------------------------------------------------
# Config / constantes
# ---------------------------------------------------------------------------

logger = logging.getLogger("engine.tools.local_index")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ZIM_DIR   = Path(os.environ.get("SICDOX_ZIM_DIR",   "data/zim"))
INDEX_DIR = Path(os.environ.get("SICDOX_INDEX_DIR", "data/index"))

#_DEFAULT_GGUF  = r"C:\Users\olDox222\Documents\A20251122\DOSSIER\Altonomo\Projetos_E_Programas\Projeto_OIA\olDox222RN\ORN\models\sicdox\Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF\qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
_DEFAULT_GGUF  = r"C:\Users\olDox222\Documents\A20251122\DOSSIER\Altonomo\Projetos_E_Programas\Projeto_OIA\olDox222RN\ORN\models\sicdox\qwen2.5-coder-0.5b-instruct-q2_k.gguf"
_GGUF_PATH_ENV = "SICDOX_GGUF"

# ---------------------------------------------------------------------------
# Regexes de módulo
# ---------------------------------------------------------------------------

_RE_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_RE_NAV    = re.compile(
    r'<[^>]*(navbox|mw-toc|mw-jump|sidebar|reflist)[^>]*>.*?</\w+>',
    re.DOTALL | re.IGNORECASE,
)
_RE_CODE   = re.compile(
    r"(?P<open><(?P<tag>pre|code|syntaxhighlight|source|math|math-display)"
    r"(?P<attrs>[^>]*)>)(?P<body>.*?)(?P<close></(?P=tag)>)",
    re.DOTALL | re.IGNORECASE,
)
_RE_TAG    = re.compile(r"<[^>\n]+>")
_RE_ENTITY = re.compile(r"&(?:[a-zA-Z]{2,8}|#\d{1,6});")
_RE_MULTI  = re.compile(r"[ \t]{2,}")
_RE_NEWL   = re.compile(r"\n{3,}")
_RE_URL    = re.compile(r"https?://\S+")

_CODE_BLOCK_SEARCH_RE = re.compile(
    r"\[CODE-BEGIN\s*(?P<lang>[^\]\n]*)\]\n?(?P<body>.*?)\n?\[CODE-END\]",
    re.DOTALL | re.IGNORECASE,
)

_LANGUAGE_ALIASES: dict[str, str] = {
    "py": "python",    "python": "python",
    "js": "javascript","javascript": "javascript",
    "ts": "typescript","typescript": "typescript",
    "java": "java",
    "c": "c",
    "cpp": "cpp",      "c++": "cpp",
    "csharp": "csharp","cs": "csharp",
    "go": "go",        "golang": "go",
    "rust": "rust",
    "rb": "ruby",      "ruby": "ruby",
    "php": "php",
    "swift": "swift",
    "kotlin": "kotlin",
    "scala": "scala",
}

try:
    from rapidfuzz import fuzz as _fuzz
    _HAS_RAPIDFUZZ = True
except Exception:
    _fuzz = None
    _HAS_RAPIDFUZZ = False

# Pesos de scoring
_SCORE_WEIGHTS_NORMAL = dict(title_boost=120.0, early_density=300.0, density=120.0, tf=30.0,  front_bonus=80.0)
_SCORE_WEIGHTS_CODE   = dict(title_boost=45.0,  early_density=420.0, density=220.0, tf=55.0,  front_bonus=20.0)

_ZIM_MAGIC       = 0x044D495A
_ZIM_HEADER_SIZE = 80


# ===========================================================================
# § Normalização de texto
# ===========================================================================

def _normalize_text_for_match(s: str) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s)


def _trigrams_for(s: str) -> set[str]:
    s = _normalize_text_for_match(s)
    if not s:
        return set()
    padded = f"  {s} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def _similarity_ratio(a: str, b: str) -> float:
    if _HAS_RAPIDFUZZ:
        return _fuzz.token_sort_ratio(a, b) / 100.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _normalize_math_text(text: str) -> str:
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

def _extract_lang_from_attrs(attrs: str) -> str:
    data_lang = re.search(r'data-lang=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
    if data_lang:
        return data_lang.group(1).lower()
    cls_m = re.search(r'class=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
    if cls_m:
        for p in reversed(re.split(r"[^\w+-]+", cls_m.group(1))):
            if p and len(p) <= 20 and re.match(r"^[a-zA-Z0-9_+-]+$", p):
                return p.lower()
    return ""


def _extract_code_blocks(html: str) -> tuple[str, list[tuple[str, str]]]:
    code_blocks: list[tuple[str, str]] = []
    out_parts:   list[str] = []
    last = 0

    for idx, m in enumerate(_RE_CODE.finditer(html)):
        start, end = m.span()
        tag   = m.group("tag").lower()
        attrs = m.group("attrs") or ""
        body  = m.group("body") or ""

        body_clean = _html_lib.unescape(re.sub(r"<[^>]+>", "", body))

        if tag in ("math", "math-display"):
            ph    = f"__MATH_BLOCK_{idx}__"
            repr_ = f"\n[MATH-BEGIN]\n{body_clean.strip()}\n[MATH-END]\n"
        else:
            lang  = _extract_lang_from_attrs(attrs)
            ph    = f"__CODE_BLOCK_{idx}__"
            repr_ = f"\n[CODE-BEGIN{' ' + lang if lang else ''}]\n{body_clean.strip()}\n[CODE-END]\n"

        code_blocks.append((ph, repr_))
        out_parts.append(html[last:start])
        out_parts.append(ph)
        last = end

    out_parts.append(html[last:])
    return "".join(out_parts), code_blocks


def _restore_code_placeholders(text: str, code_blocks: list[tuple[str, str]]) -> str:
    for ph, code in code_blocks:
        text = text.replace(ph, code)
    return text


def _truncate_respecting_blocks(text: str, max_chars: int) -> str:
    cut = text[:max_chars]
    for open_tag, close_tag in (("[CODE-BEGIN", "[CODE-END]"), ("[MATH-BEGIN", "[MATH-END]")):
        if cut.rfind(open_tag) > cut.rfind(close_tag):
            end = text.find(close_tag, max_chars)
            return text[:end + len(close_tag)] if end != -1 else cut
    return cut


def _strip_html(html_str: str, max_chars: int = 64000) -> str:
    if not html_str:
        return ""

    extracted_html, code_blocks = _extract_code_blocks(html_str)

    try:
        from engine.native.html_helper import strip_html_fast
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
        text = _restore_code_placeholders(text, code_blocks)

    if len(text) > max_chars:
        text = _truncate_respecting_blocks(text, max_chars)

    return text


# ===========================================================================
# § Limpeza de corpo de documento
# ===========================================================================

def _norm_key(s: str) -> str:
    return re.sub(r"[^\w\s]", "", s or "").strip().lower()


def _deduplicate_heading(lines: list[str]) -> list[str]:
    if not lines:
        return lines
    first = lines[0].strip()
    if not (0 < len(first) <= 120) or "[CODE-BEGIN" in first or "[MATH-BEGIN" in first:
        return lines
    fk = _norm_key(first)
    i  = 1
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
    out:  list[str] = []
    for ln in lines[:window]:
        key = ln.strip().lower()
        is_marker = any(m in key for m in ("[code-begin", "[code-end]", "[math-begin", "[math-end]"))
        if key and len(key) <= 120 and not is_marker:
            if key in seen:
                continue
            seen.add(key)
        out.append(ln)
    return out + lines[window:]


def _truncate_lines(lines: list[str], max_chars: int) -> list[str]:
    out      = []
    total    = 0
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


def _clean_body(text: str, max_chars: int = 100_000) -> str:
    if not text:
        return ""
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return ""

    text  = "".join(ch for ch in text if ch >= " " or ch in ("\n", "\t"))
    text  = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    lines = [ln.rstrip() for ln in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)

    lines = _deduplicate_heading(lines)
    lines = _deduplicate_short_top(lines)
    lines = _truncate_lines(lines, max_chars)

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ===========================================================================
# § Compressão
# ===========================================================================

def _compress(data: bytes) -> bytes:
    try:
        import pyzstd
        return b"\x01" + pyzstd.compress(data)
    except Exception:
        logger.debug("pyzstd indisponível; armazenando payload raw (flag=0x00)")
        return b"\x00" + data


def _decompress(data: bytes) -> bytes:
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
    if len(data) >= 5 and data[1:5] == b"\x28\xb5\x2f\xfd":
        try:
            import pyzstd
            return pyzstd.decompress(payload)
        except Exception:
            raise RuntimeError("Formato desconhecido e pyzstd indisponível")
    return payload


# ===========================================================================
# § Blocos de código para busca (modo --code-only)
# ===========================================================================

def _extract_code_blocks_for_search(body_text: str) -> list[tuple[str, str]]:
    return [
        ((m.group("lang") or "").strip().lower(), (m.group("body") or "").strip())
        for m in _CODE_BLOCK_SEARCH_RE.finditer(body_text or "")
    ]


def _canonical_query_languages(qwords: list[str]) -> set[str]:
    return {
        _LANGUAGE_ALIASES[w.lower().strip()]
        for w in qwords
        if w.lower().strip() in _LANGUAGE_ALIASES
    }


def _score_code_only_match(
    body_text: str, q_raw: str, qwords: list[str]
) -> tuple[bool, float, int, int]:
    blocks = _extract_code_blocks_for_search(body_text)
    if not blocks:
        return False, 0.0, 0, 0

    all_code = "\n".join(
        ((f"[lang:{lang}]\n" if lang else "") + body) for lang, body in blocks
    ).lower()

    query_terms   = [w for w in qwords if len(w) >= 2] or ([q_raw.lower()] if q_raw.strip() else [])
    phrase_match  = q_raw.lower() in all_code
    matched_terms = {w for w in query_terms if w in all_code}

    query_langs = _canonical_query_languages(qwords)
    if query_langs:
        block_langs = {_LANGUAGE_ALIASES.get(lang, lang) for lang, _ in blocks if lang}
        if block_langs and not (query_langs & block_langs):
            if not any(lang in all_code for lang in query_langs):
                return False, 0.0, len(matched_terms), len(query_terms)

    coverage_terms = query_terms
    if query_langs and not any(lang for lang, _ in blocks):
        non_lang = [w for w in query_terms if _LANGUAGE_ALIASES.get(w, w) not in query_langs]
        if non_lang:
            coverage_terms = non_lang
    matched_cov = {w for w in coverage_terms if w in all_code}
    n_cov = len(coverage_terms)

    if not phrase_match:
        if n_cov >= 2 and len(matched_cov) < 2:
            return False, 0.0, len(matched_terms), len(query_terms)
        if n_cov >= 3 and (len(matched_cov) / n_cov) < 0.67:
            return False, 0.0, len(matched_terms), len(query_terms)

    tf  = float(sum(all_code.count(w) for w in query_terms))
    tf += 18.0 if phrase_match else 0.0
    tf += (len(matched_terms) / max(1, len(query_terms))) * 10.0
    return tf > 0, tf, len(matched_terms), len(query_terms)


def _format_code_only_body(body_text: str, max_blocks: int = 8) -> str:
    blocks = _extract_code_blocks_for_search(body_text)
    if not blocks:
        return ""
    return "\n\n".join(
        f"[CODE-BEGIN{' ' + lang if lang else ''}]\n{code}\n[CODE-END]"
        for lang, code in blocks[:max_blocks]
    ).strip()


# ===========================================================================
# § Formatação para terminal
# ===========================================================================

def _format_snippet_for_terminal(snippet: str) -> str:
    if not snippet:
        return ""

    def _code_repl(m: re.Match) -> str:
        lang = (m.group("lang") or "").strip()
        body = (m.group("body") or "").rstrip()
        return f"\n```{lang}\n{body}\n```\n"

    def _math_repl(m: re.Match) -> str:
        body = _normalize_math_text(m.group("body") or "")
        return f"\n$$\n{body}\n$$\n" if body else ""

    rendered = re.sub(
        r"\[CODE-BEGIN\s*(?P<lang>[^\]\n]*)\]\n?(?P<body>.*?)\n?\[CODE-END\]",
        _code_repl, snippet, flags=re.DOTALL | re.IGNORECASE,
    )
    rendered = re.sub(
        r"\[MATH-BEGIN\]\n?(?P<body>.*?)\n?\[MATH-END\]",
        _math_repl, rendered, flags=re.DOTALL | re.IGNORECASE,
    )
    return re.sub(r"\n{3,}", "\n\n", rendered).strip()


# ===========================================================================
# § TokenizerBridge (inalterado)
# ===========================================================================

class TokenizerBridge:
    """Tokenizador thread-safe com fast-path via servidor ORN.

    Hierarquia de fallback (mais rápido → mais lento):
      1. Servidor ORN (socket 127.0.0.1:8371) — modelo já carregado, zero overhead.
      2. vocab_only local                      — carga ~10s no N2808, só se servidor offline.
    """

    _llm_vocab = None
    _lock      = Lock()

    _server_ok:        bool | None = None
    _server_fail_time: float       = 0.0
    _SERVER_HOST  = "127.0.0.1"
    _SERVER_PORT  = int(os.environ.get("ORN_SERVER_PORT", "8371"))
    _SERVER_RETRY_S: float = 30.0

    @classmethod
    def _server_available(cls) -> bool:
        import socket as _sock, time as _time
        if cls._server_ok is False:
            if _time.monotonic() - cls._server_fail_time < cls._SERVER_RETRY_S:
                return False
        try:
            with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
                s.settimeout(0.3)
                s.connect((cls._SERVER_HOST, cls._SERVER_PORT))
            cls._server_ok = True
            return True
        except OSError:
            cls._server_ok        = False
            cls._server_fail_time = _time.monotonic()
            return False

    @classmethod
    def _server_tokenize(cls, text: str) -> list[int] | None:
        import json as _json, socket as _sock
        try:
            payload = (_json.dumps({"tokenize": text}) + "\n").encode("utf-8")
            with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
                s.settimeout(5.0)
                s.connect((cls._SERVER_HOST, cls._SERVER_PORT))
                s.sendall(payload)
                data = bytearray()
                while True:
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if data.endswith(b"\n"):
                        break
            resp = _json.loads(data.decode("utf-8").strip())
            return None if resp.get("error") else resp.get("tokens")
        except Exception:
            cls._server_ok        = False
            cls._server_fail_time = __import__("time").monotonic()
            return None

    @classmethod
    def _server_detokenize(cls, tokens: list[int]) -> str | None:
        import json as _json, socket as _sock
        try:
            payload = (_json.dumps({"detokenize": tokens}) + "\n").encode("utf-8")
            with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
                s.settimeout(5.0)
                s.connect((cls._SERVER_HOST, cls._SERVER_PORT))
                s.sendall(payload)
                data = bytearray()
                while True:
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if data.endswith(b"\n"):
                        break
            resp = _json.loads(data.decode("utf-8").strip())
            return None if resp.get("error") else resp.get("text")
        except Exception:
            cls._server_ok        = False
            cls._server_fail_time = __import__("time").monotonic()
            return None

    @classmethod
    def get_gguf_path(cls) -> str:
        env = os.environ.get(_GGUF_PATH_ENV)
        if env and os.path.exists(env):
            return env
        if os.path.exists(_DEFAULT_GGUF):
            return _DEFAULT_GGUF
        raise FileNotFoundError(f"GGUF não encontrado. Defina {_GGUF_PATH_ENV} apontando para o arquivo .gguf")

    @classmethod
    def get_vocab(cls):
        if cls._llm_vocab is None:
            with cls._lock:
                if cls._llm_vocab is None:
                    try:
                        from llama_cpp import Llama
                    except Exception:
                        logger.exception("llama_cpp import falhou")
                        raise
                    gguf = cls.get_gguf_path()
                    logger.debug("Carregando vocab_only do GGUF: %s", gguf)
                    cls._llm_vocab = Llama(model_path=gguf, vocab_only=True, verbose=False)
        return cls._llm_vocab

    @classmethod
    def text_to_bytes(cls, text: str) -> bytes:
        if cls._server_available():
            tokens = cls._server_tokenize(text)
            if tokens is not None:
                return array.array("i", tokens).tobytes()
        vocab  = cls.get_vocab()
        tokens = vocab.tokenize(text.encode("utf-8"), add_bos=False)
        return array.array("i", tokens).tobytes()

    @classmethod
    def bytes_to_text(cls, data: bytes) -> str:
        if not data:
            return ""
        if len(data) % 4 != 0:
            try:
                return data.decode("utf-8", errors="ignore")
            except Exception:
                return ""
        try:
            arr    = array.array("i")
            arr.frombytes(data)
            tokens = arr.tolist()
            if cls._server_available():
                result = cls._server_detokenize(tokens)
                if result is not None:
                    return result
            vocab = cls.get_vocab()
            if tokens and (max(tokens) >= vocab.n_vocab() or min(tokens) < 0):
                return data.decode("utf-8", errors="ignore")
            return vocab.detokenize(tokens).decode("utf-8", errors="ignore")
        except Exception:
            return data.decode("utf-8", errors="ignore")


# ===========================================================================
# § LocalIndexCache (inalterado)
# ===========================================================================

class LocalIndexCache:
    """Mantém conexões SQLite e leitores de índice invertido vivos na RAM."""

    _cache: dict = {}
    _lock  = Lock()

    @classmethod
    def get(cls, source_id: str) -> Tuple[Optional[sqlite3.Connection], Optional[InvertedIndexSearcher]]:
        with cls._lock:
            if source_id not in cls._cache:
                db_path = _source_id_to_db(source_id)
                inv_dir = INDEX_DIR / source_id
                con     = None
                searcher = None
                if db_path.exists():
                    try:
                        con = sqlite3.connect(str(db_path), check_same_thread=False)
                        con.execute("PRAGMA query_only=1")
                        con.execute("PRAGMA cache_size=-64000")
                    except Exception:
                        logger.error("Erro ao abrir SQLite cache para %s", source_id, exc_info=True)
                if inv_dir.exists():
                    try:
                        searcher = InvertedIndexSearcher(inv_dir)
                    except Exception:
                        logger.error("Erro ao abrir InvertedIndex cache para %s", source_id, exc_info=True)
                cls._cache[source_id] = (con, searcher)
            return cls._cache[source_id]

    @classmethod
    def evict(cls, source_id: str) -> None:
        with cls._lock:
            if source_id not in cls._cache:
                return
            con, searcher = cls._cache.pop(source_id)
            for obj in (con, searcher):
                if obj:
                    try:
                        obj.close()
                    except Exception as e:
                        logger.error("[INFRA] evict: %s", e)

    @classmethod
    def preload(cls, source_ids: List[str] = None) -> None:
        logger.info("[CACHE] Pré-carregando GGUF Vocab na RAM...")
        TokenizerBridge.get_vocab()
        for sid in (source_ids or []):
            logger.info("[CACHE] Pré-carregando DB/InvertedIndex para: %s", sid)
            cls.get(sid)


# ===========================================================================
# § LocalResult
# ===========================================================================

class LocalResult:
    __slots__ = ("source", "title", "body", "path")

    def __init__(self, source: str, title: str, body: str, path: str = "") -> None:
        self.source = source
        self.title  = title
        self.body   = body
        self.path   = path

    @property
    def ok(self) -> bool:
        return bool(self.title and self.body.strip())

    def get_snippet(self, query: str = "", max_chars: int = 1200, n_snippets: int = 3) -> str:
        if not self.ok:
            return ""
        text = self.body
        q    = (query or "").strip()
        if q:
            positions = _find_term_positions(text, q)
            if positions:
                return _build_snippet_from_positions(text, positions, q, max_chars, n_snippets)
        return _leading_snippet(text, max_chars)

    def to_prompt_block(self, max_chars: int = 600, query: str = "") -> str:
        if not self.ok:
            return ""
        snippet = self.get_snippet(query, max_chars)
        return f"[CTX-BEGIN]\nscope: {self.source} | {self.title}\n{snippet}\n[CTX-END]\n"


# ---------------------------------------------------------------------------
# Helpers de snippet
# ---------------------------------------------------------------------------

def _find_term_positions(text: str, q: str) -> list[int]:
    qlower = q.lower()
    words  = re.findall(r"[A-Za-z0-9_]{2,}", qlower)
    positions: list[int] = []
    if words:
        for w in words:
            start = 0
            while True:
                idx = text.lower().find(w, start)
                if idx == -1:
                    break
                positions.append(idx)
                start = idx + len(w)
    else:
        idx = text.lower().find(qlower)
        if idx != -1:
            positions.append(idx)
    return sorted(set(positions))


def _safe_extend_right(text: str, right: int) -> int:
    for open_tag, close_tag in (("[CODE-BEGIN", "[CODE-END]"), ("[MATH-BEGIN", "[MATH-END]")):
        if text.rfind(open_tag, 0, right) > text.rfind(close_tag, 0, right):
            end = text.find(close_tag, right)
            if end != -1:
                right = max(right, end + len(close_tag))
    return right


def _highlight_words(part: str, words: list[str]) -> str:
    skip = {"code", "begin", "end", "math"}
    for w in words:
        if w.upper() in skip:
            continue
        try:
            part = re.sub(rf"(?i)\b{re.escape(w)}\b", lambda m: f"**{m.group(0)}**", part)
        except Exception:
            pass
    return part


def _build_snippet_from_positions(
    text: str, positions: list[int], q: str, max_chars: int, n_snippets: int
) -> str:
    words   = re.findall(r"[A-Za-z0-9_]{2,}", q.lower())
    windows: list[tuple[int, int]] = []
    for pos in positions:
        if len(windows) >= n_snippets:
            break
        left  = max(0, pos - 120)
        right = min(len(text), pos + 420)
        if windows and left < windows[-1][1]:
            left = windows[-1][1] + 1
        windows.append((left, _safe_extend_right(text, right)))

    parts: list[str] = []
    total = 0
    for left, right in windows:
        part = _highlight_words(text[left:right], words)
        if left  > 0:          part = "..." + part
        if right < len(text):  part = part  + "..."
        parts.append(part)
        total += len(part)
        if total >= max_chars:
            break
    return "\n\n".join(parts)


def _leading_snippet(text: str, max_chars: int) -> str:
    end     = _safe_extend_right(text, max_chars)
    if end > max_chars * 3:
        end = max_chars
    leading = text[:end].strip()
    if len(leading) < len(text):
        leading += "..."
    return leading


# ===========================================================================
# § Path helpers
# ===========================================================================

def _zim_to_source_id(zim_path: str | Path) -> str:
    name = Path(zim_path).stem.replace("-", "_").replace(".", "_")
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return re.sub(r"_+", "_", name).strip("_").lower()


def _source_id_to_db(source_id: str) -> Path:
    return INDEX_DIR / f"{source_id}.db"


def _find_zim_for_source(source_id: str) -> Optional[Path]:
    if ZIM_DIR.exists():
        for zim in ZIM_DIR.glob("*.zim"):
            if _zim_to_source_id(zim) == source_id:
                return zim
    return None


# ===========================================================================
# § Read entry content
# ===========================================================================

def _read_entry_content(entry) -> Optional[bytes]:
    for method in ("read", "get_data", "content", "data"):
        fn = getattr(entry, method, None)
        if fn is None:
            continue
        try:
            result = fn() if callable(fn) else fn
            if isinstance(result, (bytes, bytearray, memoryview)) and len(result) > 0:
                return bytes(result)
        except Exception:
            continue
    for attr in ("_data", "_content", "raw"):
        val = getattr(entry, attr, None)
        if isinstance(val, (bytes, bytearray, memoryview)) and len(val) > 0:
            return bytes(val)
    return None


# ===========================================================================
# § Build index
# ===========================================================================

def _iter_zim_entries(
    zim_path: str,
    verbose: bool = True,
    start_scanned: int = 0,
) -> Iterator[tuple[int, str, str, str]]:
    import pyzim
    p     = Path(zim_path).absolute()
    stats = dict(scanned=0, yielded=0, redirect=0, non_html=0, empty=0, error=0)

    with pyzim.Zim.open(str(p), mode="r") as zim:
        for entry in zim.iter_entries():
            stats["scanned"] += 1
            idx = stats["scanned"]

            if start_scanned and idx <= start_scanned:
                continue
            if verbose and idx % 5000 == 0:
                logger.info("[ZIM] scanned=%d yielded=%d redirect=%d non_html=%d empty=%d",
                    idx, stats["yielded"], stats["redirect"], stats["non_html"], stats["empty"])

            if getattr(entry, "is_redirect", False):
                stats["redirect"] += 1
                continue

            ns = getattr(entry, "namespace", None)
            if ns is not None:
                if isinstance(ns, bytes):
                    ns = ns.decode("utf-8", errors="ignore")
                if str(ns).strip() in ("I", "-", "X"):
                    stats["non_html"] += 1
                    continue

            content_bytes = _read_entry_content(entry)
            if not content_bytes:
                stats["empty"] += 1
                continue

            head = content_bytes[:400].lower()
            if not (b"<html" in head or b"<!doctype" in head or b"<body" in head
                    or b"<p" in head or b"<div" in head or b"<h1" in head
                    or b"<h2" in head or content_bytes[:1] == b"<"):
                stats["non_html"] += 1
                continue

            try:
                title = getattr(entry, "title", "")
                if isinstance(title, bytes):
                    title = title.decode("utf-8", errors="ignore")
                title = str(title).strip()

                path = getattr(entry, "url", None) or getattr(entry, "path", "")
                if isinstance(path, bytes):
                    path = path.decode("utf-8", errors="ignore")
                path = str(path).strip()
                if not title:
                    title = path.split("/")[-1].replace("_", " ").strip()

                stats["yielded"] += 1
                yield idx, title, path, content_bytes.decode("utf-8", errors="replace")
            except Exception:
                stats["error"] += 1
                continue

    if verbose:
        logger.info("[ZIM] total: scanned=%d yielded=%d redirect=%d non_html=%d empty=%d error=%d",
            stats["scanned"], stats["yielded"], stats["redirect"],
            stats["non_html"], stats["empty"], stats["error"])


# ---------------------------------------------------------------------------
# Worker e acumulador de build
# ---------------------------------------------------------------------------

@dataclass
class _EntryResult:
    scanned_idx:    int
    title:          str
    path:           str
    content_hash:   str
    compressed:     bytes
    combined_tokens: list
    title_trigrams: set


def _process_entry(
    scanned_idx: int, title: str, path: str, html: str,
    vocab, max_chars: int,
) -> Optional[_EntryResult]:
    body = _strip_html(html, max_chars=max_chars)
    if len(body.strip()) < 50:
        return None
    try:
        qtoks    = vocab.tokenize(body.encode("utf-8"),  add_bos=False)
        ttoks    = vocab.tokenize(title.encode("utf-8"), add_bos=False)
        body_arr = array.array("i", qtoks)
        payload  = body_arr.tobytes()
        h        = hashlib.md5(payload).hexdigest()
        try:
            combined = ttoks + ttoks + qtoks
        except Exception:
            combined = qtoks
        return _EntryResult(
            scanned_idx=scanned_idx, title=title, path=path,
            content_hash=h, compressed=_compress(payload),
            combined_tokens=combined,
            title_trigrams=_trigrams_for(_normalize_text_for_match(title)),
        )
    except Exception:
        return None


@dataclass
class _BuildAccumulator:
    seen_hashes:     set   = field(default_factory=set)
    content_pending: dict  = field(default_factory=dict)
    buf_pages:       list  = field(default_factory=list)
    title_trigrams:  list  = field(default_factory=list)
    count:           int   = 0
    deduplicated:    int   = 0
    last_scanned:    int   = 0


def _accumulate_one(
    res: Optional[_EntryResult],
    acc: _BuildAccumulator,
    inv_builder: Optional[InvertedIndexBuilder],
) -> None:
    """Incorpora um único _EntryResult no acumulador. Noop se res é None."""
    if res is None:
        return
    acc.last_scanned = res.scanned_idx
    if res.content_hash not in acc.seen_hashes:
        acc.seen_hashes.add(res.content_hash)
        acc.content_pending[res.content_hash] = res.compressed
    else:
        acc.deduplicated += 1
    acc.count += 1
    acc.buf_pages.append((acc.count, res.title, res.path, res.content_hash))
    for tg in res.title_trigrams:
        acc.title_trigrams.append((tg, acc.count))
    if inv_builder is not None:
        inv_builder.add_document(acc.count, res.combined_tokens)


def _flush_content(con: sqlite3.Connection, acc: _BuildAccumulator) -> None:
    if not acc.content_pending:
        return
    items = list(acc.content_pending.items())
    with orn_span("build.sql_insert", category="index"):
        try:
            con.executemany("INSERT OR IGNORE INTO content_pool (hash, token_blob) VALUES (?, ?)", items)
        except Exception:
            for k, v in items:
                try:
                    con.execute("INSERT OR IGNORE INTO content_pool (hash, token_blob) VALUES (?, ?)", (k, v))
                except Exception:
                    pass
    acc.content_pending.clear()


def _commit_batch(con: sqlite3.Connection, acc: _BuildAccumulator, verbose: bool) -> None:
    if acc.buf_pages:
        con.executemany("INSERT INTO pages (id, title, path, content_hash) VALUES (?,?,?,?)", acc.buf_pages)
    _flush_content(con, acc)
    if acc.title_trigrams:
        con.executemany("INSERT INTO title_trigrams (trigram, doc_id) VALUES (?, ?)", acc.title_trigrams)
        acc.title_trigrams.clear()
    con.execute("INSERT OR REPLACE INTO meta VALUES ('build_scanned_entries', ?)", (str(acc.last_scanned),))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('build_docs_processed',  ?)", (str(acc.count),))
    con.execute("COMMIT")
    con.execute("BEGIN")
    acc.buf_pages.clear()
    if verbose:
        logger.info("[BUILD] ⏳ %d artigos processados e salvos no DB...", acc.count)


def _init_db(con: sqlite3.Connection) -> None:
    con.execute("PRAGMA page_size=4096")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    try:
        con.execute("PRAGMA cache_size = -20000")
    except Exception:
        pass
    con.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY, title TEXT, path TEXT, content_hash TEXT
        )""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS content_pool (
            hash TEXT PRIMARY KEY, token_blob BLOB
        )""")
    con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_pages_hash ON pages(content_hash)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS title_trigrams (
            trigram TEXT, doc_id INTEGER
        )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_title_trigrams_trigram ON title_trigrams(trigram)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_title_trigrams_doc     ON title_trigrams(doc_id)")


@dataclass
class _ResumeState:
    mode:          bool = False
    start_scanned: int  = 0
    start_doc_id:  int  = 0


def _check_resume(db_path: str) -> _ResumeState:
    state = _ResumeState()
    if not Path(db_path).exists():
        return state
    resume_enabled = os.environ.get("SICDOX_RESUME_BUILD", "1").strip().lower() not in ("0", "false", "no")
    if not resume_enabled:
        return state
    try:
        probe = sqlite3.connect(db_path)
        try:
            probe.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            meta = dict(probe.execute("SELECT key, value FROM meta").fetchall())
            if meta.get("build_status") == "in_progress":
                state.mode          = True
                state.start_scanned = int(meta.get("build_scanned_entries", "0") or 0)
                state.start_doc_id  = int(meta.get("build_docs_processed",  "0") or 0)
        finally:
            probe.close()
    except Exception:
        pass
    return state


def _cleanup_stale(db_path: str, inv_dir: Path) -> None:
    db_p = Path(db_path)
    for suf in ("", "-wal", "-shm"):
        f = db_p.with_name(db_p.name + suf)
        try:
            if f.exists():
                f.unlink()
        except Exception:
            pass
    if inv_dir.exists():
        try:
            import shutil
            shutil.rmtree(inv_dir)
        except Exception:
            pass


def _resolve_zim_path(zim_arg: str) -> str:
    """Resolve o argumento ZIM para um caminho absoluto existente.

    Estratégia (em ordem):
      1. Caminho literal — usa direto se existir.
      2. Nome de arquivo dentro de ZIM_DIR — resolve se existir.
      3. Correspondência parcial (case-insensitive) dentro de ZIM_DIR.
      4. Falha com mensagem útil listando os ZIMs disponíveis.
    """
    # 1. Caminho literal
    p = Path(zim_arg)
    if p.exists():
        return str(p)

    # 2. Nome dentro de ZIM_DIR (ex: "wikipedia_pt.zim" → "data/zim/wikipedia_pt.zim")
    if ZIM_DIR.exists():
        candidate = ZIM_DIR / zim_arg
        if candidate.exists():
            return str(candidate)

        # 3. Correspondência parcial sem extensão ou case-insensitive
        zim_lower = zim_arg.lower().removesuffix(".zim")
        matches = [
            z for z in ZIM_DIR.glob("*.zim")
            if zim_lower in z.stem.lower()
        ]
        if len(matches) == 1:
            logger.info("[BUILD] Resolvido '%s' → '%s'", zim_arg, matches[0])
            return str(matches[0])
        if len(matches) > 1:
            names = ", ".join(m.name for m in matches)
            raise FileNotFoundError(
                f"Ambíguo: '{zim_arg}' corresponde a múltiplos ZIMs: {names}\n"
                f"Use o nome completo."
            )

    # 4. Falha com lista de disponíveis
    available = sorted(z.name for z in ZIM_DIR.glob("*.zim")) if ZIM_DIR.exists() else []
    hint = ""
    if available:
        hint = "\n\nZIMs disponíveis em " + str(ZIM_DIR) + ":\n"
        hint += "\n".join(f"  orn index build {n}" for n in available)
    raise FileNotFoundError(f"ZIM não encontrado: '{zim_arg}'{hint}")


def build_index(
    zim_path: str,
    source_id: Optional[str] = None,
    batch_size: int = 200,
    verbose: bool = True,
) -> Path:
    """Constrói (ou retoma) o índice SQLite a partir de um arquivo ZIM.

    Estratégia de memória:
      - Sliding window de futures com janela = workers × 2.
        Nunca mais de N entradas HTML simultâneas na heap.
      - Commit a cada `batch_size` artigos processados (checkpoint).
        Interrupção → retomada de onde parou, sem perder progresso.
      - gc.collect() após cada commit para liberar RAM imediatamente.
      - workers = min(2, cpu_count): N2808 é dual-core; mais threads
        só aumentam contenção de memória e GIL sem ganho real.

    Variáveis de ambiente:
      SICDOX_WORKERS        — número de threads (padrão: min(2, cpu_count))
      SICDOX_MAX_CHARS      — chars máximos de HTML por artigo (padrão: 64000)
      SICDOX_CONTENT_BATCH  — flush de content_pool a cada N itens (padrão: 64)
      SICDOX_BUILD_INVERTED — "1" para construir índice invertido (padrão: off)
      SICDOX_RESUME_BUILD   — "0" para forçar rebuild mesmo se DB existe

    Args:
        zim_path:   Caminho para o arquivo .zim.
        source_id:  Identificador do índice (derivado do nome do ZIM se None).
        batch_size: Artigos por checkpoint de commit (padrão: 200).
        verbose:    Emite logs de progresso.

    Returns:
        Path para o arquivo .db gerado.
    """
    import gc

    try:
        import pyzim  # noqa: F401
    except ImportError:
        raise ImportError("pyzim não instalado. Execute: pip install pyzim")

    zim_path = _resolve_zim_path(str(zim_path))

    vocab = TokenizerBridge.get_vocab()

    if source_id is None:
        source_id = _zim_to_source_id(zim_path)

    LocalIndexCache.evict(source_id)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    db_path = str(_source_id_to_db(source_id))
    inv_dir = INDEX_DIR / source_id

    # Configuração via env — valores conservadores por padrão para N2808
    cpu_count      = os.cpu_count() or 2
    workers        = int(os.environ.get("SICDOX_WORKERS",        str(min(2, cpu_count))))
    max_chars      = int(os.environ.get("SICDOX_MAX_CHARS",      "64000"))
    content_batch  = int(os.environ.get("SICDOX_CONTENT_BATCH",  "64"))
    build_inverted = os.environ.get("SICDOX_BUILD_INVERTED", "0").strip().lower() not in ("0", "false", "no")

    # Janela máxima de futures vivos simultaneamente — limita RAM
    max_inflight = workers * 2

    resume = _check_resume(db_path)
    if Path(db_path).exists() and not resume.mode:
        logger.info("[BUILD] DB existente, removendo para rebuild: %s", db_path)
        _cleanup_stale(db_path, inv_dir)

    if verbose:
        if resume.mode:
            logger.info(
                "[BUILD] Retomando build... DB=%s start_scanned=%d start_doc=%d",
                db_path, resume.start_scanned, resume.start_doc_id,
            )
        else:
            logger.info(
                "[BUILD] Iniciando build... DB=%s workers=%d max_inflight=%d batch=%d",
                db_path, workers, max_inflight, batch_size,
            )

    inv_builder: Optional[InvertedIndexBuilder] = InvertedIndexBuilder() if build_inverted else None
    acc = _BuildAccumulator(count=resume.start_doc_id, last_scanned=resume.start_scanned)
    t0  = time.monotonic()

    con = sqlite3.connect(db_path, isolation_level=None)
    try:
        _init_db(con)
        con.execute("BEGIN")
        con.execute("INSERT OR REPLACE INTO meta VALUES ('build_status', 'in_progress')")
        con.execute("INSERT OR REPLACE INTO meta VALUES ('build_scanned_entries', ?)", (str(resume.start_scanned),))
        con.execute("INSERT OR REPLACE INTO meta VALUES ('build_docs_processed',  ?)", (str(resume.start_doc_id),))

        # ── Sliding window de futures ─────────────────────────────────
        # Invariante: len(inflight) <= max_inflight a qualquer momento.
        # Cada future segura UMA entrada HTML na heap até ser drenado.
        # Quando a janela está cheia, bloqueia no future mais antigo
        # antes de submeter o próximo → pressão de memória constante.
        from collections import deque
        inflight: deque = deque()

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for scanned_idx, title, path, html in _iter_zim_entries(
                zim_path, verbose=verbose, start_scanned=resume.start_scanned
            ):
                # Enfileira novo trabalho
                inflight.append(
                    pool.submit(_process_entry, scanned_idx, title, path, html, vocab, max_chars)
                )

                # Drena o mais antigo quando a janela está cheia
                while len(inflight) >= max_inflight:
                    res = inflight.popleft().result()
                    _accumulate_one(res, acc, inv_builder)

                    # Checkpoint a cada batch_size artigos
                    if acc.count > 0 and acc.count % batch_size == 0:
                        if len(acc.content_pending) > 0:
                            _flush_content(con, acc)
                        _commit_batch(con, acc, verbose)
                        gc.collect()

            # Drena o restante da janela ao terminar o ZIM
            while inflight:
                res = inflight.popleft().result()
                _accumulate_one(res, acc, inv_builder)

        if verbose:
            logger.info("[BUILD] ZIM extraído. Salvando registros finais...")

        # Commit final
        if acc.buf_pages:
            con.executemany(
                "INSERT INTO pages (id, title, path, content_hash) VALUES (?,?,?,?)",
                acc.buf_pages,
            )
        _flush_content(con, acc)
        if acc.title_trigrams:
            con.executemany(
                "INSERT INTO title_trigrams (trigram, doc_id) VALUES (?, ?)",
                acc.title_trigrams,
            )

        con.execute("INSERT OR REPLACE INTO meta VALUES ('build_scanned_entries', ?)", (str(acc.last_scanned),))
        con.execute("INSERT OR REPLACE INTO meta VALUES ('build_docs_processed',  ?)", (str(acc.count),))
        con.execute("INSERT OR REPLACE INTO meta VALUES ('build_status', 'completed')")
        con.execute("COMMIT")

    except Exception:
        logger.exception("Erro durante build_index; rollback")
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()

    if build_inverted and inv_builder is not None:
        if verbose:
            logger.info("[BUILD] Escrevendo índice invertido: %s", inv_dir)
        inv_builder.write(inv_dir)

    if verbose:
        logger.info(
            "[BUILD] ✅ CONCLUÍDO: %d artigos (dedup: %d) em %.1fs",
            acc.count, acc.deduplicated, time.monotonic() - t0,
        )

    return Path(db_path)


# ===========================================================================
# § Search
# ===========================================================================

def _simple_query_tokens(text: str) -> list[int]:
    return [
        int(hashlib.md5(w.encode("utf-8")).hexdigest()[:8], 16) & 0x7FFFFFFF
        for w in re.findall(r"[A-Za-z0-9_]+|[^\w\s]", text)
    ]


def _fuzzy_title_search(
    con: sqlite3.Connection, query: str,
    candidate_limit: int = 30, final_limit: int = 10,
) -> list[int]:
    qnorm = _normalize_text_for_match(query)
    trigs = list(_trigrams_for(qnorm))
    if not trigs:
        return []
    ph   = ",".join("?" * len(trigs))
    rows = con.execute(
        f"SELECT doc_id, COUNT(*) AS cnt FROM title_trigrams "
        f"WHERE trigram IN ({ph}) GROUP BY doc_id ORDER BY cnt DESC LIMIT ?",
        (*trigs, candidate_limit),
    ).fetchall()
    if not rows:
        return []
    doc_ids   = [r[0] for r in rows]
    ph2       = ",".join("?" * len(doc_ids))
    title_map = {r[0]: r[1] for r in con.execute(
        f"SELECT id, title FROM pages WHERE id IN ({ph2})", doc_ids
    ).fetchall()}

    scored = []
    for doc_id in doc_ids:
        tnorm = _normalize_text_for_match(title_map.get(doc_id, ""))
        score = _similarity_ratio(qnorm, tnorm)
        if tnorm == qnorm:           score += 0.6
        elif tnorm.startswith(qnorm): score += 0.35
        scored.append((doc_id, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [doc_id for doc_id, _ in scored[:final_limit]]


def _harvest_candidates(
    con: sqlite3.Connection, searcher, q_raw: str, code_only: bool,
) -> tuple[list[int], set[int]]:
    candidates:   list[int] = []
    inverted_ids: set[int]  = set()

    if searcher:
        try:
            if os.environ.get("SICDOX_FAST_MODE", "").strip().lower() not in ("", "0", "false", "no"):
                qtoks = _simple_query_tokens(q_raw)
            else:
                qtoks = TokenizerBridge.get_vocab().tokenize(q_raw.encode("utf-8"), add_bos=False)
            body_ids = searcher.search(qtoks, limit=120 if code_only else 80) or []
            candidates.extend(body_ids)
            inverted_ids = set(body_ids)
        except Exception:
            pass

    q_esc = _like_escape(q_raw)
    try:
        rows = con.execute(
            "SELECT p.id FROM pages p "
            "WHERE p.title = ? OR p.title LIKE ? ESCAPE '\\' OR p.title LIKE ? ESCAPE '\\' LIMIT 80",
            (q_raw, f"{q_esc}%", f"%{q_esc}%"),
        ).fetchall()
        title_ids = [r[0] for r in rows]
    except Exception:
        title_ids = []

    if not title_ids:
        try:
            title_ids = _fuzzy_title_search(con, q_raw, candidate_limit=200, final_limit=60)
        except Exception:
            title_ids = []

    for tid in title_ids:
        if tid not in candidates:
            candidates.append(tid)

    return candidates, inverted_ids


@dataclass
class _DecodedBody:
    tokens:    Optional[list]
    body_text: str


def _decode_blob(blob: bytes, title: str) -> _DecodedBody:
    try:
        raw      = _decompress(blob)
        arr      = array.array("i")
        arr.frombytes(raw)
        tokens    = arr.tolist()
        body_text = TokenizerBridge.bytes_to_text(raw)
        body_text = _clean_body(body_text, max_chars=100_000)
        if body_text.lower().startswith(title.lower()):
            body_text = re.sub(rf"^{re.escape(title)}\s*", "", body_text, flags=re.IGNORECASE).lstrip()
        return _DecodedBody(tokens=tokens, body_text=body_text)
    except Exception:
        try:
            return _DecodedBody(tokens=None, body_text=TokenizerBridge.bytes_to_text(_decompress(blob)))
        except Exception:
            return _DecodedBody(tokens=None, body_text="")


def _title_boost(qnorm: str, title: str) -> float:
    tnorm = _normalize_text_for_match(title)
    if tnorm == qnorm:             return 3.0
    if tnorm.startswith(qnorm):   return 1.8
    return 0.9 * _similarity_ratio(qnorm, tnorm)


def _score_candidate(
    decoded: _DecodedBody, title: str,
    qnorm: str, q_raw: str, qwords: list[str],
    qtoken_set: set[int], code_only: bool, formula_like: bool,
) -> Optional[float]:
    tokens    = decoded.tokens
    body_text = decoded.body_text
    dl        = max(1, len(tokens) if tokens is not None else max(1, len(body_text.split())))

    if code_only:
        passed, tf, matched, total = _score_code_only_match(body_text, q_raw, qwords)
        if not passed:
            return None
        early_tf  = tf + (8.0 if total > 0 and matched == total else 0.0)
        positions = []
    else:
        if tokens is not None:
            positions  = [i for i, tok in enumerate(tokens) if tok in qtoken_set]
            tf         = float(len(positions))
            early_win  = min(200, max(20, dl // 8))
            early_tf   = float(sum(1 for p in positions if p < early_win))
        else:
            tf        = float(sum(body_text.lower().count(w) for w in qwords if w))
            early_tf  = float(sum(body_text[:400].lower().count(w) for w in qwords if w))
            positions = []

    w          = _SCORE_WEIGHTS_CODE if code_only else _SCORE_WEIGHTS_NORMAL
    tb         = _title_boost(qnorm, title)
    density    = tf / dl
    early_den  = early_tf / dl
    front_bon  = 1.0 if early_tf > 0 and positions and min(positions) < max(10, dl // 20) else 0.0

    score = (
        w["title_boost"]   * tb
        + w["early_density"] * early_den
        + w["density"]       * density
        + w["tf"]            * tf
        + w["front_bonus"]   * front_bon
    )
    if not code_only and formula_like and body_text:
        if q_raw in body_text:             score += 6.0
        elif q_raw.lower() in body_text.lower(): score += 2.0

    return score


def _assemble_result(
    label: str, title: str, path: str, body_text: str, code_only: bool,
) -> LocalResult:
    body = body_text or ""
    if code_only:
        code_body = _format_code_only_body(body)
        if code_body:
            body = code_body
    body = re.sub(r"\n\s*\n", "\n\n", body).strip()
    body = re.sub(rf"^\s*{re.escape(title)}\s*[:\-\|]?\s*(\r?\n)+", "", body, flags=re.IGNORECASE)
    body = re.sub(r"\n{3,}", "\n\n", body).lstrip()
    return LocalResult(label, title, body, path)


def search_local(
    query: str, source_id: str, limit: int = 3, code_only: bool = False,
) -> List[LocalResult]:
    if not query.strip():
        return []

    s = source_id.replace("-", "_").replace(".", "_")
    source_id = re.sub(r"_+", "_", re.sub(r"[^a-zA-Z0-9_]", "_", s)).strip("_").lower()
    label     = f"{source_id}-local"

    try:
        con, searcher = LocalIndexCache.get(source_id)
        if not con:
            return []

        q_raw  = query.strip()
        qnorm  = _normalize_text_for_match(q_raw)
        qwords = re.findall(r"[A-Za-z0-9_]+", q_raw.lower())

        # Fase 1: exact title match
        if not code_only:
            try:
                row = con.execute(
                    "SELECT p.id, p.title, p.path, c.token_blob "
                    "FROM pages p JOIN content_pool c ON p.content_hash = c.hash "
                    "WHERE LOWER(p.title) = ? LIMIT 1",
                    (qnorm,),
                ).fetchone()
                if row:
                    _, title, path, blob = row
                    decoded = _decode_blob(blob, title)
                    return [LocalResult(label, title, decoded.body_text, path)]
            except Exception:
                pass

        formula_like = bool(re.search(r"[A-Za-z].*\d|\d", q_raw)) and len(q_raw) <= 12

        # Fase 2: coleta de candidatos
        candidates, inverted_ids = _harvest_candidates(con, searcher, q_raw, code_only)
        if not candidates:
            return []

        ph   = ",".join("?" * len(candidates))
        rows = con.execute(
            f"SELECT p.id, p.title, p.path, c.token_blob "
            f"FROM pages p JOIN content_pool c ON p.content_hash = c.hash "
            f"WHERE p.id IN ({ph})",
            candidates,
        ).fetchall()
        row_map = {r[0]: r for r in rows}

        try:
            qtoks = TokenizerBridge.get_vocab().tokenize(q_raw.encode("utf-8"), add_bos=False)
        except Exception:
            qtoks = _simple_query_tokens(q_raw)
        qtoken_set = {int(t) for t in qtoks}

        # Fase 3: scoring
        scored: list[tuple] = []
        for cid in candidates:
            r = row_map.get(cid)
            if not r:
                continue
            doc_id, title, path, blob = r
            decoded = _decode_blob(blob, title)
            score   = _score_candidate(decoded, title, qnorm, q_raw, qwords, qtoken_set, code_only, formula_like)
            if score is None:
                continue
            if cid in inverted_ids:
                score *= 1.03
            scored.append((doc_id, score, title, path, decoded.body_text))

        scored.sort(key=lambda x: x[1], reverse=True)

        # Fase 4: montagem
        return [
            _assemble_result(label, title, path, body_text, code_only)
            for _, _, title, path, body_text in scored[:limit]
        ]

    except Exception:
        logger.exception("search_local failed for source_id=%s", source_id)
        return []


# ===========================================================================
# § Info / listagem
# ===========================================================================

def index_info(source_id: str) -> dict:
    db_path = _source_id_to_db(source_id)
    zim     = _find_zim_for_source(source_id)
    info    = {
        "source_id": source_id, "exists": False, "articles": 0,
        "mode": "Aguardando Build", "zim_path": str(zim) if zim else "?",
    }
    if db_path.exists():
        try:
            con = sqlite3.connect(str(db_path))
            info["articles"] = con.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
            info["exists"] = True
            info["mode"]   = "SiCDox (Tokenized)" if meta.get("sicdox_ver") else "Texto Puro"
            con.close()
        except Exception:
            pass
    return info


def list_indexes() -> List[dict]:
    seen:   set[str]   = set()
    result: List[dict] = []
    if INDEX_DIR.exists():
        for db_file in sorted(INDEX_DIR.glob("*.db")):
            sid = db_file.stem
            seen.add(sid)
            result.append(index_info(sid))
    if ZIM_DIR.exists():
        for zim_file in sorted(ZIM_DIR.glob("*.zim")):
            sid = _zim_to_source_id(zim_file)
            if sid not in seen:
                result.append({
                    "source_id": sid, "articles": 0, "zim_path": str(zim_file),
                    "mode": "Aguardando Build", "exists": False,
                })
                seen.add(sid)
    return result


# ===========================================================================
# § ZIM probe / diagnose (inalterado)
# ===========================================================================

def _read_zim_header(zim_path: str) -> dict:
    with open(zim_path, "rb") as f:
        raw = f.read(_ZIM_HEADER_SIZE)
    if len(raw) < _ZIM_HEADER_SIZE:
        raise ValueError(f"Arquivo muito pequeno ({len(raw)} bytes)")
    magic, major, minor = struct.unpack_from("<IHH", raw, 0)
    if magic != _ZIM_MAGIC:
        raise ValueError(f"Magic inválido: 0x{magic:08X}")
    entry_count, cluster_count = struct.unpack_from("<II", raw, 24)
    return {
        "version":       f"{major}.{minor}",
        "uuid":          raw[8:24].hex(),
        "entry_count":   entry_count,
        "cluster_count": cluster_count,
    }


def probe_zim(zim_path: str) -> None:
    try:
        info    = _read_zim_header(zim_path)
        size_mb = round(Path(zim_path).stat().st_size / 1_048_576, 1)
        print(f"\n  [PROBE] {Path(zim_path).name}")
        print(f"  Versão ZIM:    {info['version']}")
        print(f"  Entradas:      {info['entry_count']:,}")
        print(f"  Clusters:      {info['cluster_count']:,}")
        print(f"  UUID:          {info['uuid']}")
        print(f"  Tamanho:       {size_mb} MB")
    except Exception as e:
        print(f"[PROBE] FALHOU: {e}")


def diagnose_zim(zim_path: str, n: int = 20) -> None:
    try:
        import pyzim
    except ImportError:
        print("  pyzim não instalado.")
        return

    print(f"\n[DIAGNOSE] {Path(zim_path).name} — primeiras {n} entradas")
    print(f"  {'#':<4} {'redirect':<10} {'namespace':<12} {'mime':<30} {'content_bytes':<14} {'title'}")
    print(f"  {'-' * 100}")

    with pyzim.Zim.open(str(Path(zim_path).absolute()), mode="r") as zim:
        for i, entry in enumerate(zim.iter_entries()):
            if i >= n:
                break
            is_redir = getattr(entry, "is_redirect", "?")
            ns = getattr(entry, "namespace", "?")
            if isinstance(ns, bytes):
                ns = ns.decode("utf-8", errors="ignore")
            mime = getattr(entry, "mimetype", None) or getattr(entry, "mime_type", "?")
            if callable(mime):
                mime = mime()
            if isinstance(mime, bytes):
                mime = mime.decode("utf-8", errors="ignore")
            title = getattr(entry, "title", "?")
            if isinstance(title, bytes):
                title = title.decode("utf-8", errors="ignore")
            content = _read_entry_content(entry)
            clen    = len(content) if content else 0
            print(f"  {i:<4} {str(is_redir):<10} {str(ns):<12} {str(mime)[:28]:<30} {clen:<14} {str(title)[:40]}")
    print()


# ===========================================================================
# § CLI (inalterado)
# ===========================================================================

def _cli_main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="local_index",
        description="ORN LocalIndex v6.0 — SiCDox (Semantic Compression)",
    )
    parser.add_argument("--gguf",    help="Caminho para o arquivo .gguf (sobe para SICDOX_GGUF)")
    parser.add_argument("--verbose", action="store_true", help="Ativa modo verboso")

    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("probe", help="Ler header do zim")

    b = sub.add_parser("build", help="Construir índice tokenizado")
    b.add_argument("zim", help="Caminho do arquivo .zim")
    b.add_argument("source_id", nargs="?", help="Source ID opcional")

    s = sub.add_parser("search", help="Buscar no índice local")
    s.add_argument("source_id", help="Source ID")
    s.add_argument("--code-only", action="store_true")
    s.add_argument("query", nargs="+")

    i = sub.add_parser("info", help="Informação do índice")
    i.add_argument("source_id")
    sub.add_parser("list", help="Listar índices e ZIMs disponíveis")
    sub.add_parser("diagnose", help="Diagnose ZIM").add_argument("zim", nargs=1)

    p = sub.add_parser("preload", help="Testa carregamento do vocab e index na RAM")
    p.add_argument("source_id", nargs="?")

    args = parser.parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    if args.gguf:
        os.environ[_GGUF_PATH_ENV] = args.gguf

    chronos_recorder = None
    try:
        from doxoade.chronos import chronos_recorder

        class FakeCommand:
            name = f"INDEX-{args.cmd.upper() if args.cmd else 'NONE'}"

        class FakeCtx:
            invoked_subcommand = None
            command = FakeCommand()
            obj = {}

        chronos_recorder.start_command(FakeCtx())
    except Exception:
        pass

    exit_code    = 0
    t_start      = time.perf_counter()

    try:
        if args.cmd == "probe":
            probe_zim(args.zim)
        elif args.cmd == "build":
            build_index(args.zim, source_id=getattr(args, "source_id", None))
            try:
                GLOBAL_TELEMETRY.flush_json("telemetry/local_index_build.json")
            except Exception:
                pass
        elif args.cmd == "search":
            q       = " ".join(args.query or [])
            results = search_local(q, args.source_id, code_only=getattr(args, "code_only", False))
            elapsed = round((time.perf_counter() - t_start) * 1000, 2)
            if not results:
                print("\n  Nenhum resultado para a busca.")
            else:
                max_chars = int(os.environ.get("SICDOX_SNIPPET_CHARS", "2000"))
                n_snips   = int(os.environ.get("SICDOX_SNIPPETS",      "3"))
                for r in results:
                    snippet  = r.get_snippet(q, max_chars=max_chars, n_snippets=n_snips)
                    rendered = _format_snippet_for_terminal(snippet)
                    print(f"\n  [{r.source}] {r.title}\n{rendered}\n  path: {r.path}")
            print(f"\n  Tempo: {elapsed}ms | {len(results)} resultado(s)")
        elif args.cmd == "info":
            for k, v in index_info(args.source_id).items():
                print(f"  {k:<12}: {v}")
        elif args.cmd == "list":
            for info in list_indexes():
                print(f"  {info['source_id']:<45} {info.get('articles', 0):>8}  {info.get('mode', '?')}")
        elif args.cmd == "diagnose":
            diagnose_zim(args.zim[0], n=20)
        elif args.cmd == "preload":
            LocalIndexCache.preload([args.source_id] if args.source_id else [])
            elapsed = round((time.perf_counter() - t_start) * 1000, 2)
            print(f"\n[OK] Vocab e banco(s) montados na RAM em {elapsed}ms!")
        else:
            parser.print_help()

    except Exception:
        exit_code = 1
        raise
    finally:
        if chronos_recorder:
            try:
                chronos_recorder.end_command(exit_code, (time.perf_counter() - t_start) * 1000)
            except Exception:
                pass

    return exit_code


if __name__ == "__main__":
    raise SystemExit(_cli_main())