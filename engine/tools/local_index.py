from __future__ import annotations

# --- DOXOADE_VULCAN_BOOTSTRAP:START ---
from pathlib import Path as _doxo_path
import importlib.util as _doxo_importlib_util
import sys as _doxo_sys
import time as _doxo_time

_doxo_activate_vulcan = None
_doxo_install_meta_finder = None
_doxo_probe_embedded = None
_doxo_project_root = None
_doxo_boot_t0 = _doxo_time.monotonic()
_doxo_install_ms = 0
_doxo_embedded_ms = 0
_doxo_fallback_ms = 0

for _doxo_base in[_doxo_path(__file__).resolve(), *_doxo_path(__file__).resolve().parents]:
    _doxo_runtime_file = _doxo_base / ".doxoade" / "vulcan" / "runtime.py"
    if not _doxo_runtime_file.exists():
        continue
    _doxo_spec = _doxo_importlib_util.spec_from_file_location("_doxoade_vulcan_runtime", str(_doxo_runtime_file))
    if not (_doxo_spec and _doxo_spec.loader):
        continue
    _doxo_mod = _doxo_importlib_util.module_from_spec(_doxo_spec)
    _doxo_sys.modules["_doxoade_vulcan_runtime"] = _doxo_mod
    _doxo_spec.loader.exec_module(_doxo_mod)
    _doxo_activate_vulcan = getattr(_doxo_mod, "activate_vulcan", None)
    _doxo_install_meta_finder = getattr(_doxo_mod, "install_meta_finder", None)
    _doxo_probe_embedded = getattr(_doxo_mod, "probe_embedded", None)
    _doxo_project_root = str(_doxo_base)
    break

# 1. Instala MetaFinder primeiro
if callable(_doxo_install_meta_finder) and _doxo_project_root:
    _doxo_t = _doxo_time.monotonic()
    try:
        _doxo_install_meta_finder(_doxo_project_root)
    except Exception:
        pass
    finally:
        _doxo_install_ms = int((_doxo_time.monotonic() - _doxo_t) * 1000)

# 2. Tenta usar o loader "embedded"
try:
    _doxo_t = _doxo_time.monotonic()
    if _doxo_project_root:
        _embedded_path = _doxo_path(_doxo_project_root) / ".doxoade" / "vulcan" / "vulcan_embedded.py"
        if _embedded_path.exists():
            _doxo_spec2 = _doxo_importlib_util.spec_from_file_location("_doxoade_vulcan_embedded", str(_embedded_path))
            if _doxo_spec2 and _doxo_spec2.loader:
                _doxo_mod2 = _doxo_importlib_util.module_from_spec(_doxo_spec2)
                _doxo_sys.modules["_doxoade_vulcan_embedded"] = _doxo_mod2
                _doxo_spec2.loader.exec_module(_doxo_mod2)
                _doxo_activate_embedded = getattr(_doxo_mod2, "activate_embedded", None)
                _doxo_safe_call = getattr(_doxo_mod2, "safe_call", None)
                if callable(_doxo_activate_embedded):
                    try:
                        _doxo_activate_embedded(globals(), __file__, _doxo_project_root)
                    except Exception:
                        pass
                if callable(_doxo_safe_call):
                    try:
                        import sys as _d_sys
                        _bin_dir = _doxo_path(_doxo_project_root) / ".doxoade" / "vulcan" / "bin"
                        _vulcan_suffix = _d_sys.intern("_vulcan_optimized")
                        _suffix_len    = len(_vulcan_suffix)
                        for mname, mod in list(_d_sys.modules.items()):
                            try:
                                mfile = getattr(mod, "__file__", None)
                                if not mfile:
                                    continue
                                mpath = _doxo_path(mfile)
                                if _bin_dir not in mpath.parents:
                                    continue
                                for attr in dir(mod):
                                    if not attr.endswith(_vulcan_suffix):
                                        continue
                                    native_obj = getattr(mod, attr, None)
                                    if not callable(native_obj):
                                        continue
                                    base = attr[: -_suffix_len]
                                    try:
                                        setattr(mod, base, _doxo_safe_call(native_obj, getattr(mod, base, None)))
                                    except Exception:
                                        continue
                            except Exception:
                                continue
                    except Exception:
                        pass
except Exception:
    pass
finally:
    _doxo_embedded_ms = int((_doxo_time.monotonic() - _doxo_t) * 1000)

# 3. Fallback: runtime.activate_vulcan
if callable(_doxo_activate_vulcan):
    _doxo_t = _doxo_time.monotonic()
    try:
        _doxo_activate_vulcan(globals(), __file__)
    except Exception:
        pass
    finally:
        _doxo_fallback_ms = int((_doxo_time.monotonic() - _doxo_t) * 1000)

# 4. Diagnóstico opcional
if callable(_doxo_probe_embedded):
    try:
        __doxoade_vulcan_probe__ = _doxo_probe_embedded(_doxo_project_root)
        __doxoade_vulcan_probe__["install_meta_ms"] = _doxo_install_ms
        __doxoade_vulcan_probe__["embedded_load_ms"] = _doxo_embedded_ms
        __doxoade_vulcan_probe__["fallback_ms"] = _doxo_fallback_ms
        __doxoade_vulcan_probe__["boot_ms"] = int((_doxo_time.monotonic() - _doxo_boot_t0) * 1000)
        if _doxo_sys.environ.get("VULCAN_DIAG", "").strip() == "1":
            _doxo_sys.stderr.write(
                "[VULCAN:DIAG] "
                + "finder_count=" + str(__doxoade_vulcan_probe__.get("finder_count", 0)) + " "
                + "bin=" + str(__doxoade_vulcan_probe__.get("bin_count", 0)) + " "
                + "lib_bin=" + str(__doxoade_vulcan_probe__.get("lib_bin_count", 0)) + " "
                + "boot_ms=" + str(__doxoade_vulcan_probe__.get("boot_ms", 0)) + " "
                + "install_ms=" + str(__doxoade_vulcan_probe__.get("install_meta_ms", 0)) + " "
                + "embedded_ms=" + str(__doxoade_vulcan_probe__.get("embedded_load_ms", 0)) + " "
                + "fallback_ms=" + str(__doxoade_vulcan_probe__.get("fallback_ms", 0)) + "\n"
            )
    except Exception:
        pass
# --- DOXOADE_VULCAN_BOOTSTRAP:END ---

# -*- coding: utf-8 -*-
# engine/tools/local_index.py

import argparse
import array
import hashlib
import logging
import os
import re
import sqlite3
import struct
import sys
import time
import unicodedata
import difflib

from contextlib import closing
from pathlib import Path
from threading import Lock
from typing import Iterator, List, Optional, Tuple

# dependências do projeto (mantidas)
from engine.tools.inverted_index import InvertedIndexBuilder, InvertedIndexSearcher
from engine.telemetry.core import orn_span, GLOBAL_TELEMETRY, record_direct_telemetry

# ---------------------------------------------------------------------------
# Config / constantes
# ---------------------------------------------------------------------------
logger = logging.getLogger("engine.tools.local_index")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ZIM_DIR = Path(os.environ.get("SICDOX_ZIM_DIR", "data/zim"))
INDEX_DIR = Path(os.environ.get("SICDOX_INDEX_DIR", "data/index"))

_DEFAULT_GGUF = r"C:\Users\olDox222\Documents\A20251122\DOSSIER\Altonomo\Projetos_E_Programas\Projeto_OIA\olDox222RN\ORN\models\sicdox\Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF\qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
_GGUF_PATH_ENV = "SICDOX_GGUF"

_RE_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_RE_NAV = re.compile(r'<[^>]*(navbox|mw-toc|mw-jump|sidebar|reflist)[^>]*>.*?</\w+>', re.DOTALL | re.IGNORECASE)

# Atualizado para capturar tags <math> e <math-display> e isolar fórmulas matemáticas
_RE_CODE = re.compile(
    r"(?P<open><(?P<tag>pre|code|syntaxhighlight|source|math|math-display)(?P<attrs>[^>]*)>)(?P<body>.*?)(?P<close></(?P=tag)>)",
    re.DOTALL | re.IGNORECASE,
)

_RE_TAG = re.compile(r"<[^>\n]+>") 
_RE_ENTITY = re.compile(r"&(?:[a-zA-Z]{2,8}|#\d{1,6});")
_RE_MULTI = re.compile(r"[ \t]{2,}")
_RE_NEWL = re.compile(r"\n{3,}")
_RE_URL = re.compile(r"https?://\S+")


_CODE_BLOCK_SEARCH_RE = re.compile(
    r"\[CODE-BEGIN\s*(?P<lang>[^\]\n]*)\]\n?(?P<body>.*?)\n?\[CODE-END\]",
    re.DOTALL | re.IGNORECASE,
)

_LANGUAGE_ALIASES = {
    "py": "python",
    "python": "python",
    "js": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "csharp": "csharp",
    "cs": "csharp",
    "go": "go",
    "golang": "go",
    "rust": "rust",
    "rb": "ruby",
    "ruby": "ruby",
    "php": "php",
    "swift": "swift",
    "kotlin": "kotlin",
    "scala": "scala",
}


def _extract_code_blocks_for_search(body_text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for m in _CODE_BLOCK_SEARCH_RE.finditer(body_text or ""):
        lang = (m.group("lang") or "").strip().lower()
        body = (m.group("body") or "").strip()
        blocks.append((lang, body))
    return blocks


def _canonical_query_languages(qwords: list[str]) -> set[str]:
    langs: set[str] = set()
    for w in qwords:
        key = w.lower().strip()
        if key in _LANGUAGE_ALIASES:
            langs.add(_LANGUAGE_ALIASES[key])
    return langs


def _score_code_only_match(body_text: str, q_raw: str, qwords: list[str]) -> tuple[bool, float, int, int]:
    """Retorna (passou, tf, termos_unicos, total_termos) para modo --code-only."""
    blocks = _extract_code_blocks_for_search(body_text)
    if not blocks:
        return False, 0.0, 0, 0

    all_code_text = "\n".join(
        ((f"[lang:{lang}]\n" if lang else "") + body)
        for lang, body in blocks
    ).lower()

    query_terms = [w for w in qwords if len(w) >= 2]
    if not query_terms:
        query_terms = [q_raw.lower()] if q_raw.strip() else []

    phrase_match = q_raw.lower() in all_code_text
    matched_terms = {w for w in query_terms if w in all_code_text}

    query_langs = _canonical_query_languages(qwords)
    normalized_block_langs: set[str] = set()
    if query_langs:
        block_langs = {lang for lang, _ in blocks if lang}
        normalized_block_langs = {
            _LANGUAGE_ALIASES.get(lang, lang)
            for lang in block_langs
        }
        # Só aplica bloqueio rígido por linguagem quando há metadata explícita de linguagem
        # no bloco de código. Em conteúdos sem lang tag, evitamos falso-negativo.
        if normalized_block_langs and not (query_langs & normalized_block_langs):
            if not any(lang in all_code_text for lang in query_langs):
                return False, 0.0, len(matched_terms), len(query_terms)

    coverage_terms = list(query_terms)
    if query_langs and not normalized_block_langs:
        non_lang_terms = [w for w in query_terms if _LANGUAGE_ALIASES.get(w, w) not in query_langs]
        if non_lang_terms:
            coverage_terms = non_lang_terms
    matched_for_coverage = {w for w in coverage_terms if w in all_code_text}

    if not phrase_match:
        if len(coverage_terms) >= 2 and len(matched_for_coverage) < 2:
            return False, 0.0, len(matched_terms), len(query_terms)
        if len(coverage_terms) >= 3 and (len(matched_for_coverage) / max(1, len(coverage_terms))) < 0.67:
            return False, 0.0, len(matched_terms), len(query_terms)

    tf = float(sum(all_code_text.count(w) for w in query_terms))
    tf += 18.0 if phrase_match else 0.0
    tf += (len(matched_terms) / max(1, len(query_terms))) * 10.0
    return tf > 0, tf, len(matched_terms), len(query_terms)




def _format_code_only_body(body_text: str, max_blocks: int = 8) -> str:
    """Retorna apenas blocos de código para exibição em modo --code-only."""
    blocks = _extract_code_blocks_for_search(body_text)
    if not blocks:
        return ""

    parts: list[str] = []
    for lang, code in blocks[:max_blocks]:
        lang_suffix = f" {lang}" if lang else ""
        parts.append(f"[CODE-BEGIN{lang_suffix}]\n{code}\n[CODE-END]")
    return "\n\n".join(parts).strip()

def _normalize_math_text(text: str) -> str:
    """Normaliza fórmulas extraídas de HTML para leitura em terminal/contexto."""
    if not text:
        return ""

    compact = " ".join(ln.strip() for ln in text.splitlines() if ln.strip())
    compact = re.sub(r"\s+", " ", compact).strip()

    displaystyle = re.search(r"\{\\displaystyle\s*(.+)\}\s*$", compact)
    if displaystyle and displaystyle.group(1).strip():
        compact = displaystyle.group(1).strip()

    compact = re.sub(r"\s+([\)\]\}])", r"\1", compact)
    compact = re.sub(r"([\(\[\{])\s+", r"\1", compact)
    return compact


def _format_snippet_for_terminal(snippet: str) -> str:
    """Converte marcadores internos em blocos markdown legíveis no CLI."""
    if not snippet:
        return ""

    rendered = snippet

    def _code_repl(match: re.Match) -> str:
        lang = (match.group("lang") or "").strip()
        body = (match.group("body") or "").rstrip()
        lang_suffix = lang if lang else ""
        return f"\n```{lang_suffix}\n{body}\n```\n"

    def _math_repl(match: re.Match) -> str:
        body = _normalize_math_text(match.group("body") or "")
        if not body:
            return ""
        return f"\n$$\n{body}\n$$\n"

    rendered = re.sub(
        r"\[CODE-BEGIN\s*(?P<lang>[^\]\n]*)\]\n?(?P<body>.*?)\n?\[CODE-END\]",
        _code_repl,
        rendered,
        flags=re.DOTALL | re.IGNORECASE,
    )
    rendered = re.sub(
        r"\[MATH-BEGIN\]\n?(?P<body>.*?)\n?\[MATH-END\]",
        _math_repl,
        rendered,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return re.sub(r"\n{3,}", "\n\n", rendered).strip()

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

try:
    from rapidfuzz import fuzz, process as rprocess 
    _HAS_RAPIDFUZZ = True
except Exception:
    _HAS_RAPIDFUZZ = False

def _normalize_text_for_match(s: str) -> str:
    if s is None:
        return ""
    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s

def _trigrams_for(s: str) -> set:
    s = _normalize_text_for_match(s)
    if not s:
        return set()
    s = f"  {s} "  
    tr = set()
    for i in range(len(s) - 2):
        tr.add(s[i : i + 3])
    return tr

def _similarity_ratio(a: str, b: str) -> float:
    if _HAS_RAPIDFUZZ:
        return fuzz.token_sort_ratio(a, b) / 100.0
    return difflib.SequenceMatcher(None, a, b).ratio()

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "no", "off")

def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

def _clean_body(text: str, max_chars: int = 100_000) -> str:
    if not text:
        return ""
    if not isinstance(text, str):
        try: text = str(text)
        except Exception: text = ""

    text = "".join(ch for ch in text if (ch >= " " or ch in ("\n", "\t")))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", "    ")

    lines =[ln.rstrip() for ln in text.split("\n")]
    while lines and lines[0].strip() == "":
        lines.pop(0)

    if lines:
        first = lines[0].strip()
        if 0 < len(first) <= 120 and "[CODE-BEGIN" not in first and "[MATH-BEGIN" not in first:
            def norm_key(s: str) -> str:
                return re.sub(r"[^\w\s]", "", s or "").strip().lower()
            fk = norm_key(first)
            i = 1
            removed = 0
            while i < min(len(lines), 30):
                if norm_key(lines[i]) == fk:
                    lines.pop(i)
                    removed += 1
                    continue
                if lines[i].strip() == "" and i + 1 < len(lines) and norm_key(lines[i + 1]) == fk:
                    lines.pop(i)
                    lines.pop(i)
                    removed += 2
                    continue
                i += 1

    limit_top = min(len(lines), 40)
    out_top =[]
    seen_short = set()
    for ln in lines[:limit_top]:
        key = ln.strip().lower()
        if key and len(key) <= 120 and "[CODE-BEGIN" not in key and "[CODE-END]" not in key and "[MATH-BEGIN" not in key and "[MATH-END]" not in key:
            if key in seen_short:
                continue
            seen_short.add(key)
        out_top.append(ln)
    
    rest = lines[limit_top:]
    lines = out_top + rest

    out_lines =[]
    total_len = 0
    in_code = False
    for ln in lines:
        if "[CODE-BEGIN" in ln or "[MATH-BEGIN" in ln:
            in_code = True
        elif "[CODE-END]" in ln or "[MATH-END]" in ln:
            in_code = False
            
        out_lines.append(ln)
        total_len += len(ln) + 1
        
        if total_len > max_chars and not in_code:
            out_lines.append("...")
            break

    text = "\n".join(out_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_code_blocks(html: str) -> tuple[str, list[tuple[str, str]]]:
    import html as _html_lib
    code_blocks =[]
    out_html =[]
    last = 0
    idx = 0
    for m in _RE_CODE.finditer(html):
        start, end = m.span()
        tag = m.group("tag").lower()
        attrs = m.group("attrs") or ""
        body = m.group("body") or ""
        
        body_clean = re.sub(r"<[^>]+>", "", body)
        body_clean = _html_lib.unescape(body_clean)
        
        if tag in ("math", "math-display"):
            ph = f"__MATH_BLOCK_{idx}__"
            code_repr = f"\n[MATH-BEGIN]\n{body_clean.strip()}\n[MATH-END]\n"
            code_blocks.append((ph, code_repr))
        else:
            lang = ""
            cls_m = re.search(r'class=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if cls_m:
                cls = cls_m.group(1)
                lm = re.search(r"(?:lang|language|language-|(brush:)|(?:language:))?([a-zA-Z0-9_+-]+)", cls)
                if lm:
                    parts = re.split(r"[^\w+-]+", cls)
                    for p in parts[::-1]:
                        if len(p) <= 20 and re.match(r"^[a-zA-Z0-9_+-]+$", p):
                            lang = p.lower()
                            break
            data_lang = re.search(r'data-lang=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if data_lang:
                lang = data_lang.group(1).lower()
            
            ph = f"__CODE_BLOCK_{idx}__"
            lang_str = f" {lang}" if lang else ""
            code_repr = f"\n[CODE-BEGIN{lang_str}]\n{body_clean.strip()}\n[CODE-END]\n"
            code_blocks.append((ph, code_repr))
            
        out_html.append(html[last:start])
        out_html.append(ph)
        last = end
        idx += 1
        
    out_html.append(html[last:])
    return "".join(out_html), code_blocks

def _restore_code_placeholders(text: str, code_blocks: list[tuple[str,str]]) -> str:
    for ph, code in code_blocks:
        text = text.replace(ph, code)
    return text

def _strip_html(html: str, max_chars: int = 64000) -> str:
    if not html:
        return ""

    extracted_html, code_blocks = _extract_code_blocks(html)

    text = _RE_NAV.sub(" ", extracted_html)
    text = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", text, flags=re.DOTALL | re.IGNORECASE)

    text = _RE_TAG.sub(" ", text)
    text = _RE_ENTITY.sub(" ", text)
    text = _RE_URL.sub(" ", text)
    text = _RE_MULTI.sub(" ", text)
    text = _RE_NEWL.sub("\n\n", text).strip()

    if code_blocks:
        text = _restore_code_placeholders(text, code_blocks)

    if len(text) > max_chars:
        cut_text = text[:max_chars]
        last_cb = cut_text.rfind("[CODE-BEGIN")
        last_ce = cut_text.rfind("[CODE-END]")
        last_mb = cut_text.rfind("[MATH-BEGIN")
        last_me = cut_text.rfind("[MATH-END]")
        
        # Proteção para blocos de Código
        if last_cb > last_ce:
            actual_end = text.find("[CODE-END]", max_chars)
            if actual_end != -1:
                text = text[:actual_end + len("[CODE-END]")]
            else: text = cut_text
        # Proteção para blocos Matemáticos
        elif last_mb > last_me:
            actual_end = text.find("[MATH-END]", max_chars)
            if actual_end != -1:
                text = text[:actual_end + len("[MATH-END]")]
            else: text = cut_text
        else:
            text = cut_text

    return text

# ---------------------------------------------------------------------------
# Compression helpers (pyzstd optional)
# ---------------------------------------------------------------------------

def _compress(data: bytes) -> bytes:
    try:
        import pyzstd
        compressed = pyzstd.compress(data)
        return b"\x01" + compressed
    except Exception:
        logger.debug("pyzstd unavailable; storing raw payload (flag 0)")
        return b"\x00" + data

def _decompress(data: bytes) -> bytes:
    if not data:
        return data
    flag = data[0:1]
    payload = data[1:]
    if flag == b"\x00":
        return payload
    if flag == b"\x01":
        try:
            import pyzstd
            return pyzstd.decompress(payload)
        except Exception:
            raise RuntimeError("Unable to decompress zstd payload: pyzstd missing or decompression failed")
    if len(data) >= 5 and data[1:5] == b"\x28\xb5\x2f\xfd":
        try:
            import pyzstd
            return pyzstd.decompress(payload)
        except Exception:
            raise RuntimeError("Unknown blob format and pyzstd unavailable")
    return payload


# ---------------------------------------------------------------------------
# Read entry content (consolidated)
# ---------------------------------------------------------------------------

def _read_entry_content(entry) -> Optional[bytes]:
    for method in ("read", "get_data", "content", "data"):
        fn = getattr(entry, method, None)
        if fn is None:
            continue
        try:
            result = fn() if callable(fn) else fn
            if isinstance(result, (bytes, bytearray)) and len(result) > 0:
                return bytes(result)
            if isinstance(result, memoryview) and len(result) > 0:
                return bytes(result)
        except Exception:
            continue

    for attr in ("_data", "_content", "raw"):
        val = getattr(entry, attr, None)
        if isinstance(val, (bytes, bytearray, memoryview)) and len(val) > 0:
            return bytes(val)
    return None

# ---------------------------------------------------------------------------
# TokenizerBridge (thread-safe, GGUF via env)
# ---------------------------------------------------------------------------

class TokenizerBridge:
    """Tokenizador thread-safe com fast-path via servidor ORN.

    Hierarquia de fallback (mais rápido → mais lento):
      1. Servidor ORN (socket 127.0.0.1:8371) — modelo já carregado, zero overhead.
      2. vocab_only local                      — carga ~10s no N2808, só se servidor offline.

    O fast-path elimina os ~120 hits de profiler em local_index.py:642 que
    apareciam na telemetria toda vez que 'orn think' subia um processo novo.
    """

    _llm_vocab = None
    _lock = Lock()

    # Cache de disponibilidade do servidor: None = não testado ainda,
    # True = online, False = offline (reavalia após _SERVER_RETRY_S segundos).
    _server_ok: bool | None = None
    _server_fail_time: float = 0.0
    _SERVER_HOST  = "127.0.0.1"
    _SERVER_PORT  = int(os.environ.get("ORN_SERVER_PORT", "8371"))
    _SERVER_RETRY_S: float = 30.0   # após falha, tenta de novo em 30s

    # ------------------------------------------------------------------ #
    # Fast-path: delega ao servidor ORN via socket                        #
    # ------------------------------------------------------------------ #

    @classmethod
    def _server_available(cls) -> bool:
        """Verifica disponibilidade do servidor com back-off simples."""
        import socket as _sock
        import time as _time

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
            cls._server_ok = False
            cls._server_fail_time = _time.monotonic()
            return False

    @classmethod
    def _server_tokenize(cls, text: str) -> list[int] | None:
        """Pede ao servidor para tokenizar 'text'. Retorna None em falha."""
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
            if resp.get("error"):
                return None
            return resp.get("tokens")   # list[int]
        except Exception:
            cls._server_ok = False
            cls._server_fail_time = __import__("time").monotonic()
            return None

    @classmethod
    def _server_detokenize(cls, tokens: list[int]) -> str | None:
        """Pede ao servidor para detokenizar. Retorna None em falha."""
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
            if resp.get("error"):
                return None
            return resp.get("text")   # str
        except Exception:
            cls._server_ok = False
            cls._server_fail_time = __import__("time").monotonic()
            return None

    # ------------------------------------------------------------------ #
    # Fallback: vocab_only local (caminho original)                       #
    # ------------------------------------------------------------------ #

    @classmethod
    def get_gguf_path(cls) -> str:
        env = os.environ.get(_GGUF_PATH_ENV)
        if env and os.path.exists(env):
            return env
        if os.path.exists(_DEFAULT_GGUF):
            return _DEFAULT_GGUF
        raise FileNotFoundError(f"GGUF não encontrado. Defina { _GGUF_PATH_ENV } apontando para o arquivo .gguf")

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

    # ------------------------------------------------------------------ #
    # API pública (server-first, fallback local)                          #
    # ------------------------------------------------------------------ #

    @classmethod
    def text_to_bytes(cls, text: str) -> bytes:
        # Fast-path: servidor
        if cls._server_available():
            tokens = cls._server_tokenize(text)
            if tokens is not None:
                return array.array("i", tokens).tobytes()
        # Fallback: vocab_only local
        vocab = cls.get_vocab()
        tokens = vocab.tokenize(text.encode("utf-8"), add_bos=False)
        return array.array("i", tokens).tobytes()

    @classmethod
    def bytes_to_text(cls, data: bytes) -> str:
        if not data:
            return ""
        if len(data) % 4 != 0:
            try: return data.decode("utf-8", errors="ignore")
            except Exception: return ""
        try:
            arr = array.array("i")
            arr.frombytes(data)
            tokens = arr.tolist()

            # Fast-path: servidor
            if cls._server_available():
                result = cls._server_detokenize(tokens)
                if result is not None:
                    return result

            # Fallback: vocab_only local
            vocab = cls.get_vocab()
            if tokens and (max(tokens) >= vocab.n_vocab() or min(tokens) < 0):
                return data.decode("utf-8", errors="ignore")
            return vocab.detokenize(tokens).decode("utf-8", errors="ignore")
        except Exception:
            return data.decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# LocalIndexCache (Gestor de RAM para a IA em Runtime)
# ---------------------------------------------------------------------------

class LocalIndexCache:
    """
    Mantém conexões de banco de dados e leitores de índice invertido vivos na memória RAM
    para eliminar os custos de I/O em ambientes de execução contínua (como o cérebro da IA).
    """
    _cache = {}
    _lock = Lock()

    @classmethod
    def get(cls, source_id: str) -> Tuple[Optional[sqlite3.Connection], Optional[InvertedIndexSearcher]]:
        with cls._lock:
            if source_id not in cls._cache:
                db_path = _source_id_to_db(source_id)
                inv_dir = INDEX_DIR / source_id
                
                con = None
                searcher = None
                
                if db_path.exists():
                    try:
                        # check_same_thread=False permite que as diversas threads de contexto da IA acessem
                        con = sqlite3.connect(str(db_path), check_same_thread=False)
                        con.execute("PRAGMA query_only=1")
                        # 64MB Cache de OS/RAM pre-carregado por DB (muito econômico e ultra rápido)
                        con.execute("PRAGMA cache_size=-64000")
                    except Exception:
                        logger.error(f"Erro ao abrir SQLite cache para {source_id}", exc_info=True)
                        
                if inv_dir.exists():
                    try:
                        searcher = InvertedIndexSearcher(inv_dir)
                    except Exception:
                        logger.error(f"Erro ao abrir InvertedIndex cache para {source_id}", exc_info=True)
                        
                cls._cache[source_id] = (con, searcher)
            return cls._cache[source_id]

    @classmethod
    def evict(cls, source_id: str):
        """Remove e fecha instâncias de cache para permitir atualizações (Build) sem FileLocks."""
        with cls._lock:
            if source_id in cls._cache:
                con, searcher = cls._cache.pop(source_id)
                if con:
                    try: con.close()
                    except Exception as e:
                        import logging as _dox_log
                        _dox_log.error(f"[INFRA] evict: {e}")
                if searcher:
                    try: searcher.close()
                    except Exception as e:
                        import logging as _dox_log
                        _dox_log.error(f"[INFRA] evict: {e}")
                    
    @classmethod
    def preload(cls, source_ids: List[str] = None):
        """Pré-carrega o Vocabulário LLM e os bancos de dados/índices solicitados na RAM."""
        logger.info("[CACHE] Pré-carregando GGUF Vocab na memória RAM (Isto leva alguns segundos)...")
        TokenizerBridge.get_vocab()
        
        if source_ids:
            for sid in source_ids:
                logger.info(f"[CACHE] Pré-carregando banco SQLite e InvertedIndex para: {sid}")
                cls.get(sid)


# ---------------------------------------------------------------------------
# LocalResult (consolidado)
# ---------------------------------------------------------------------------

class LocalResult:
    __slots__ = ("source", "title", "body", "path")

    def __init__(self, source: str, title: str, body: str, path: str = ""):
        self.source = source
        self.title = title
        self.body = body
        self.path = path

    @property
    def ok(self) -> bool:
        return bool(self.title and self.body.strip())

    def get_snippet(self, query: str = "", max_chars: int = 1200, n_snippets: int = 3) -> str:
        if not self.ok: return ""
        text = self.body
        if not text: return ""

        q = (query or "").strip()
        if q:
            qlower = q.lower()
            positions =[]
            words =[w for w in re.findall(r"[A-Za-z0-9_]{2,}", qlower)]
            if words:
                for w in words:
                    start = 0
                    while True:
                        idx = text.lower().find(w, start)
                        if idx == -1: break
                        positions.append(idx)
                        start = idx + len(w)
            else:
                idx = text.lower().find(qlower)
                if idx != -1: positions.append(idx)

            positions = sorted(set(positions))

            if positions:
                snippets =[]
                used = 0
                for pos in positions:
                    if len(snippets) >= n_snippets: break
                    left = max(0, pos - 120)
                    right = min(len(text), pos + 420)
                    if snippets and left < snippets[-1][1]:
                        left = snippets[-1][1] + 1
                    snippets.append((left, right))
                    used += (right - left)

                out_parts =[]
                total = 0
                for left, right in snippets:
                    part = text[left:right].strip()
                    real_left = left
                    real_right = right
                    
                    # Proteção contra cortes no meio de códigos ou fórmulas matemáticas
                    open_code = text.rfind("[CODE-BEGIN", 0, right)
                    close_code = text.rfind("[CODE-END]", 0, right)
                    if open_code > close_code:
                        end_idx = text.find("[CODE-END]", right)
                        if end_idx != -1: real_right = max(real_right, end_idx + len("[CODE-END]"))

                    open_math = text.rfind("[MATH-BEGIN", 0, right)
                    close_math = text.rfind("[MATH-END]", 0, right)
                    if open_math > close_math:
                        end_idx = text.find("[MATH-END]", right)
                        if end_idx != -1: real_right = max(real_right, end_idx + len("[MATH-END]"))
                    
                    part = text[real_left:real_right]

                    if q:
                        try:
                            for w in words:
                                if w.upper() in["CODE", "BEGIN", "END", "MATH"]: continue
                                part = re.sub(rf"(?i)\b{re.escape(w)}\b", lambda m: f"**{m.group(0)}**", part)
                        except Exception: pass
                            
                    if real_left > 0: part = "..." + part
                    if real_right < len(text): part = part + "..."
                        
                    out_parts.append(part)
                    total += len(part)
                    if total >= max_chars: break

                return "\n\n".join(out_parts)

        leading = text[:max_chars]
        
        # Proteção extra para fallback context
        open_code = leading.rfind("[CODE-BEGIN")
        close_code = leading.rfind("[CODE-END]")
        if open_code > close_code:
            end_idx = text.find("[CODE-END]", open_code)
            if end_idx != -1 and end_idx < max_chars * 3:
                leading = text[: end_idx + len("[CODE-END]")]
                
        open_math = leading.rfind("[MATH-BEGIN")
        close_math = leading.rfind("[MATH-END]")
        if open_math > close_math:
            end_idx = text.find("[MATH-END]", open_math)
            if end_idx != -1 and end_idx < max_chars * 3:
                leading = text[: end_idx + len("[MATH-END]")]
        
        leading = leading.strip()
        if len(leading) < len(text):
            leading = leading + "..."
        return leading

    def to_prompt_block(self, max_chars: int = 600, query: str = "") -> str:
        if not self.ok: return ""
        snippet = self.get_snippet(query, max_chars)
        return f"[CTX-BEGIN]\nscope: {self.source} | {self.title}\n{snippet}\n[CTX-END]\n"


# ---------------------------------------------------------------------------
# ZIM iteration
# ---------------------------------------------------------------------------

def _zim_to_source_id(zim_path: str | Path) -> str:
    name = Path(zim_path).stem
    name = name.replace("-", "_").replace(".", "_")
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return re.sub(r"_+", "_", name).strip("_").lower()

def _source_id_to_db(source_id: str) -> Path:
    return INDEX_DIR / f"{source_id}.db"

def _find_zim_for_source(source_id: str) -> Optional[Path]:
    if ZIM_DIR.exists():
        for zim in ZIM_DIR.glob("*.zim"):
            if _zim_to_source_id(zim) == source_id: return zim
    return None

def _iter_zim_entries(zim_path: str, verbose: bool = True, start_scanned: int = 0) -> Iterator[tuple[int, str, str, str]]:
    import pyzim

    p = Path(zim_path).absolute()
    total_scanned = total_yielded = total_redirect = 0
    total_non_html = total_empty = total_error = 0

    with pyzim.Zim.open(str(p), mode="r") as zim:
        for entry in zim.iter_entries():
            total_scanned += 1
            if start_scanned and total_scanned <= start_scanned:
                continue

            if verbose and total_scanned % 5000 == 0:
                logger.info("[ZIM] scanned=%d yielded=%d redirect=%d non_html=%d empty=%d",
                    total_scanned, total_yielded, total_redirect, total_non_html, total_empty)

            if getattr(entry, "is_redirect", False):
                total_redirect += 1
                continue

            ns = getattr(entry, "namespace", None)
            if ns is not None:
                if isinstance(ns, bytes): ns = ns.decode("utf-8", errors="ignore")
                ns = str(ns).strip()
                if ns in ("I", "-", "X"):
                    total_non_html += 1
                    continue

            content_bytes = _read_entry_content(entry)
            if not content_bytes:
                total_empty += 1
                continue

            head = content_bytes[:400].lower()
            is_html = (
                b"<html" in head or b"<!doctype" in head or b"<body" in head
                or b"<p" in head or b"<div" in head or b"<h1" in head
                or b"<h2" in head or content_bytes[:1] == b"<"
            )
            if not is_html:
                total_non_html += 1
                continue

            try:
                title = getattr(entry, "title", "")
                if isinstance(title, bytes): title = title.decode("utf-8", errors="ignore")
                title = str(title).strip()

                path = getattr(entry, "url", None) or getattr(entry, "path", "")
                if isinstance(path, bytes): path = path.decode("utf-8", errors="ignore")
                path = str(path).strip()

                if not title: title = path.split("/")[-1].replace("_", " ").strip()

                content = content_bytes.decode("utf-8", errors="replace")
                total_yielded += 1
                yield total_scanned, title, path, content

            except Exception:
                total_error += 1
                continue

    if verbose:
        logger.info("[ZIM] total: scanned=%d yielded=%d redirect=%d non_html=%d empty=%d error=%d",
            total_scanned, total_yielded, total_redirect, total_non_html, total_empty, total_error)


# ---------------------------------------------------------------------------
# BUILD INDEX
# ---------------------------------------------------------------------------

def build_index(zim_path: str, source_id: Optional[str] = None, batch_size: int = 1000, verbose: bool = True) -> Path:
    try:
        import pyzim 
    except ImportError:
        raise ImportError("pyzim não instalado. pip install pyzim")

    zim_path = str(zim_path)
    if not Path(zim_path).exists():
        available = sorted(str(z.name) for z in ZIM_DIR.glob("*.zim")) if ZIM_DIR.exists() else []
        hint = ""
        if available:
            close = difflib.get_close_matches(Path(zim_path).name, available, n=3, cutoff=0.35)
            if close:
                hint = "\nSugestões próximas em data/zim: " + ", ".join(close)
            else:
                hint = "\nZIMs disponíveis em data/zim: " + ", ".join(available[:5])
        raise FileNotFoundError(f"ZIM não encontrado: {zim_path}{hint}")

    TokenizerBridge.get_vocab()

    if source_id is None:
        source_id = _zim_to_source_id(zim_path)

    # Fundamental: Evitar erro de FileLock no Windows caso um servidor esteja com o cache carregado
    LocalIndexCache.evict(source_id)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    db_path = str(_source_id_to_db(source_id))
    db_p = Path(db_path)
    inv_dir = INDEX_DIR / source_id
    resume_enabled = _env_bool("SICDOX_RESUME_BUILD", True)
    build_inverted = _env_bool("SICDOX_BUILD_INVERTED", False)
    start_scanned = 0
    start_doc_id = 0
    resume_mode = False

    try:
        if db_p.exists() and resume_enabled:
            probe = sqlite3.connect(db_path)
            try:
                probe.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
                meta = dict(probe.execute("SELECT key, value FROM meta").fetchall())
                if meta.get("build_status") == "in_progress":
                    resume_mode = True
                    start_scanned = int(meta.get("build_scanned_entries", "0") or 0)
                    start_doc_id = int(meta.get("build_docs_processed", "0") or 0)
            finally:
                probe.close()

        if db_p.exists() and not resume_mode:
            logger.info("[SiCDox BUILD] DB existente encontrado, removendo para rebuild: %s", db_path)
            for suf in ("", "-wal", "-shm"):
                f = db_p.with_name(db_p.name + suf)
                try:
                    if f.exists(): f.unlink()
                except Exception: pass
        if inv_dir.exists() and not resume_mode:
            try:
                import shutil
                shutil.rmtree(inv_dir)
            except Exception: pass
    except Exception:
        pass

    if verbose:
        if resume_mode:
            logger.info("[SiCDox BUILD] Retomando build anterior... DB=%s start_scanned=%d docs=%d", db_path, start_scanned, start_doc_id)
        else:
            logger.info("[SiCDox BUILD] Construindo Banco Tokenizado... DB: %s", db_path)

    inv_builder = InvertedIndexBuilder() if build_inverted else None
    t0 = time.monotonic()

    con = sqlite3.connect(db_path, isolation_level=None)
    try:
        con.execute("PRAGMA page_size=4096")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        try: con.execute("PRAGMA cache_size = -20000")
        except Exception: pass

        con.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY,
            title TEXT,
            path TEXT,
            content_hash TEXT
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS content_pool (
            hash TEXT PRIMARY KEY,
            token_blob BLOB
        )
        """)
        con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")

        con.execute("CREATE INDEX IF NOT EXISTS idx_pages_hash ON pages(content_hash)")
        con.execute("""
        CREATE TABLE IF NOT EXISTS title_trigrams (
            trigram TEXT,
            doc_id INTEGER
        )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_title_trigrams_trigram ON title_trigrams(trigram)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_title_trigrams_doc ON title_trigrams(doc_id)")

        con.execute("BEGIN")
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('build_status', 'in_progress')")
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('build_scanned_entries', ?)", (str(start_scanned),))
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('build_docs_processed', ?)", (str(start_doc_id),))

        vocab = TokenizerBridge.get_vocab()
        
        MAX_TOKENIZE_CHARS = int(os.environ.get("SICDOX_MAX_CHARS", "64000"))

        count = start_doc_id
        deduplicated = 0
        buf_pages: List[tuple] =[]
        seen_hashes = set()
        content_pending: dict[str, bytes] = {}
        title_trigrams_pending: List[tuple] =[]
        CONTENT_FLUSH_BATCH = int(os.environ.get("SICDOX_CONTENT_BATCH", "256"))
        last_scanned = start_scanned

        def _flush_content_pending():
            nonlocal content_pending
            if not content_pending: return
            items = list(content_pending.items())
            with orn_span("build.sql_insert", category="index"):
                try: con.executemany("INSERT OR IGNORE INTO content_pool (hash, token_blob) VALUES (?, ?)", items)
                except Exception:
                    for k, v in items:
                        try: con.execute("INSERT OR IGNORE INTO content_pool (hash, token_blob) VALUES (?, ?)", (k, v))
                        except Exception: pass
            content_pending = {}

        for scanned_idx, title, path, html in _iter_zim_entries(zim_path, verbose=verbose, start_scanned=start_scanned):
            last_scanned = scanned_idx
            with orn_span("build.strip_html", category="index"):
                body = _strip_html(html, max_chars=MAX_TOKENIZE_CHARS)

            if len(body.strip()) < 50: continue

            with orn_span("build.tokenize", category="index"):
                try:
                    body_bytes = body.encode("utf-8")
                    qtoks = vocab.tokenize(body_bytes, add_bos=False)
                    title_bytes = title.encode("utf-8")
                    ttoks = vocab.tokenize(title_bytes, add_bos=False)
                    body_arr = array.array("i", qtoks)
                    payload = body_arr.tobytes()
                except Exception: continue

                h = hashlib.md5(payload).hexdigest()

            if h not in seen_hashes:
                seen_hashes.add(h)
                with orn_span("build.zstd_compress", category="index"):
                    compressed = _compress(payload)

                content_pending[h] = compressed
                if len(content_pending) >= CONTENT_FLUSH_BATCH: _flush_content_pending()
            else:
                deduplicated += 1

            count += 1
            buf_pages.append((count, title, path, h))
            
            tnorm = _normalize_text_for_match(title)
            trigs = _trigrams_for(tnorm)
            for tg in trigs: title_trigrams_pending.append((tg, count))

            if len(title_trigrams_pending) >= 2000:
                with orn_span("build.sql_insert_trigrams", category="index"):
                    con.executemany("INSERT INTO title_trigrams (trigram, doc_id) VALUES (?, ?)", title_trigrams_pending)
                title_trigrams_pending =[]

            try: combined_tokens = ttoks + ttoks + qtoks
            except Exception: combined_tokens = qtoks

            if build_inverted and inv_builder is not None:
                with orn_span("build.inverted_idx", category="index"):
                    inv_builder.add_document(count, combined_tokens)

            if len(buf_pages) >= batch_size:
                with orn_span("build.sql_commit", category="index"):
                    con.executemany("INSERT INTO pages (id, title, path, content_hash) VALUES (?,?,?,?)", buf_pages)
                    _flush_content_pending()
                    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('build_scanned_entries', ?)", (str(last_scanned),))
                    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('build_docs_processed', ?)", (str(count),))
                    con.execute("COMMIT")
                    con.execute("BEGIN")
                    buf_pages.clear()
                if verbose: logger.info("[BUILD] ⏳ %d artigos processados e salvos no DB...", count)

        if verbose: logger.info("[BUILD] ZIM extraído por completo. Salvando registros finais no banco...")

        if buf_pages: con.executemany("INSERT INTO pages (id, title, path, content_hash) VALUES (?,?,?,?)", buf_pages)
        _flush_content_pending()
        
        if title_trigrams_pending:
            con.executemany("INSERT INTO title_trigrams (trigram, doc_id) VALUES (?, ?)", title_trigrams_pending)
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('build_scanned_entries', ?)", (str(last_scanned),))
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('build_docs_processed', ?)", (str(count),))
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('build_status', 'completed')")
        con.execute("COMMIT")

    except Exception:
        logger.exception("Erro durante build_index; rollback")
        try: con.rollback()
        except Exception: pass
        raise
    finally:
        con.close()

    if build_inverted and inv_builder is not None:
        if verbose: logger.info("[BUILD] Banco de dados finalizado. Ordenando Índice Invertido em memória...")
        inv_builder.finalize()
        inv_dir = INDEX_DIR / source_id
        if verbose: logger.info("[BUILD] Gravando Índice Invertido no disco: %s (isso pode levar alguns minutos)...", inv_dir)
        inv_builder.write(inv_dir)
    else:
        if verbose:
            logger.info("[BUILD] Índice invertido em memória desativado (SICDOX_BUILD_INVERTED=0). Build persistente concluído sem pico de RAM.")

    if verbose: logger.info("[BUILD] ✅ PROCESSO CONCLUÍDO: %d artigos (Dedup: %d) finalizados em %.1fs", count, deduplicated, time.monotonic() - t0)

    return Path(db_path)

# ---------------------------------------------------------------------------
# SEARCH LOCAL
# ---------------------------------------------------------------------------

def _simple_query_tokens(text: str) -> list[int]:
    toks =[]
    for w in re.findall(r"[A-Za-z0-9_]+|[^\w\s]", text):
        h = int(hashlib.md5(w.encode("utf-8")).hexdigest()[:8], 16)
        toks.append(h & 0x7fffffff)
    return toks

def _fuzzy_title_search(con: sqlite3.Connection, query: str, candidate_limit: int = 30, final_limit: int = 10):
    qnorm = _normalize_text_for_match(query)
    trigs = list(_trigrams_for(qnorm))
    if not trigs: return[]

    placeholders = ",".join("?" for _ in trigs)
    sql = f"""
      SELECT doc_id, COUNT(*) as cnt
      FROM title_trigrams
      WHERE trigram IN ({placeholders})
      GROUP BY doc_id
      ORDER BY cnt DESC
      LIMIT ?
    """
    rows = con.execute(sql, (*trigs, candidate_limit)).fetchall()
    if not rows: return []

    candidates =[r[0] for r in rows]
    rows2 = con.execute(f"SELECT id, title FROM pages WHERE id IN ({','.join('?' for _ in candidates)})", candidates).fetchall()
    title_map = {r[0]: r[1] for r in rows2}

    scored =[]
    for doc_id in candidates:
        title = title_map.get(doc_id, "")
        score = _similarity_ratio(qnorm, _normalize_text_for_match(title))
        tnorm = _normalize_text_for_match(title)
        if tnorm == qnorm: score += 0.6
        elif tnorm.startswith(qnorm): score += 0.35
        scored.append((doc_id, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return[doc_id for doc_id, _ in scored[:final_limit]]

def search_local(query: str, source_id: str, limit: int = 3, code_only: bool = False) -> List[LocalResult]:
    if not query.strip():
        return[]
        
    source_id = re.sub(r"_+", "_", re.sub(r"[^a-zA-Z0-9_]", "_", source_id.replace("-", "_").replace(".", "_"))).strip("_").lower()

    t_start = time.perf_counter()
    label = f"{source_id}-local"

    try:
        con, searcher = LocalIndexCache.get(source_id)
        if not con: return[]

        results: List[LocalResult] =[]
        doc_ids: List[int] =[]
        candidates =[]
        body_ids: list[int] =[]
        query_tokens: list[int] = []

        q_raw = query.strip()
        qnorm = _normalize_text_for_match(q_raw)

        # Skip exact title match Se a pessoa quer forçar pesquisa apenas por Código
        if not code_only:
            try:
                row = con.execute("SELECT p.id, p.title, p.path, c.token_blob FROM pages p JOIN content_pool c ON p.content_hash = c.hash WHERE LOWER(p.title) = ? LIMIT 1", (qnorm,)).fetchone()
                if row:
                    doc_id, title, path, blob = row
                    try:
                        decompressed = _decompress(blob)
                        body = TokenizerBridge.bytes_to_text(decompressed)
                    except Exception: body = ""
                    res = LocalResult(label, title, (body[len(title):].strip() if body.lower().startswith(title.lower()) else body), path)
                    return [res]
            except Exception: pass

        _formula_like = bool(re.search(r"[A-Za-z].*\d|\d", q_raw)) and len(q_raw) <= 12

        if searcher:
            try:
                if _env_bool("SICDOX_FAST_MODE"):
                    query_tokens = _simple_query_tokens(query)
                else:
                    vocab = TokenizerBridge.get_vocab()
                    query_tokens = vocab.tokenize(query.encode("utf-8"), add_bos=False)
                # Mais tolerante para trazer candidatos se estivermos no modo "só código"
                body_ids = searcher.search(query_tokens, limit=120 if code_only else 80) or[]
                candidates.extend(body_ids)
            except Exception: pass

        q_esc = _like_escape(q_raw)
        exact = q_raw
        starts = f"{q_esc}%"
        contains = f"%{q_esc}%"
        try:
            rows = con.execute(
                "SELECT p.id FROM pages p WHERE p.title = ? OR p.title LIKE ? ESCAPE '\\' OR p.title LIKE ? ESCAPE '\\' LIMIT ?",
                (exact, starts, contains, 80),
            ).fetchall()
            title_ids_quick =[r[0] for r in rows]
        except Exception: title_ids_quick =[]

        if not title_ids_quick:
            try: title_ids_quick = _fuzzy_title_search(con, q_raw, candidate_limit=200, final_limit=60)
            except Exception: title_ids_quick =[]

        for tid in title_ids_quick:
            if tid not in candidates: candidates.append(tid)

        if not candidates:
            return[]

        placeholders = ",".join("?" for _ in candidates)
        rows = con.execute(
            f"SELECT p.id, p.title, p.path, c.token_blob FROM pages p JOIN content_pool c ON p.content_hash = c.hash WHERE p.id IN ({placeholders})",
            candidates,
        ).fetchall()
        row_map = {r[0]: r for r in rows}

        qtoken_set = set(int(t) for t in (query_tokens or []))
        qwords =[w for w in re.findall(r"[A-Za-z0-9_]+", q_raw.lower())]

        scored =[]
        for cid in candidates:
            r = row_map.get(cid)
            if not r: continue
            doc_id, title, path, blob = r

            tokens = None
            body_text = ""
            try:
                decompressed = _decompress(blob)
                arr = array.array("i")
                arr.frombytes(decompressed)
                tokens = arr.tolist()
                body_text = TokenizerBridge.bytes_to_text(decompressed)
                
                body_text = _clean_body(body_text, max_chars=100_000)
                if body_text.lower().startswith(title.lower()):
                    body_text = re.sub(rf"^{re.escape(title)}\s*", "", body_text, flags=re.IGNORECASE).lstrip()
            except Exception:
                try: body_text = TokenizerBridge.bytes_to_text(_decompress(blob))
                except Exception: body_text = ""

            dl = max(1, len(tokens) if tokens is not None else max(1, len(body_text.split())))
            
            # FILTRO ESTRITO DE CÓDIGO
            if code_only:
                passed, tf, matched_terms, total_terms = _score_code_only_match(body_text, q_raw, qwords)
                if not passed:
                    continue
                early_tf = tf + (8.0 if total_terms > 0 and matched_terms == total_terms else 0.0)
                positions =[] # Bypass
            else:
                if tokens is not None:
                    positions =[i for i, tok in enumerate(tokens) if tok in qtoken_set]
                    tf = len(positions)
                    early_window = min(200, max(20, dl // 8))
                    early_tf = sum(1 for p in positions if p < early_window)
                    first_pos = min(positions) if positions else None
                else:
                    words = [w for w in re.findall(r"[A-Za-z0-9_]+", body_text.lower())]
                    tf = sum(body_text.lower().count(w) for w in qwords if len(w) > 0)
                    early_tf = sum(body_text[:400].lower().count(w) for w in qwords if len(w) > 0)
                    positions =[]
                    first_pos = 0 if early_tf > 0 else None

            tnorm = _normalize_text_for_match(title)
            title_boost = 0.0
            if tnorm == qnorm: title_boost = 3.0
            elif tnorm.startswith(qnorm): title_boost = 1.8
            else:
                title_sim = _similarity_ratio(qnorm, tnorm)
                title_boost = 0.9 * title_sim

            density = tf / dl
            early_density = early_tf / max(1, dl)
            front_bonus = 1.0 if early_tf > 0 and (positions and min(positions) < max(10, dl // 20)) else 0.0

            formula_score = 0.0
            if _formula_like and body_text:
                if q_raw in body_text: formula_score = 6.0
                elif q_raw.lower() in body_text.lower(): formula_score = 2.0

            score = 0.0
            if code_only:
                score += 45.0 * title_boost
                score += 420.0 * early_density
                score += 220.0 * density
                score += 55.0 * tf
                score += 20.0 * front_bonus
            else:
                score += 120.0 * title_boost
                score += 300.0 * early_density
                score += 120.0 * density
                score += 30.0 * tf
                score += 80.0 * front_bonus
                score += formula_score

            if cid in body_ids: score *= 1.03

            scored.append((doc_id, score, title, path, body_text))

        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:limit]

        results =[]
        for doc_id, score, title, path, body_text in top:
            body = body_text or ""
            if code_only:
                code_only_body = _format_code_only_body(body)
                if code_only_body:
                    body = code_only_body
            body = re.sub(r"\n\s*\n", "\n\n", body).strip()
            pat = rf"^\s*{re.escape(title)}\s*[:\-\|]?\s*(\r?\n)+"
            body = re.sub(pat, "", body, flags=re.IGNORECASE)
            body = re.sub(r"\n{3,}", "\n\n", body).lstrip()
            results.append(LocalResult(label, title, body, path))

        return results

    except Exception:
        logger.exception("search_local failed")
        return[]

# ---------------------------------------------------------------------------
# INFO / LIST
# ---------------------------------------------------------------------------

def index_info(source_id: str) -> dict:
    db_path = _source_id_to_db(source_id)
    zim = _find_zim_for_source(source_id)
    info = {"source_id": source_id, "exists": False, "articles": 0, "mode": "Aguardando Build", "zim_path": str(zim) if zim else "?"}
    if db_path.exists():
        try:
            con = sqlite3.connect(db_path)
            info["articles"] = con.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
            info["exists"] = True
            info["mode"] = "SiCDox (Tokenized)" if meta.get("sicdox_ver") else "Texto Puro"
            con.close()
        except Exception: pass
    return info

def list_indexes() -> List[dict]:
    seen, result = set(),[]
    if INDEX_DIR.exists():
        for db_file in sorted(INDEX_DIR.glob("*.db")):
            sid = db_file.stem
            seen.add(sid)
            result.append(index_info(sid))
    if ZIM_DIR.exists():
        for zim_file in sorted(ZIM_DIR.glob("*.zim")):
            sid = _zim_to_source_id(zim_file)
            if sid not in seen:
                result.append({"source_id": sid, "articles": 0, "zim_path": str(zim_file), "mode": "Aguardando Build", "exists": False})
                seen.add(sid)
    return result

# ---------------------------------------------------------------------------
# ZIM header probe / diagnose
# ---------------------------------------------------------------------------

_ZIM_MAGIC = 0x044D495A
_ZIM_HEADER_SIZE = 80

def _read_zim_header(zim_path: str) -> dict:
    with open(zim_path, "rb") as f:
        raw = f.read(_ZIM_HEADER_SIZE)
    if len(raw) < _ZIM_HEADER_SIZE:
        raise ValueError(f"Arquivo muito pequeno ({len(raw)} bytes)")
    magic, major, minor = struct.unpack_from("<IHH", raw, 0)
    if magic != _ZIM_MAGIC:
        raise ValueError(f"Magic inválido: 0x{magic:08X}")
    entry_count, cluster_count = struct.unpack_from("<II", raw, 24)
    return {"version": f"{major}.{minor}", "uuid": raw[8:24].hex(), "entry_count": entry_count, "cluster_count": cluster_count}

def probe_zim(zim_path: str) -> None:
    try:
        info = _read_zim_header(zim_path)
        size_mb = round(Path(zim_path).stat().st_size / 1_048_576, 1)
        print(f"\n  [PROBE] {Path(zim_path).name}")
        print(f"  Versão ZIM:    {info['version']}")
        print(f"  Entradas:      {info['entry_count']:,}")
        print(f"  Clusters:      {info['cluster_count']:,}")
        print(f"  UUID:          {info['uuid']}")
        print(f"  Tamanho:       {size_mb} MB")
    except Exception as e: print(f"[PROBE] FALHOU: {e}")

def diagnose_zim(zim_path: str, n: int = 20) -> None:
    try: import pyzim
    except ImportError:
        print("  pyzim não instalado.")
        return

    print(f"\n[DIAGNOSE] {Path(zim_path).name} — primeiras {n} entradas")
    print(f"  {'#':<4} {'redirect':<10} {'namespace':<12} {'mime':<30} {'content_bytes':<14} {'title'}")
    print(f"  {'-'*100}")

    with pyzim.Zim.open(str(Path(zim_path).absolute()), mode="r") as zim:
        for i, entry in enumerate(zim.iter_entries()):
            if i >= n: break
            is_redir = getattr(entry, "is_redirect", "?")
            ns = getattr(entry, "namespace", "?")
            if isinstance(ns, bytes): ns = ns.decode("utf-8", errors="ignore")
            mime = getattr(entry, "mimetype", None) or getattr(entry, "mime_type", "?")
            if callable(mime): mime = mime()
            if isinstance(mime, bytes): mime = mime.decode("utf-8", errors="ignore")
            title = getattr(entry, "title", "?")
            if isinstance(title, bytes): title = title.decode("utf-8", errors="ignore")
            content = _read_entry_content(entry)
            clen = len(content) if content else 0
            print(f"  {i:<4} {str(is_redir):<10} {str(ns):<12} {str(mime)[:28]:<30} {clen:<14} {str(title)[:40]}")

    print()

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="local_index", description="ORN LocalIndex v6.0 — SiCDox (Semantic Compression)")
    parser.add_argument("--gguf", help="Caminho para o arquivo .gguf (sobe para SICDOX_GGUF)")
    parser.add_argument("--verbose", action="store_true", help="Ativa modo verboso")

    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("probe", help="Ler header do zim")
    b = sub.add_parser("build", help="Construir índice tokenizado")
    b.add_argument("zim", help="Caminho do arquivo .zim")
    b.add_argument("source_id", nargs="?", help="Source ID opcional")
    
    s = sub.add_parser("search", help="Buscar no índice local")
    s.add_argument("source_id", help="Source ID")
    s.add_argument("--code-only", action="store_true", help="Pesquisar apenas em blocos de código fonte (descartando o resto)")
    s.add_argument("query", nargs="+", help="Termos de busca")
    
    i = sub.add_parser("info", help="Informação do índice")
    i.add_argument("source_id", help="Source ID")
    sub.add_parser("list", help="Listar índices e ZIMs disponíveis")
    sub.add_parser("diagnose", help="Diagnose ZIM (primeiras entradas)").add_argument("zim", nargs=1)
    
    p = sub.add_parser("preload", help="Testa o tempo de carregamento do vocab e index na memória RAM")
    p.add_argument("source_id", nargs="?", help="Source ID opcional para cachear DB")

    args = parser.parse_args(argv)

    if args.verbose: logging.getLogger().setLevel(logging.DEBUG)
    if args.gguf: os.environ[_GGUF_PATH_ENV] = args.gguf

    chronos_recorder = None
    try:
        from doxoade.chronos import chronos_recorder
        class FakeCommand: name = f"INDEX-{args.cmd.upper() if args.cmd else 'NONE'}"
        class FakeCtx:
            invoked_subcommand = None
            command = FakeCommand()
            obj = {}
        chronos_recorder.start_command(FakeCtx())
        logger.debug("[TELEMETRY] Chronos Nexus ativado! (Sessão: %s)", chronos_recorder.session_uuid)
    except Exception as e: pass

    exit_code = 0
    t_start_global = time.perf_counter()

    try:
        if args.cmd == "probe": probe_zim(args.zim)
        elif args.cmd == "build":
            build_index(args.zim, source_id=getattr(args, "source_id", None))
            try: GLOBAL_TELEMETRY.flush_json("telemetry/local_index_build.json")
            except Exception: pass
        elif args.cmd == "search":
            q = " ".join(args.query or[])
            results = search_local(q, args.source_id, code_only=getattr(args, "code_only", False))
            elapsed = round((time.perf_counter() - t_start_global) * 1000, 2)
            if not results: print("\n  Nenhum resultado para a busca.")
            else:
                max_chars = int(os.environ.get("SICDOX_SNIPPET_CHARS", "2000"))
                n_snips = int(os.environ.get("SICDOX_SNIPPETS", "3"))
                for r in results:
                    snippet = r.get_snippet(q, max_chars=max_chars, n_snippets=n_snips)
                    rendered_snippet = _format_snippet_for_terminal(snippet)
                    print(f"\n  [{r.source}] {r.title}\n{rendered_snippet}\n  path: {r.path}")
            print(f"\n  Tempo: {elapsed}ms | {len(results)} resultado(s)")
            print("  (DICA: Para velocidade extrema, chame LocalIndexCache.preload() dentro da IA ao invés do CLI)")
        elif args.cmd == "info":
            for k, v in index_info(args.source_id).items(): print(f"  {k:<12}: {v}")
        elif args.cmd == "list":
            for info in list_indexes(): print(f"  {info['source_id']:<45} {info.get('articles', 0):>8}  {info.get('mode', '?')}")
        elif args.cmd == "diagnose":
            diagnose_zim(args.zim[0], n=20)
        elif args.cmd == "preload":
            LocalIndexCache.preload([args.source_id] if args.source_id else[])
            elapsed = round((time.perf_counter() - t_start_global) * 1000, 2)
            print(f"\n[OK] Vocabulário GGUF e Banco(s) montados na RAM com sucesso em {elapsed}ms!")
        else:
            parser.print_help()

    except Exception:
        exit_code = 1
        raise
    finally:
        if chronos_recorder:
            duration_ms = (time.perf_counter() - t_start_global) * 1000
            try: chronos_recorder.end_command(exit_code, duration_ms)
            except Exception: pass

    return exit_code

if __name__ == "__main__":
    raise SystemExit(_cli_main())