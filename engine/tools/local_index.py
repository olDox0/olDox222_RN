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
    _doxo_t = _doxo_time.monotonic()   # inicializado ANTES do if — evita NameError no finally
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
                        # sys.intern no sufixo — a comparação endswith é feita N_módulos×N_attrs vezes
                        _vulcan_suffix = _d_sys.intern("_vulcan_optimized")
                        _suffix_len    = len(_vulcan_suffix)
                        for mname, mod in list(_d_sys.modules.items()):
                            try:
                                mfile = getattr(mod, "__file__", None)
                                if not mfile:
                                    continue  # saída antecipada — evita construir Path para módulos builtin
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
# engine\tools\local_index.py
"""
ORN — LocalIndex (Projeto Vulcan / SiCDox) v5.4 - pyzim Only EditionORN — LocalIndex (Projeto Vulcan / SiCDox) v6.0 - Semantic Edition
Motor de Busca Offline ZIM -> SQLite FTS5 + ZSTD Tokenizado Nativo

Backend exclusivo: python-zim (pyzim)  — libzim removido (crashava no Windows)
Busca:            SQLite FTS5 (build obrigatório uma vez)
Compressão:       pyzstd (opcional — fallback para texto puro se não instalado)

Uso rápido:
  python -m engine.tools.local_index probe  data/zim/<arquivo>.zim
  python -m engine.tools.local_index build  data/zim/<arquivo>.zim
  python -m engine.tools.local_index search <source_id> <query>
  python -m engine.tools.local_index list

God Thoth — dá forma ao conhecimento e o torna pesquisável.

Compliance PA10: 
- Compressão Semântica via Tokenização Nativa (llama_cpp).
- Conversão de Texto para Arrays Int (A Matriz Numérica da IA).
- Zero dependência do HuggingFace/Transformers.
"""

import array
import hashlib
import os
import re
import struct
import sys
import sqlite3
import time
from pathlib import Path
from typing import Iterator

from engine.tools.inverted_index import InvertedIndexBuilder, InvertedIndexSearcher
from engine.telemetry.core import orn_span, GLOBAL_TELEMETRY, record_direct_telemetry


ZIM_DIR   = Path("data/zim")
INDEX_DIR = Path("data/index")

_GGUF_PATH = (
    r"C:\Users\olDox222\Documents\A20251122\DOSSIER\Altonomo\Projetos_E_Programas\Projeto_OIA\olDox222RN\ORN\models\sicdox\Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
    
)

# ---------------------------------------------------------------------------
# Utilidades e Compressão (ZSTD)
# ---------------------------------------------------------------------------
def _zim_to_source_id(zim_path: str | Path) -> str:
    name = Path(zim_path).stem
    name = name.replace("-", "_").replace(".", "_")
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return re.sub(r"_+", "_", name).strip("_").lower()

def _source_id_to_db(source_id: str) -> Path:
    return INDEX_DIR / f"{source_id}.db"

def _find_zim_for_source(source_id: str) -> "Path | None":
    if ZIM_DIR.exists():
        for zim in ZIM_DIR.glob("*.zim"):
            if _zim_to_source_id(zim) == source_id: return zim
    return None

def _compress(data: bytes) -> bytes:
    try:
        import pyzstd
        return pyzstd.compress(data)
    except ImportError: return data

def _decompress(data: bytes) -> bytes:
    try:
        import pyzstd
        return pyzstd.decompress(data)
    except Exception:
        return data

class LocalResult:
    __slots__ = ("source", "title", "body", "path")
    def __init__(self, source: str, title: str, body: str, path: str = ""):
        self.source = source; self.title = title; self.body = body; self.path = path
    @property
    def ok(self) -> bool: return bool(self.title and self.body.strip())
    def to_prompt_block(self, max_chars: int = 800) -> str:
        if not self.ok: return ""
        return f"[CTX-BEGIN]\nscope: {self.source} | {self.title}\n{self.body[:max_chars]}\n[CTX-END]\n"

_RE_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_RE_NAV    = re.compile(r'<[^>]*(navbox|mw-toc|mw-jump|sidebar|infobox|reflist)[^>]*>.*?</\w+>', re.DOTALL | re.IGNORECASE)
_RE_TAG    = re.compile(r"<[^>]+>")
_RE_ENTITY = re.compile(r"&(?:[a-zA-Z]{2,8}|#\d{1,6});")
_RE_MULTI  = re.compile(r"[ \t]{2,}")
_RE_NEWL   = re.compile(r"\n{3,}")
_RE_URL    = re.compile(r"https?://\S+")

def _strip_html(html: str, max_chars: int = 8000) -> str:
    html = _RE_SCRIPT.sub(" ", html)
    html = _RE_NAV.sub(" ", html)
    html = _RE_TAG.sub(" ", html)
    html = _RE_ENTITY.sub(" ", html)
    html = _RE_URL.sub(" ", html)
    text = _RE_MULTI.sub(" ", html)
    text = _RE_NEWL.sub("\n\n", text).strip()
    return text[:max_chars]

def _read_entry_content(entry) -> "bytes | None":
    for method in ("read", "get_data", "content", "data"):
        fn = getattr(entry, method, None)
        if fn is None: continue
        try:
            result = fn() if callable(fn) else fn
            if isinstance(result, (bytes, bytearray, memoryview)) and len(result) > 0: return bytes(result)
        except Exception: continue
    for attr in ("_data", "_content", "raw"):
        val = getattr(entry, attr, None)
        if isinstance(val, (bytes, bytearray, memoryview)) and len(val) > 0: return bytes(val)
    return None

def _iter_zim_entries(zim_path: str, verbose: bool = True) -> Iterator[tuple[str, str, str]]:
    """Itera entradas HTML de um ZIM. Compatível com ZIM 5.x e 6.x."""
    import pyzim
    p = Path(zim_path).absolute()

    total_scanned = total_yielded = total_redirect = 0
    total_non_html = total_empty = total_error = 0

    with pyzim.Zim.open(str(p), mode="r") as zim:
        for entry in zim.iter_entries():
            total_scanned += 1

            if verbose and total_scanned % 5000 == 0:
                print(
                    f"  [ZIM] scanned={total_scanned} yielded={total_yielded} "
                    f"redirect={total_redirect} non_html={total_non_html} "
                    f"empty={total_empty}",
                    flush=True,
                )

            # --- Redirect ---
            if getattr(entry, "is_redirect", False):
                total_redirect += 1
                continue

            # --- Namespace ---
            # ZIM 5.x: "A"=artigos, "I"=imagens, "-"=metadados → filtrar recursos.
            # ZIM 6.x: namespace removido — pyzim pode retornar None, "", "C".
            # Estratégia: bloquear APENAS namespaces de recursos explícitos.
            ns = getattr(entry, "namespace", None)
            if ns is not None:
                if isinstance(ns, bytes):
                    ns = ns.decode("utf-8", errors="ignore")
                ns = str(ns).strip()
                if ns in ("I", "-", "X"):   # imagens, metadados — nunca artigos
                    total_non_html += 1
                    continue

            # --- Ler conteúdo ---
            content_bytes = _read_entry_content(entry)
            if not content_bytes:
                total_empty += 1
                continue

            # --- Filtro de conteúdo: HTML ou texto ---
            # ZIM 6.x pode conter HTML sem DOCTYPE — verifica sinais mais amplos.
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

            # --- Extração de título e path ---
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
                continue

    if verbose:
        print(
            f"  [ZIM] total: scanned={total_scanned} yielded={total_yielded} "
            f"redirect={total_redirect} non_html={total_non_html} "
            f"empty={total_empty} error={total_error}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# Ponte Semântica Nativa (llama.cpp) — Zero Bloatware
# ---------------------------------------------------------------------------
class TokenizerBridge:
    """Singleton ultraleve — carrega só o vocabulário do GGUF (vocab_only=True)."""
    _llm_vocab = None

    @classmethod
    def get_vocab(cls):
        if cls._llm_vocab is None:
            from llama_cpp import Llama
            if not os.path.exists(_GGUF_PATH):
                raise FileNotFoundError(f"GGUF não encontrado: {_GGUF_PATH}")
            print("  [SiCDox] Carregando a Matriz de Vocabulario (vocab_only)...", flush=True)
            cls._llm_vocab = Llama(model_path=_GGUF_PATH, vocab_only=True, verbose=False)
        return cls._llm_vocab

    @classmethod
    def text_to_bytes(cls, text: str) -> bytes:
        """Converte texto humano em C-Array de Tokens (Inteiros)"""
        vocab  = cls.get_vocab()
        tokens = vocab.tokenize(text.encode("utf-8"), add_bos=False)
        # 'i' = signed int de 32 bits nativo da linguagem C
        return array.array("i", tokens).tobytes()

    @classmethod
    def bytes_to_text(cls, data: bytes) -> str:
        """Recria o texto a partir dos Tokens binários para entregar ao RAG"""
        # Proteção 1: Se o bloco de bytes não for múltiplo de 4, é texto legado
        if len(data) % 4 != 0:
            return data.decode("utf-8", errors="ignore")
            
        try:
            vocab = cls.get_vocab()
            arr   = array.array("i")
            arr.frombytes(data)
            tokens = arr.tolist()
            
            # Proteção 2 (Anti-C++ Crash): Se um token extrapolar o limite do modelo,
            # significa que estamos tentando ler texto puro como inteiros.
            if tokens and (max(tokens) >= vocab.n_vocab() or min(tokens) < 0):
                return data.decode("utf-8", errors="ignore")

            return vocab.detokenize(tokens).decode("utf-8", errors="ignore")
            
        except Exception:
            # Fallback final: devolve o dado como string normal
            return data.decode("utf-8", errors="ignore")

# ---------------------------------------------------------------------------
# LocalResult — __slots__ explícito (Vulcan C++ Safe)
# ---------------------------------------------------------------------------

class LocalResult:
    """
    Resultado de busca offline.
    __slots__ obrigatório — sem ele o Vulcan/GCC gera wrapper sem __init__.
    """
    __slots__ = ("source", "title", "body", "path")

    def __init__(self, source: str, title: str, body: str, path: str = ""):
        self.source = source
        self.title  = title
        self.body   = body
        self.path   = path

    @property
    def ok(self) -> bool:
        return bool(self.title and self.body.strip())

    def to_prompt_block(self, max_chars: int = 600) -> str:
        if not self.ok:
            return ""
        return (
            f"[CTX-BEGIN]\n"
            f"scope: {self.source} | {self.title}\n"
            f"{self.body[:max_chars]}\n"
            f"[CTX-END]\n"
        )


# ---------------------------------------------------------------------------
# Limpeza HTML (stdlib pura)
# ---------------------------------------------------------------------------

_RE_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_RE_NAV    = re.compile(
    r'<[^>]*(navbox|mw-toc|mw-jump|sidebar|infobox|reflist)[^>]*>.*?</\w+>',
    re.DOTALL | re.IGNORECASE,
)
_RE_TAG    = re.compile(r"<[^>]+>")
_RE_ENTITY = re.compile(r"&(?:[a-zA-Z]{2,8}|#\d{1,6});")
_RE_MULTI  = re.compile(r"[ \t]{2,}")
_RE_NEWL   = re.compile(r"\n{3,}")
_RE_URL    = re.compile(r"https?://\S+")


def _strip_html(html: str, max_chars: int = 8000) -> str:
    html = _RE_SCRIPT.sub(" ", html)
    html = _RE_NAV.sub(" ", html)
    html = _RE_TAG.sub(" ", html)
    html = _RE_ENTITY.sub(" ", html)
    html = _RE_URL.sub(" ", html)
    text = _RE_MULTI.sub(" ", html)
    text = _RE_NEWL.sub("\n\n", text).strip()
    return text[:max_chars]


# ---------------------------------------------------------------------------
# Compressão opcional (pyzstd)
# ---------------------------------------------------------------------------

def _compress(data: bytes) -> bytes:
    try:
        import pyzstd
        return pyzstd.compress(data)
    except ImportError:
        return data  # fallback: sem compressão


def _decompress(data: bytes) -> bytes:
    # Detecta magic bytes do ZSTD: 0xFD2FB528
    if len(data) >= 4 and data[:4] == b"\x28\xb5\x2f\xfd":
        try:
            import pyzstd
            return pyzstd.decompress(data)
        except Exception:
            pass
    return data  # já é texto puro (fallback sem pyzstd)


# ---------------------------------------------------------------------------
# Iterador pyzim — core do build
# ---------------------------------------------------------------------------

def _read_entry_content(entry) -> "bytes | None":
    """
    Tenta ler o conteúdo de uma entry pyzim.
    pyzim tem APIs diferentes entre versões — testa em ordem.
    """
    # API mais comum: entry.read()
    for method in ("read", "get_data", "content", "data"):
        fn = getattr(entry, method, None)
        if fn is None:
            continue
        try:
            result = fn() if callable(fn) else fn
            if isinstance(result, (bytes, bytearray)) and len(result) > 0:
                return bytes(result)
            if isinstance(result, memoryview):
                return bytes(result)
        except Exception:
            continue

    # Último recurso: atributo direto
    for attr in ("_data", "_content", "raw"):
        val = getattr(entry, attr, None)
        if isinstance(val, (bytes, bytearray, memoryview)) and len(val) > 0:
            return bytes(val)

    return None


# ---------------------------------------------------------------------------
# VULCAN BUILD (Indexador Tokenizado)
# ---------------------------------------------------------------------------
def build_index(zim_path: str, source_id: "str | None" = None, batch_size: int = 500, verbose: bool = True) -> Path:
    try: import pyzim  # noqa: F401
    except ImportError: raise ImportError("pyzim não instalado.  pip install pyzim")
    if not Path(zim_path).exists(): raise FileNotFoundError(f"ZIM não encontrado: {zim_path}")

    # Força o carregamento do LLM Vocab antes do loop
    TokenizerBridge.get_vocab()

    if source_id is None: source_id = _zim_to_source_id(zim_path)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    db_path = str(_source_id_to_db(source_id))

    if verbose: print(f"\n  [SiCDox BUILD] Construindo Banco Tokenizado...\n  DB: {db_path}", flush=True)
    # inicializa o builder do índice invertido no escopo correto
    inv_builder = InvertedIndexBuilder()

    t0 = time.monotonic()

    con = sqlite3.connect(db_path, isolation_level=None)
    con.execute("PRAGMA page_size=4096")
    con.execute("PRAGMA synchronous=NORMAL")

    con.execute("BEGIN")
    for tbl in ("articles_fts", "pages", "content_pool", "meta"): con.execute(f"DROP TABLE IF EXISTS {tbl}")
    
    con.execute("CREATE TABLE content_pool (hash TEXT PRIMARY KEY, token_blob BLOB)")
    con.execute("CREATE TABLE pages (id INTEGER PRIMARY KEY, title TEXT, path TEXT, content_hash TEXT)")
#    con.execute("CREATE VIRTUAL TABLE articles_fts USING fts5(title, body, content='', content_rowid='id', tokenize='unicode61 remove_diacritics 1')")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO meta VALUES ('source_id', ?)", (source_id,))
    con.execute("INSERT INTO meta VALUES ('sicdox_ver', '6.0')",)
    con.execute("COMMIT")

    count = deduplicated = 0
    buf_pages, seen_hashes = [], set()
#    buf_pages, buf_fts, seen_hashes = [],[], set()

    con.execute("BEGIN")
    for title, path, html in _iter_zim_entries(zim_path, verbose=verbose):
        with orn_span("build.strip_html", category="index"):
            body = _strip_html(html, max_chars=8000)
            
        if len(body.strip()) < 50: continue

        with orn_span("build.tokenize", category="index"):
            try: payload = TokenizerBridge.text_to_bytes(body)
            except Exception: continue

            tokens = array.array("i")
            tokens.frombytes(payload)
            h = hashlib.md5(payload).hexdigest()

        if h not in seen_hashes:
            seen_hashes.add(h)
            with orn_span("build.zstd_compress", category="index"):
                compressed = _compress(payload)
            
            with orn_span("build.sql_insert", category="index"):
                con.execute("INSERT INTO content_pool VALUES (?, ?)", (h, compressed))
        else: deduplicated += 1

        count += 1
        buf_pages.append((count, title, path, h))

        with orn_span("build.inverted_idx", category="index"):
            inv_builder.add_document(count, tokens)

        if len(buf_pages) >= batch_size:
            with orn_span("build.sql_commit", category="index"):
                con.executemany("INSERT INTO pages (id, title, path, content_hash) VALUES (?,?,?,?)", buf_pages)
                con.execute("COMMIT")
                con.execute("BEGIN")
                buf_pages.clear()
            if verbose: print(f"  [BUILD] {count} artigos tokenizados...", end="\r", flush=True)

    if buf_pages:
        con.executemany("INSERT INTO pages (id, title, path, content_hash) VALUES (?,?,?,?)", buf_pages)
#        con.executemany("INSERT INTO articles_fts (rowid, title, body) VALUES (?,?,?)", buf_fts)
    con.execute("COMMIT")
#    con.execute("INSERT INTO articles_fts(articles_fts) VALUES('optimize')")
    con.close()

    # ------------------------------------------------
    # Finaliza índice invertido
    # ------------------------------------------------

    if verbose:
        print("\n  [INDEX] Finalizando Inverted Index...")

    inv_builder.finalize()

    inv_dir = INDEX_DIR / source_id

    inv_builder.write(inv_dir)

    if verbose: print(f"\n  [BUILD] Concluído: {count} matrizes (Dedup: {deduplicated}) em {round(time.monotonic()-t0, 1)}s")
    return Path(db_path)

# ---------------------------------------------------------------------------
# SEARCH LOCAL (Descompressão Semântica)
# ---------------------------------------------------------------------------
def search_local(query: str, source_id: str, limit: int = 3) -> "list[LocalResult]":
    if not query.strip(): return[]
    db_path = str(_source_id_to_db(source_id))
    if not Path(db_path).exists(): return[]

    t_start = time.perf_counter()
    label   = f"{source_id}-local"

    try:
        con = sqlite3.connect(db_path, check_same_thread=False)
        con.execute("PRAGMA query_only=1")
        
        results: list[LocalResult] =[]

        # 1. BUSCA RÁPIDA PELO TÍTULO (Ignora maiúsculas/minúsculas e acha instantâneo)
        rows = con.execute(
            "SELECT p.title, p.path, c.token_blob FROM pages p "
            "JOIN content_pool c ON p.content_hash = c.hash "
            "WHERE p.title LIKE ? LIMIT ?", (f"%{query}%", limit)
        ).fetchall()

        if rows:
            for title, path, blob in rows:
                decompressed_bytes = _decompress(blob)
                body = TokenizerBridge.bytes_to_text(decompressed_bytes)
                body = re.sub(r'\n\s*\n', '\n\n', body).strip()
                results.append(LocalResult(label, title, body, path))
        else:
            # 2. SE NÃO ACHOU NO TÍTULO, TENTA A BUSCA POR TOKENS (Inverted Index)
            inv_dir = INDEX_DIR / source_id
            from engine.tools.inverted_index import InvertedIndexSearcher
            searcher = InvertedIndexSearcher(inv_dir)

            query_tokens = TokenizerBridge.get_vocab().tokenize(
                query.encode("utf-8"),
                add_bos=False
            )

            doc_ids = searcher.search(query_tokens, limit=limit)

            for doc_id in doc_ids:
                row = con.execute("SELECT p.title, p.path, c.token_blob FROM pages p JOIN content_pool c ON p.content_hash = c.hash WHERE p.id = ?", (doc_id,)).fetchone()
                if row:
                    title, path, blob = row
                    decompressed_bytes = _decompress(blob)
                    body = TokenizerBridge.bytes_to_text(decompressed_bytes)
                    body = re.sub(r'\n\s*\n', '\n\n', body).strip()
                    results.append(LocalResult(label, title, body, path))

        con.close()

        if os.environ.get("VULCAN_TELEMETRY") == "1":
            print(f"\n[🔥 VULCAN PROFILER] search_semantic({source_id}) C++ ZSTD: {(time.perf_counter() - t_start)*1000:.2f}ms")
        return results

    except Exception as e:
        if os.environ.get("VULCAN_TELEMETRY") == "1": print(f"[ERRO search_local]: {e}")
        return []

# ---------------------------------------------------------------------------
# RESTANTE (info, list, probe, cli)
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

def list_indexes() -> "list[dict]":
    seen, result = set(),[]
    if INDEX_DIR.exists():
        for db_file in sorted(INDEX_DIR.glob("*.db")):
            sid = db_file.stem; seen.add(sid); result.append(index_info(sid))
    if ZIM_DIR.exists():
        for zim_file in sorted(ZIM_DIR.glob("*.zim")):
            sid = _zim_to_source_id(zim_file)
            if sid not in seen:
                result.append({"source_id": sid, "articles": 0, "zim_path": str(zim_file), "mode": "Aguardando Build", "exists": False})
                seen.add(sid)
    return result

_ZIM_MAGIC         = 0x044D495A
_ZIM_HEADER_SIZE   = 80


def _read_zim_header(zim_path: str) -> dict:
    """Lê 80 bytes do header ZIM sem abrir pyzim (O(1))."""
    with open(zim_path, "rb") as f:
        raw = f.read(_ZIM_HEADER_SIZE)
    if len(raw) < _ZIM_HEADER_SIZE:
        raise ValueError(f"Arquivo muito pequeno ({len(raw)} bytes)")
    magic, major, minor = struct.unpack_from("<IHH", raw, 0)
    if magic != _ZIM_MAGIC:
        raise ValueError(f"Magic inválido: 0x{magic:08X}")
    entry_count, cluster_count = struct.unpack_from("<II", raw, 24)
    return {"version": f"{major}.{minor}", "uuid": raw[8:24].hex(),
            "entry_count": entry_count, "cluster_count": cluster_count}


def probe_zim(zim_path: str) -> None:
    """Exibe metadados do ZIM lendo apenas o header binário."""
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
    """Inspeciona as primeiras N entradas do ZIM e imprime atributos reais.

    Usar quando build retorna 0 artigos: revela o que pyzim enxerga
    (namespace, MIME type, is_redirect, tamanho do conteúdo).
    """
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
            is_redir  = getattr(entry, "is_redirect", "?")
            ns        = getattr(entry, "namespace", "?")
            if isinstance(ns, bytes): ns = ns.decode("utf-8", errors="ignore")
            mime      = getattr(entry, "mimetype", None) or getattr(entry, "mime_type", "?")
            if callable(mime): mime = mime()
            if isinstance(mime, bytes): mime = mime.decode("utf-8", errors="ignore")
            title     = getattr(entry, "title", "?")
            if isinstance(title, bytes): title = title.decode("utf-8", errors="ignore")
            content   = _read_entry_content(entry)
            clen      = len(content) if content else 0
            chead     = ""
            if content:
                chead = content[:60].replace(b"\n", b" ").decode("utf-8", errors="ignore")
            print(f"  {i:<4} {str(is_redir):<10} {str(ns):<12} {str(mime)[:28]:<30} {clen:<14} {str(title)[:40]}")

    print()



_HELP = "ORN LocalIndex v6.0 — SiCDox (Semantic Compression)"

def _cli_main() -> None:
    import sys
    import time
    from pathlib import Path
    
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"): 
        print(_HELP)
        return

    cmd = args[0]

    # --- INJEÇÃO BLINDADA E LOCALIZADOR DO DOXOADE ---
    # Sobe 3 níveis a partir deste arquivo (engine/tools/local_index.py) 
    # para chegar na pasta 'olDox222RN' e tenta achar a pasta 'doxoade'
    try:
        project_root = Path(__file__).resolve().parents[3]
        doxoade_dir = project_root / "doxoade"
        if doxoade_dir.exists() and str(doxoade_dir) not in sys.path:
            sys.path.insert(0, str(doxoade_dir))
    except Exception:
        pass

    chronos_recorder = None
    try:
        from doxoade.chronos import chronos_recorder
        
        class FakeCommand:
            name = f"INDEX-{cmd.upper()}"
            
        class FakeCtx:
            invoked_subcommand = None
            command = FakeCommand()
            obj = {}
            
        chronos_recorder.start_command(FakeCtx())
        print(f"[TELEMETRY] Chronos Nexus ativado! (Sessão: {chronos_recorder.session_uuid})")
    except Exception as e:
        print(f"  [TELEMETRY] Aviso: Doxoade Chronos não iniciou -> {e}")
    # -------------------------------------------------

    t_start_global = time.perf_counter()
    exit_code = 0

    try:
        if cmd == "probe": 
            probe_zim(args[1])
        elif cmd == "build": 
            build_index(args[1], source_id=args[2] if len(args) > 2 else None)
            from engine.telemetry.core import GLOBAL_TELEMETRY
            GLOBAL_TELEMETRY.flush_json("telemetry/local_index_build.json")
            print("[TELEMETRY] ORN Spans salvos em telemetry/local_index_build.json")
        elif cmd == "search":
            t0 = time.perf_counter()
            results = search_local(" ".join(args[2:]), args[1])
            elapsed = round((time.perf_counter() - t0) * 1000, 2)
            if not results: 
                print(f"\n  Nenhum resultado para a busca.")
            else:
                for r in results: 
                    print(f"\n  [{r.source}] {r.title}\n  {r.body[:400]}")
            print(f"\n  Tempo: {elapsed}ms | {len(results)} resultado(s)")
        elif cmd == "info":
            for k, v in index_info(args[1]).items(): 
                print(f"  {k:<12}: {v}")
        elif cmd == "list":
            for info in list_indexes(): 
                print(f"  {info['source_id']:<45} {info.get('articles', 0):>8}  {info.get('mode', '?')}")
        else: 
            print("Comandos: probe | build | search | info | list")
            
    except Exception as e:
        exit_code = 1
        raise e
        
    finally:
        # --- FINALIZA O CHRONOS COM SEGURANÇA ---
        if chronos_recorder:
            duration_ms = (time.perf_counter() - t_start_global) * 1000
            try:
                chronos_recorder.end_command(exit_code, duration_ms)
                print(f"  [TELEMETRY] Dados gravados no banco de auditoria Doxoade.")
            except Exception as e:
                print(f"  [TELEMETRY] Erro ao salvar log do Chronos: {e}")

if __name__ == "__main__": _cli_main()