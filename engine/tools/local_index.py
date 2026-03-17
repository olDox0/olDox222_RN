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
import html as _html_module

from contextlib import closing
from pathlib import Path
from threading import Lock
from typing import Iterator, List, Optional


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

# Caminho padrão antigo mantido como fallback — preferir definir SICDOX_GGUF
_DEFAULT_GGUF = r"C:\Users\olDox222\Documents\A20251122\DOSSIER\Altonomo\Projetos_E_Programas\Projeto_OIA\olDox222RN\ORN\models\sicdox\Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF\qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
_GGUF_PATH_ENV = "SICDOX_GGUF"

# Regexes melhor definidos — preservam blocos de interesse
_RE_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
# NAV: manter infobox? opcional — deixei para remover apenas 'navbox' e 'mw-toc' mas sem tocar outras tags cruciais
_RE_NAV = re.compile(r'<[^>]*(navbox|mw-toc|mw-jump|sidebar|reflist)[^>]*>.*?</\w+>', re.DOTALL | re.IGNORECASE)

# Tags a preservar (capturamos conteúdo entre tags e substituímos por placeholders)
# preserva: <pre>...</pre>, <code>...</code>, <syntaxhighlight>...</syntaxhighlight>, <math>...</math>, <math-display>...</math-display>
_RE_PRESERVE = re.compile(
    r"(?P<open><(?P<tag>pre|code|syntaxhighlight|math|math-display|source)[^>]*>)(?P<body>.*?)(?P<close></(?P=tag)>)",
    re.DOTALL | re.IGNORECASE,
)

# Tags a remover (mas depois do preserve)
_RE_TAG = re.compile(r"<[^>\n]+>")  # menos agressivo: não atravessa linhas arbitrárias sem '>'
_RE_ENTITY = re.compile(r"&(?:[a-zA-Z]{2,8}|#\d{1,6});")
_RE_MULTI = re.compile(r"[ \t]{2,}")
_RE_NEWL = re.compile(r"\n{3,}")
_RE_URL = re.compile(r"https?://\S+")

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

try:
    from rapidfuzz import fuzz, process as rprocess  # opcional, muito recomendado
    _HAS_RAPIDFUZZ = True
except Exception:
    _HAS_RAPIDFUZZ = False

def _normalize_text_for_match(s: str) -> str:
    """Lower + remove accents + collapse whitespace."""
    if s is None:
        return ""
    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s

def _trigrams_for(s: str) -> set:
    """Return set of character trigrams for string s (with boundary padding)."""
    s = _normalize_text_for_match(s)
    if not s:
        return set()
    s = f"  {s} "  # pad start/end
    tr = set()
    for i in range(len(s) - 2):
        tr.add(s[i : i + 3])
    return tr

def _similarity_ratio(a: str, b: str) -> float:
    """Return similarity [0..1] between two normalized strings."""
    if _HAS_RAPIDFUZZ:
        return fuzz.token_sort_ratio(a, b) / 100.0
    # fallback to difflib.SequenceMatcher
    return difflib.SequenceMatcher(None, a, b).ratio()

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "no", "off")


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

def _clean_body(text: str, max_chars: int = 100_000) -> str:
    """
    Normaliza o body antes de retornar/exibir:
     - remove caracteres de controle
     - normaliza quebras de linha e espaços
     - remove repetições do título no começo (linhas idênticas repetidas)
     - colapsa runs longos de newline para no máximo 2
     - mantém parágrafos intactos ao truncar
    """
    if not text:
        return ""

    # ensure str
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            text = ""

    # remove unicode control chars except \n and \t
    text = "".join(ch for ch in text if (ch >= " " or ch in ("\n", "\t")))

    # normalize newlines and tabs/spaces
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ")

    # trim leading/trailing spaces on each line, but keep empty lines
    lines = [ln.rstrip() for ln in text.split("\n")]

    # Remove leading empty lines
    while lines and lines[0].strip() == "":
        lines.pop(0)

    # If the first non-empty line is short (likely a title/header),
    # remove consecutive repetitions of the same short header at the top.
    if lines:
        first = lines[0].strip()
        if 0 < len(first) <= 120:
            # remove immediate repeated lines equal to first (case-insensitive, ignore punctuation)
            def norm_key(s: str) -> str:
                s2 = re.sub(r"[^\w\s]", "", s or "").strip().lower()
                return s2
            fk = norm_key(first)
            # consume repeated header lines up to a sane limit
            i = 1
            removed = 0
            while i < min(len(lines), 30):  # only check the first 30 lines to avoid O(n^2)
                if norm_key(lines[i]) == fk:
                    lines.pop(i)
                    removed += 1
                    continue
                # also remove if the next line is empty and the following is same header (header + blank + header)
                if lines[i].strip() == "" and i + 1 < len(lines) and norm_key(lines[i + 1]) == fk:
                    # pop the blank and the next header
                    lines.pop(i)     # blank
                    lines.pop(i)     # the repeated header
                    removed += 2
                    continue
                i += 1

    # collapse multiple identical short lines in the top region (e.g., "Chemistry" repeated with blanks)
    # but do this conservatively only for the first ~40 lines
    limit_top = min(len(lines), 40)
    out_top = []
    seen_short = set()
    for ln in lines[:limit_top]:
        key = ln.strip().lower()
        if key and len(key) <= 120:
            if key in seen_short:
                # skip repeated short header
                continue
            seen_short.add(key)
        out_top.append(ln)
    # append the remainder lines unchanged
    rest = lines[limit_top:]
    lines = out_top + rest

    # collapse runs of 3+ newlines to exactly 2
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # remove leading/trailing whitespace
    text = text.strip()

    # Remove stray long sequences of the same character (e.g., many repeated '-') that may be header artifacts
    text = re.sub(r"([\-=_\*])\1{6,}", r"\1\1\1", text)

    # limit total length while preserving paragraph boundaries
    if len(text) > max_chars:
        parts = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        out_parts = []
        total = 0
        for p in parts:
            if total + len(p) + 2 > max_chars and out_parts:
                break
            out_parts.append(p)
            total += len(p) + 2
            if len(out_parts) >= 6:
                break
        text = "\n\n".join(out_parts)
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "..."

    return text
    

# ---------------------------------------------------------------------------
# HTML cleaning / helpers
# ---------------------------------------------------------------------------

# Substitua a função _strip_html existente por esta.
_RE_CODE = re.compile(
    r"(?P<open><(?P<tag>pre|code|script)(?P<attrs>[^>]*)>)(?P<body>.*?)(?P<close></(?P=tag)>)",
    re.DOTALL | re.IGNORECASE,
)

def _extract_code_blocks(html: str) -> tuple[str, list[tuple[str, str]]]:
    """
    Extrai blocos de código (pre, code, script) e os substitui por placeholders.
    Retorna (html_with_placeholders, list_of_code_blocks)
    cada code block -> (placeholder, code_text_with_optional_lang)
    """
    code_blocks = []
    out_html = []
    last = 0
    idx = 0
    for m in _RE_CODE.finditer(html):
        start, end = m.span()
        tag = m.group("tag").lower()
        attrs = m.group("attrs") or ""
        body = m.group("body") or ""
        # Do not lose &lt; &gt; in code: keep body as-is (no entity unescape)
        # try to detect language from class or data-lang
        lang = ""
        cls_m = re.search(r'class=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        if cls_m:
            cls = cls_m.group(1)
            # typical patterns: language-python, lang-python, brush:python
            lm = re.search(r"(?:lang|language|language-|(brush:)|(?:language:))?([a-zA-Z0-9_+-]+)", cls)
            if lm:
                # take last token that looks like a language
                parts = re.split(r"[^\w+-]+", cls)
                for p in parts[::-1]:
                    if len(p) <= 20 and re.match(r"^[a-zA-Z0-9_+-]+$", p):
                        lang = p.lower()
                        break
        data_lang = re.search(r'data-lang=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        if data_lang:
            lang = data_lang.group(1).lower()
        # placeholder
        ph = f"__CODE_BLOCK_{idx}__"
        code_text = body
        # If HTML-escaped inside (e.g., &lt;), we leave as-is; tokeniser will handle.
        code_repr = f"```{lang}\n{code_text}\n```"
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

def _strip_html(html: str, max_chars: int = 8000) -> str:
    """
    Limpeza avançada que preserva blocos de código.
    - extrai code/pre/script em placeholders;
    - remove nav/infobox/style tags e outras tags HTML;
    - preserva entidades dentro de code blocks;
    - restaura code blocks como fenced code (```lang\n...\n```).
    """
    if not html:
        return ""

    # 1) extrair blocos de código preservando seu conteúdo
    extracted_html, code_blocks = _extract_code_blocks(html)

    # 2) remover blocos de navegação/infobox que poluem
    text = _RE_NAV.sub(" ", extracted_html)

    # 3) remover apenas <style> (mantemos scripts/code extracted above)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)

    # 4) remover tags restantes (mas placeholders permanecem)
    text = _RE_TAG.sub(" ", text)

    # 5) não destruir conteúdo dos code blocks com entity removal - as entidades fora de code podem ser simplificadas
    # primeiro capturar e preservar placeholders (eles são alfanuméricos com underscores)
    # então aplicamos entity/substitutions no restante
    text = _RE_ENTITY.sub(" ", text)
    text = _RE_URL.sub(" ", text)
    text = _RE_MULTI.sub(" ", text)
    text = _RE_NEWL.sub("\n\n", text).strip()

    # 6) restaurar blocos de código convertendo placeholders para fences
    if code_blocks:
        text = _restore_code_placeholders(text, code_blocks)

    # 7) limitar tamanho final
    return text[:max_chars]


# ---------------------------------------------------------------------------
# Compression helpers (pyzstd optional)
# ---------------------------------------------------------------------------

def _compress(data: bytes) -> bytes:
    """
    Retorna blob com um byte de formato:
      b'\\x00' + raw_payload  -> não comprimido
      b'\\x01' + zstd_payload -> comprimido (pyzstd disponível)
    """
    try:
        import pyzstd
        compressed = pyzstd.compress(data)
        return b"\x01" + compressed
    except Exception:
        logger.debug("pyzstd unavailable; storing raw payload (flag 0)")
        return b"\x00" + data


def _decompress(data: bytes) -> bytes:
    """
    Interpreta o primeiro byte de flag e devolve os bytes payload (descomprimidos
    quando necessário). Não devolve dados comprimidos cru.
    """
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
            logger.exception("_decompress: pyzstd present at build but missing at runtime")
            # NÃO retornar payload comprimido — em vez disso sinalizamos erro
            raise RuntimeError("Unable to decompress zstd payload: pyzstd missing or decompression failed")
    # fallback: se não reconhecido, tentar heurística segura
    logger.warning("_decompress: unknown format flag %r; attempting to detect zstd magic", flag)
    if len(data) >= 5 and data[1:5] == b"\x28\xb5\x2f\xfd":
        try:
            import pyzstd
            return pyzstd.decompress(payload)
        except Exception:
            raise RuntimeError("Unknown blob format and pyzstd unavailable")
    # último recurso: devolver como-is (não ideal)
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
            logger.debug("_read_entry_content: method %s failed", method, exc_info=True)
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
    """Singleton leve que carrega apenas o vocab (vocab_only=True).
    Fornecer o caminho do GGUF via variável de ambiente SICDOX_GGUF é recomendado.
    """

    _llm_vocab = None
    _lock = Lock()

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
                    logger.info("Carregando vocab_only do GGUF: %s", gguf)
                    cls._llm_vocab = Llama(model_path=gguf, vocab_only=True, verbose=False)
        return cls._llm_vocab

    @classmethod
    def text_to_bytes(cls, text: str) -> bytes:
        vocab = cls.get_vocab()
        tokens = vocab.tokenize(text.encode("utf-8"), add_bos=False)
        return array.array("i", tokens).tobytes()

    @classmethod
    def bytes_to_text(cls, data: bytes) -> str:
        # data expected to be token-array-bytes (length %4==0) after decompression.
        if not data:
            return ""
        if len(data) % 4 != 0:
            # Não tentar decodificar comprimido ou corrompido como UTF-8 sem avisar.
            logger.warning("bytes_to_text: data length %d not multiple of 4 — possible corrupted/compressed blob", len(data))
            try:
                # tentativa cuidadosa: devolve texto legível como fallback
                return data.decode("utf-8", errors="ignore")
            except Exception:
                return ""
        try:
            vocab = cls.get_vocab()
            arr = array.array("i")
            arr.frombytes(data)
            tokens = arr.tolist()
            if tokens and (max(tokens) >= vocab.n_vocab() or min(tokens) < 0):
                logger.warning("bytes_to_text: token ids outside vocab range; returning fallback decode")
                return data.decode("utf-8", errors="ignore")
            return vocab.detokenize(tokens).decode("utf-8", errors="ignore")
        except Exception:
            logger.exception("bytes_to_text failed; returning raw decode")
            return data.decode("utf-8", errors="ignore")


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
        """
        Retorna até `n_snippets` trechos relevantes com no máximo `max_chars` chars
        no total. Se query vazia ou não encontrada, devolve os primeiros max_chars do body.
        Mantém e preserva marcadores [CODE-BEGIN] / [MATH-BEGIN] se existirem.
        """
        if not self.ok:
            return ""
        text = self.body
        if not text:
            return ""

        # normalize search tokens (simple words)
        q = (query or "").strip()
        if q:
            qlower = q.lower()
            # localizar todas ocorrências de palavras (fallback: substring)
            positions = []
            # procura por palavras longas primeiro
            words = [w for w in re.findall(r"[A-Za-z0-9_]{2,}", qlower)]
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
                # fallback substring
                idx = text.lower().find(qlower)
                if idx != -1:
                    positions.append(idx)

            # dedupe and sort
            positions = sorted(set(positions))

            if positions:
                snippets = []
                used = 0
                # escolher até n_snippets janelas em torno das posições (evitar sobreposição)
                for pos in positions:
                    if len(snippets) >= n_snippets:
                        break
                    # janela:  start..end
                    left = max(0, pos - 120)   # 120 chars antes
                    right = min(len(text), pos + 420)  # 420 after -> ~540 window
                    # evitar sobreposição com snippet anterior
                    if snippets and left < snippets[-1][1]:
                        left = snippets[-1][1] + 1
                    snippets.append((left, right))
                    used += (right - left)

                # juntar snippets respeitando max_chars
                out_parts = []
                total = 0
                for left, right in snippets:
                    part = text[left:right].strip()
                    # garantir que não corte código markers no meio
                    # se começa dentro de [CODE-BEGIN], expandir até [CODE-END]
                    if "[CODE-BEGIN" in part and "[CODE-END]" not in part:
                        # expand to next code end
                        end_idx = text.find("[CODE-END]", right)
                        if end_idx != -1:
                            part = text[left:end_idx + len("[CODE-END]")]
                    # similar for math markers
                    if "[MATH-BEGIN]" in part and "[MATH-END]" not in part:
                        end_idx = text.find("[MATH-END]", right)
                        if end_idx != -1:
                            part = text[left:end_idx + len("[MATH-END]")]
                    # highlight query occurrences (simple)
                    if q:
                        try:
                            # highlight words from `words`, wrap in ** **
                            for w in words:
                                # case-preserving replace: use regex with IGNORECASE
                                part = re.sub(rf"(?i)\b{re.escape(w)}\b", lambda m: f"**{m.group(0)}**", part)
                        except Exception:
                            pass
                    # append with ellipses
                    if left > 0:
                        part = "..." + part
                    if right < len(text):
                        part = part + "..."
                    out_parts.append(part)
                    total += len(part)
                    if total >= max_chars:
                        break

                # fallback: no occurrences found -> return first N paragraphs (more context)
                paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
                if not paras:
                    return ""
                # escolha até 3 parágrafos que caibam em max_chars
                out = []
                total = 0
                for p in paras[:6]:  # olhar até 6 parágrafos, pegar os melhores 1-3
                    if total + len(p) + 2 > max_chars and out:
                        break
                    out.append(p)
                    total += len(p) + 2
                    if len(out) >= 3:
                        break
                snippet = "\n\n".join(out)
                if len(snippet) > max_chars:
                    snippet = snippet[:max_chars].rstrip() + "..."
                return snippet

        # fallback: no occurrences found -> return the leading context (preserving code/math markers)
        leading = text[:max_chars]
        # try to avoid cutting inside markers: if we cut inside [CODE-BEGIN], extend until [CODE-END] or trim to last newline
        if "[CODE-BEGIN" in leading and "[CODE-END]" not in leading:
            end_idx = text.find("[CODE-END]")
            if end_idx != -1 and end_idx < max_chars * 3:
                # append until code end (within reason)
                leading = text[: end_idx + len("[CODE-END]")]
        # normalize spaces/newlines
        leading = leading.strip()
        if len(leading) < len(text):
            leading = leading + "..."
        return leading

    def to_prompt_block(self, max_chars: int = 600, query: str = "") -> str:
        if not self.ok:
            return ""
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
            if _zim_to_source_id(zim) == source_id:
                return zim
    return None


def _iter_zim_entries(zim_path: str, verbose: bool = True) -> Iterator[tuple[str, str, str]]:
    import pyzim

    p = Path(zim_path).absolute()

    total_scanned = total_yielded = total_redirect = 0
    total_non_html = total_empty = total_error = 0

    with pyzim.Zim.open(str(p), mode="r") as zim:
        for entry in zim.iter_entries():
            total_scanned += 1

            if verbose and total_scanned % 5000 == 0:
                logger.info(
                    "[ZIM] scanned=%d yielded=%d redirect=%d non_html=%d empty=%d",
                    total_scanned,
                    total_yielded,
                    total_redirect,
                    total_non_html,
                    total_empty,
                )

            if getattr(entry, "is_redirect", False):
                total_redirect += 1
                continue

            ns = getattr(entry, "namespace", None)
            if ns is not None:
                if isinstance(ns, bytes):
                    ns = ns.decode("utf-8", errors="ignore")
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
                b"<html" in head
                or b"<!doctype" in head
                or b"<body" in head
                or b"<p" in head
                or b"<div" in head
                or b"<h1" in head
                or b"<h2" in head
                or content_bytes[:1] == b"<"
            )
            if not is_html:
                total_non_html += 1
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

                content = content_bytes.decode("utf-8", errors="replace")
                total_yielded += 1
                yield title, path, content

            except Exception:
                total_error += 1
                logger.debug("Error parsing zim entry", exc_info=True)
                continue

    if verbose:
        logger.info(
            "[ZIM] total: scanned=%d yielded=%d redirect=%d non_html=%d empty=%d error=%d",
            total_scanned,
            total_yielded,
            total_redirect,
            total_non_html,
            total_empty,
            total_error,
        )


# ---------------------------------------------------------------------------
# BUILD INDEX
# ---------------------------------------------------------------------------

def build_index(zim_path: str, source_id: Optional[str] = None, batch_size: int = 1000, verbose: bool = True) -> Path:
    try:
        import pyzim  # noqa: F401
    except ImportError:
        raise ImportError("pyzim não instalado. pip install pyzim")

    zim_path = str(zim_path)
    if not Path(zim_path).exists():
        raise FileNotFoundError(f"ZIM não encontrado: {zim_path}")

    # Garante que o vocab seja carregado no início (pode lançar FileNotFoundError)
    TokenizerBridge.get_vocab()

    if source_id is None:
        source_id = _zim_to_source_id(zim_path)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    db_path = str(_source_id_to_db(source_id))

    # --- Remover DB / índice existente para garantir rebuild limpo ---
    try:
        db_p = Path(db_path)
        inv_dir = INDEX_DIR / source_id
        if db_p.exists():
            logger.info("[SiCDox BUILD] DB existente encontrado, removendo para rebuild: %s", db_path)
            # fechar handles não é possível aqui (esperamos que nenhum processo esteja usando),
            # removemos arquivos sqlite auxiliares também (wal/shm).
            for suf in ("", "-wal", "-shm"):
                f = db_p.with_name(db_p.name + suf)
                try:
                    if f.exists():
                        f.unlink()
                except Exception:
                    logger.warning("Não foi possível remover %s (continuando)", f, exc_info=True)
        # remove índice invertido antigo se existir
        if inv_dir.exists():
            logger.info("[SiCDox BUILD] Removendo diretório de índice invertido anterior: %s", inv_dir)
            try:
                # usar rmtree para remover diretório recursivamente
                import shutil

                shutil.rmtree(inv_dir)
            except Exception:
                logger.warning("Falha ao remover índice invertido %s (continuando)", inv_dir, exc_info=True)
    except Exception:
        logger.exception("Erro ao tentar remover DB/índice existente; prosseguindo com build")

    if verbose:
        logger.info("[SiCDox BUILD] Construindo Banco Tokenizado... DB: %s", db_path)

    inv_builder = InvertedIndexBuilder()
    t0 = time.monotonic()

    con = sqlite3.connect(db_path, isolation_level=None)
    try:
        con.execute("PRAGMA page_size=4096")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        # cache_size is in pages; use negative value to specify KB units (e.g. -20000 ~ 20MB depending on page_size)
        try:
            con.execute("PRAGMA cache_size = -20000")
        except Exception:
            pass

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

        # Optional index for faster joins
        con.execute("CREATE INDEX IF NOT EXISTS idx_pages_hash ON pages(content_hash)")

        # table for title trigrams (for fuzzy title search)
        con.execute("""
        CREATE TABLE IF NOT EXISTS title_trigrams (
            trigram TEXT,
            doc_id INTEGER
        )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_title_trigrams_trigram ON title_trigrams(trigram)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_title_trigrams_doc ON title_trigrams(doc_id)")

        con.execute("BEGIN")
        # Preparações para otimização:
        # - carrega vocab UMA vez antes do loop
        # - reduz max chars tokenizados para diminuir custo
        vocab = TokenizerBridge.get_vocab()
        MAX_TOKENIZE_CHARS = int(os.environ.get("SICDOX_MAX_CHARS", "4000"))

        count = deduplicated = 0
        buf_pages: List[tuple] = []
        seen_hashes = set()
        # Buffer para writes em batch do content_pool: mapa hash->blob
        content_pending: dict[str, bytes] = {}
        CONTENT_FLUSH_BATCH = int(os.environ.get("SICDOX_CONTENT_BATCH", "256"))

        def _flush_content_pending():
            """Insere em bulk o que estiver pendente no content_pool e limpa o buffer."""
            nonlocal content_pending
            if not content_pending:
                return
            items = list(content_pending.items())
            with orn_span("build.sql_insert", category="index"):
                try:
                    # executemany em lote para reduzir overhead
                    con.executemany("INSERT OR IGNORE INTO content_pool (hash, token_blob) VALUES (?, ?)", items)
                except Exception:
                    # fallback item-a-item se algo falhar (mais lento, mas resiliente)
                    logger.debug("bulk insert failed; falling back to single inserts", exc_info=True)
                    for k, v in items:
                        try:
                            con.execute("INSERT OR IGNORE INTO content_pool (hash, token_blob) VALUES (?, ?)", (k, v))
                        except Exception:
                            logger.debug("failed single insert for %s", k, exc_info=True)
            content_pending = {}

        for title, path, html in _iter_zim_entries(zim_path, verbose=verbose):
            with orn_span("build.strip_html", category="index"):
                body = _strip_html(html, max_chars=MAX_TOKENIZE_CHARS)

            if len(body.strip()) < 50:
                continue

            with orn_span("build.tokenize", category="index"):
                try:
                    # tokeniza o corpo e o título (título terá peso maior no índice)
                    body_bytes = body.encode("utf-8")
                    qtoks = vocab.tokenize(body_bytes, add_bos=False)  # lista de ints
                    title_bytes = title.encode("utf-8")
                    ttoks = vocab.tokenize(title_bytes, add_bos=False)
                    # payload armazenado no content_pool: apenas tokens do corpo (economiza espaço)
                    body_arr = array.array("i", qtoks)
                    payload = body_arr.tobytes()
                except Exception:
                    logger.debug("tokenize failed for title=%s", title, exc_info=True)
                    continue

                h = hashlib.md5(payload).hexdigest()

            if h not in seen_hashes:
                seen_hashes.add(h)
                with orn_span("build.zstd_compress", category="index"):
                    compressed = _compress(payload)

                # acumula em memória e escreve em bloco quando atingir CONTENT_FLUSH_BATCH
                content_pending[h] = compressed
                if len(content_pending) >= CONTENT_FLUSH_BATCH:
                    _flush_content_pending()
            else:
                deduplicated += 1

            count += 1
            buf_pages.append((count, title, path, h))
            
            # accumulate title trigrams for this doc
            tnorm = _normalize_text_for_match(title)
            trigs = _trigrams_for(tnorm)
            # buffer inserts into in-memory list for batch insert later
            if "title_trigrams_pending" not in locals():
                title_trigrams_pending = []
            for tg in trigs:
                title_trigrams_pending.append((tg, count))

            # flush periodically (same batch timing)
            if len(title_trigrams_pending) >= 2000:
                with orn_span("build.sql_insert_trigrams", category="index"):
                    con.executemany("INSERT INTO title_trigrams (trigram, doc_id) VALUES (?, ?)", title_trigrams_pending)
                title_trigrams_pending = []

            # Para melhorar relevância, duplicamos tokens do título ao passar ao inverted index
            # (aumenta peso de termos que aparecem no título)
            try:
                combined_tokens = ttoks + ttoks + qtoks  # título tem peso 2
            except Exception:
                combined_tokens = qtoks

            with orn_span("build.inverted_idx", category="index"):
                inv_builder.add_document(count, combined_tokens)

            if len(buf_pages) >= batch_size:
                with orn_span("build.sql_commit", category="index"):
                    con.executemany("INSERT INTO pages (id, title, path, content_hash) VALUES (?,?,?,?)", buf_pages)
                    _flush_content_pending()
                    con.execute("COMMIT")
                    con.execute("BEGIN")
                    buf_pages.clear()
                if verbose:
                    logger.info("[BUILD] %d artigos tokenizados...", count)

        if buf_pages:
            con.executemany("INSERT INTO pages (id, title, path, content_hash) VALUES (?,?,?,?)", buf_pages)
        # flush any remaining title trigram pending
        if 'title_trigrams_pending' in locals() and title_trigrams_pending:
            con.executemany("INSERT INTO title_trigrams (trigram, doc_id) VALUES (?, ?)", title_trigrams_pending)
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

    inv_builder.finalize()
    inv_dir = INDEX_DIR / source_id
    inv_builder.write(inv_dir)

    if verbose:
        logger.info("[BUILD] Concluído: %d matrizes (Dedup: %d) em %.1fs", count, deduplicated, time.monotonic() - t0)

    return Path(db_path)

# ---------------------------------------------------------------------------
# SEARCH LOCAL
# ---------------------------------------------------------------------------

def _simple_query_tokens(text: str) -> list[int]:
    # Fallback rápido: hash de n-grams ou bytes simples
    # NOTE: não compatível 1:1 com tokens do GGUF, mas dá resultados rápidos
    # Implementação simples: split por palavras e use hash modulo 2^31
    toks = []
    for w in re.findall(r"[A-Za-z0-9]+", text.lower()):
        h = int(hashlib.md5(w.encode("utf-8")).hexdigest()[:8], 16)
        toks.append(h & 0x7fffffff)
    return toks

def _fuzzy_title_search(con: sqlite3.Connection, query: str, candidate_limit: int = 30, final_limit: int = 10):
    """Retorna lista ordenada de doc_ids por similaridade/title-overlap."""
    qnorm = _normalize_text_for_match(query)
    trigs = list(_trigrams_for(qnorm))
    if not trigs:
        return []

    # busca candidatos por overlap de trigramas (fast, via SQL aggregate)
    # nota: usar parâmetros com lista -> construímos placeholders
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
    if not rows:
        return []

    candidates = [r[0] for r in rows]
    # fetch titles for candidates
    rows2 = con.execute(f"SELECT id, title FROM pages WHERE id IN ({','.join('?' for _ in candidates)})", candidates).fetchall()
    title_map = {r[0]: r[1] for r in rows2}

    scored = []
    for doc_id in candidates:
        title = title_map.get(doc_id, "")
        score = _similarity_ratio(qnorm, _normalize_text_for_match(title))
        # boost exact/prefix matches
        tnorm = _normalize_text_for_match(title)
        if tnorm == qnorm:
            score += 0.6
        elif tnorm.startswith(qnorm):
            score += 0.35
        scored.append((doc_id, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [doc_id for doc_id, _ in scored[:final_limit]]

def search_local(query: str, source_id: str, limit: int = 3) -> List[LocalResult]:
    if not query.strip():
        return []

    db_path = str(_source_id_to_db(source_id))
    if not Path(db_path).exists():
        return []

    t_start = time.perf_counter()
    label = f"{source_id}-local"

    try:
        con = sqlite3.connect(db_path, check_same_thread=False)
        con.execute("PRAGMA query_only=1")
        results: List[LocalResult] = []
        doc_ids: List[int] = []

        inv_dir = INDEX_DIR / source_id
        if inv_dir.exists():
            # --- obter candidatos via inverted index (body) e fuzzy title (title) ---
                # --- obter candidatos via inverted index (body) e fuzzy title (title) ---
                candidates = []
                body_ids: list[int] = []

                # Normalize once
                q_raw = query.strip()
                qnorm = _normalize_text_for_match(q_raw)

                # 0) título exato (mais rápido e decisivo) -> se encontrar, retorna imediatamente
                try:
                    row = con.execute("SELECT p.id, p.title, p.path, c.token_blob FROM pages p JOIN content_pool c ON p.content_hash = c.hash WHERE LOWER(p.title) = ? LIMIT 1", (qnorm,)).fetchone()
                    if row:
                        doc_id, title, path, blob = row
                        try:
                            decompressed = _decompress(blob)
                            body = TokenizerBridge.bytes_to_text(decompressed)
                        except Exception:
                            body = ""
                        # retorno imediato com o artigo exato no topo
                        res = LocalResult(label, title, (body[len(title):].strip() if body.lower().startswith(title.lower()) else body), path)
                        con.close()
                        return [res]
                except Exception:
                    # não fatal — continuar com o fluxo normal
                    logger.debug("exact title lookup failed", exc_info=True)

                # Detecta queries que parecem fórmulas químicas (ex.: CH4, H2O, C6H6, subscripts removed)
                _formula_like = bool(re.search(r"[A-Za-z].*\d|\d", q_raw)) and len(q_raw) <= 12  # heurística curta

                # 1) tentar candidates pelo inverted index (body)
                try:
                    with InvertedIndexSearcher(inv_dir) as searcher:
                        if _env_bool("SICDOX_FAST_MODE"):
                            query_tokens = _simple_query_tokens(query)
                        else:
                            vocab = TokenizerBridge.get_vocab()
                            query_tokens = vocab.tokenize(query.encode("utf-8"), add_bos=False)
                        body_ids = searcher.search(query_tokens, limit=80) or []
                        candidates.extend(body_ids)
                except Exception:
                    logger.debug("Inverted index search failed; continuing", exc_info=True)

                # 2) title quick matches (exact/prefix/contains) — fast SQL
                q_esc = _like_escape(q_raw)
                exact = q_raw
                starts = f"{q_esc}%"
                contains = f"%{q_esc}%"
                try:
                    rows = con.execute(
                        "SELECT p.id FROM pages p WHERE p.title = ? OR p.title LIKE ? ESCAPE '\\' OR p.title LIKE ? ESCAPE '\\' LIMIT ?",
                        (exact, starts, contains, 80),
                    ).fetchall()
                    title_ids_quick = [r[0] for r in rows]
                except Exception:
                    title_ids_quick = []

                # 3) if no quick title hits, try fuzzy trigram
                if not title_ids_quick:
                    try:
                        title_ids_quick = _fuzzy_title_search(con, q_raw, candidate_limit=200, final_limit=60)
                    except Exception:
                        title_ids_quick = []

                # union candidates keeping order (body first, then title)
                for tid in title_ids_quick:
                    if tid not in candidates:
                        candidates.append(tid)

                if not candidates:
                    # nothing found
                    con.close()
                    return []

                # --- fetch candidate blobs in one query ---
                placeholders = ",".join("?" for _ in candidates)
                rows = con.execute(
                    f"SELECT p.id, p.title, p.path, c.token_blob FROM pages p JOIN content_pool c ON p.content_hash = c.hash WHERE p.id IN ({placeholders})",
                    candidates,
                ).fetchall()
                row_map = {r[0]: r for r in rows}

                # prepare query token set (if tokenized)
                qtoken_set = set(int(t) for t in (query_tokens or []))

                scored = []
                for cid in candidates:
                    r = row_map.get(cid)
                    if not r:
                        continue
                    doc_id, title, path, blob = r

                    # tenta extrair tokens (lista de ints) e texto detokenizado
                    tokens = None
                    body_text = ""
                    try:
                        decompressed = _decompress(blob)
                        arr = array.array("i")
                        arr.frombytes(decompressed)
                        tokens = arr.tolist()
                        body_text = TokenizerBridge.bytes_to_text(decompressed)
                        
                        body_text = _clean_body(body_text, max_chars=50_000)
                        # se começou com title, remova
                        if body_text.lower().startswith(title.lower()):
                            body_text = re.sub(rf"^{re.escape(title)}\s*", "", body_text, flags=re.IGNORECASE).lstrip()
                    except Exception:
                        # fallback: tentar decodificar bruto para texto
                        try:
                            body_text = TokenizerBridge.bytes_to_text(_decompress(blob))
                        except Exception:
                            body_text = ""

                    # sinais a extrair
                    dl = max(1, len(tokens) if tokens is not None else max(1, len(body_text.split())))
                    if tokens is not None:
                        positions = [i for i, tok in enumerate(tokens) if tok in qtoken_set]
                        tf = len(positions)
                        early_window = min(200, max(20, dl // 8))
                        early_tf = sum(1 for p in positions if p < early_window)
                        first_pos = min(positions) if positions else None
                    else:
                        # substring heuristic counts (word-level)
                        words = [w for w in re.findall(r"[A-Za-z0-9]+", body_text.lower())]
                        qwords = [w for w in re.findall(r"[A-Za-z0-9]+", q_raw.lower())]
                        tf = sum(body_text.lower().count(w) for w in qwords if len(w) > 0)
                        early_tf = sum(body_text[:400].lower().count(w) for w in qwords if len(w) > 0)
                        positions = []
                        first_pos = 0 if early_tf > 0 else None

                    # title signals
                    tnorm = _normalize_text_for_match(title)
                    title_boost = 0.0
                    if tnorm == qnorm:
                        title_boost = 3.0
                    elif tnorm.startswith(qnorm):
                        title_boost = 1.8
                    else:
                        title_sim = _similarity_ratio(qnorm, tnorm)
                        title_boost = 0.9 * title_sim

                    # body signals
                    density = tf / dl
                    early_density = early_tf / max(1, dl)
                    front_bonus = 1.0 if early_tf > 0 and (positions and min(positions) < max(10, dl // 20)) else 0.0

                    # special handling for formula-like queries: substring match priority
                    formula_score = 0.0
                    if _formula_like and body_text:
                        # case-sensitive substring check first (chemical formulas are case-sensitive-ish)
                        if q_raw in body_text:
                            formula_score = 6.0
                        elif q_raw.lower() in body_text.lower():
                            formula_score = 2.0

                    # combine signals into final score (weights tuned to favor title and early mentions)
                    score = 0.0
                    score += 120.0 * title_boost        # strong bias to title matches
                    score += 300.0 * early_density      # emphasize appearances at start
                    score += 120.0 * density            # normalized frequency in document
                    score += 30.0 * tf                  # raw tf small bonus
                    score += 80.0 * front_bonus         # very early occurrence bonus
                    score += formula_score              # formula special boost

                    # boost small: if candidate came from inverted body search, keep slight preference
                    if cid in body_ids:
                        score *= 1.03

                    scored.append((doc_id, score, title, path, body_text))

                # sort & limit
                scored.sort(key=lambda x: x[1], reverse=True)
                top = scored[:limit]

                # build results
                results = []
                for doc_id, score, title, path, body_text in top:
                    body = body_text or ""
                    body = re.sub(r"\n\s*\n", "\n\n", body).strip()
                    # safer remove of leading title + following separators/newlines
                    pat = rf"^\s*{re.escape(title)}\s*[:\-\|]?\s*(\r?\n)+"
                    body = re.sub(pat, "", body, flags=re.IGNORECASE)
                    # collapse remaining repeated blank lines
                    body = re.sub(r"\n{3,}", "\n\n", body).lstrip()
                    results.append(LocalResult(label, title, body, path))

                con.close()
                if _env_bool("VULCAN_TELEMETRY"):
                    logger.info("[VULCAN PROFILER] search_semantic(%s) C++ ZSTD: %.2fms", source_id, (time.perf_counter() - t_start) * 1000)
                return results

        for doc_id in doc_ids:
            row = con.execute(
                "SELECT p.title, p.path, c.token_blob FROM pages p JOIN content_pool c ON p.content_hash = c.hash WHERE p.id = ?",
                (doc_id,),
            ).fetchone()
            if row:
                title, path, blob = row
                try:
                    decompressed_bytes = _decompress(blob)
                except RuntimeError as e:
                    logger.warning("search_local: skipping doc %s due to decompression error: %s", doc_id, e)
                    continue
                body = TokenizerBridge.bytes_to_text(decompressed_bytes)
                if not body.strip():
                    # try fallback: if we have raw_html stored (content_raw) decode it; otherwise attempt to read ZIM entry
                    try:
                        # try to read raw content_pool raw_html table if present
                        row2 = con.execute("SELECT raw_html FROM content_raw WHERE hash = (SELECT content_hash FROM pages WHERE id = ?)", (doc_id,)).fetchone()
                        if row2 and row2[0]:
                            raw = row2[0]
                            # if stored compressed, use _decompress convention or decode
                            try:
                                raw_txt = _decompress(raw)
                                body = raw_txt.decode("utf-8", errors="replace")
                            except Exception:
                                body = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
                    except Exception:
                        pass

                if len(body.strip()) < 40:
                    logger.warning("SHORT_BODY id=%s title=%s body_len=%d blob_len=%d", doc_id, title, len(body), len(blob) if blob else 0)

                if not body.strip():
                    logger.debug("search_local: doc %s produced empty body after decode; skipping", doc_id)
                    continue

                # Normaliza e limpa excessos de newlines/whitespace antes de armazenar
                body = _clean_body(body, max_chars=50_000)

                # Se o body começa com o título repetido, remova o prefixo redundante
                if body.lower().startswith(title.lower()):
                    # tente remover apenas a primeira ocorrência e limpar espaços sobrando
                    body = re.sub(rf"^{re.escape(title)}\s*", "", body, flags=re.IGNORECASE).lstrip()

                results.append(LocalResult(label, title, body, path))

        con.close()
        if _env_bool("VULCAN_TELEMETRY"):
            logger.info("[VULCAN PROFILER] search_semantic(%s) C++ ZSTD: %.2fms", source_id, (time.perf_counter() - t_start) * 1000)
        return results

    except Exception:
        logger.exception("search_local failed")
        return []


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
        except Exception:
            logger.debug("index_info failed for %s", source_id, exc_info=True)
    return info


def list_indexes() -> List[dict]:
    seen, result = set(), []
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
    except Exception as e:
        print(f"  [PROBE] FALHOU: {e}")


def diagnose_zim(zim_path: str, n: int = 20) -> None:
    try:
        import pyzim
    except ImportError:
        print("  pyzim não instalado.")
        return

    print(f"\n  [DIAGNOSE] {Path(zim_path).name} — primeiras {n} entradas")
    print(f"  {'#':<4} {'redirect':<10} {'namespace':<12} {'mime':<30} {'content_bytes':<14} {'title'}")
    print(f"  {'-'*100}")

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
            clen = len(content) if content else 0
            chead = ""
            if content:
                chead = content[:60].replace(b"\n", b" ").decode("utf-8", errors="ignore")
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
    s.add_argument("query", nargs=argparse.REMAINDER, help="Termos de busca")
    i = sub.add_parser("info", help="Informação do índice")
    i.add_argument("source_id", help="Source ID")
    sub.add_parser("list", help="Listar índices e ZIMs disponíveis")
    sub.add_parser("diagnose", help="Diagnose ZIM (primeiras entradas)").add_argument("zim", nargs=1)

    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.gguf:
        os.environ[_GGUF_PATH_ENV] = args.gguf

    # Chronos (opcional)
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
        logger.info("[TELEMETRY] Chronos Nexus ativado! (Sessão: %s)", chronos_recorder.session_uuid)
    except Exception as e:
        logger.debug("Chronos não iniciado: %s", e)

    exit_code = 0
    t_start_global = time.perf_counter()

    try:
        if args.cmd == "probe":
            probe_zim(args.zim)
        elif args.cmd == "build":
            build_index(args.zim, source_id=getattr(args, "source_id", None))
            try:
                GLOBAL_TELEMETRY.flush_json("telemetry/local_index_build.json")
                logger.info("[TELEMETRY] ORN Spans salvos em telemetry/local_index_build.json")
            except Exception:
                logger.debug("Não foi possível salvar GLOBAL_TELEMETRY", exc_info=True)
        elif args.cmd == "search":
            q = " ".join(args.query or [])
            results = search_local(q, args.source_id)
            elapsed = round((time.perf_counter() - t_start_global) * 1000, 2)
            if not results:
                print("\n  Nenhum resultado para a busca.")
            else:
                # tamanho de snippet via env (padrão 1200)
                max_chars = int(os.environ.get("SICDOX_SNIPPET_CHARS", "1200"))
                n_snips = int(os.environ.get("SICDOX_SNIPPETS", "3"))
                for r in results:
                    snippet = r.get_snippet(q, max_chars=max_chars, n_snippets=n_snips)
                    print(f"\n  [{r.source}] {r.title}\n{snippet}\n  path: {r.path}")
            print(f"\n  Tempo: {elapsed}ms | {len(results)} resultado(s)")
        elif args.cmd == "info":
            for k, v in index_info(args.source_id).items():
                print(f"  {k:<12}: {v}")
        elif args.cmd == "list":
            for info in list_indexes():
                print(f"  {info['source_id']:<45} {info.get('articles', 0):>8}  {info.get('mode', '?')}")
        elif args.cmd == "diagnose":
            diagnose_zim(args.zim[0], n=20)
        else:
            parser.print_help()

    except Exception as e:
        exit_code = 1
        logger.exception("CLI command failed")
        raise

    finally:
        if chronos_recorder:
            duration_ms = (time.perf_counter() - t_start_global) * 1000
            try:
                chronos_recorder.end_command(exit_code, duration_ms)
                logger.info("[TELEMETRY] Dados gravados no banco de auditoria Doxoade.")
            except Exception:
                logger.debug("Erro ao salvar log do Chronos", exc_info=True)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(_cli_main())
