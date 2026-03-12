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

from __future__ import annotations

import array
import hashlib
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Iterator

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
    if len(data) >= 4 and data[:4] == b"\xfd\x2f\xb5\x28":
        try:
            import pyzstd
            return pyzstd.decompress(data)
        except Exception: pass
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
    import pyzim
    p = Path(zim_path).absolute()
    with pyzim.Zim.open(str(p), mode="r") as zim:
        for entry in zim.iter_entries():
            if getattr(entry, "is_redirect", False): continue
            ns = getattr(entry, "namespace", None)
            if ns is not None:
                if isinstance(ns, bytes): ns = ns.decode("utf-8", errors="ignore")
                if str(ns).strip() not in ("A", "C", ""): continue

            content_bytes = _read_entry_content(entry)
            if not content_bytes: continue
            
            head = content_bytes[:200].lower()
            if not (content_bytes[:1] == b"<" or b"<html" in head or b"<!doctype" in head or b"<body" in head or b"<p>" in head):
                continue

            try:
                title = getattr(entry, "title", "")
                if isinstance(title, bytes): title = title.decode("utf-8", errors="ignore")
                path = getattr(entry, "url", None) or getattr(entry, "path", "")
                if isinstance(path, bytes): path = path.decode("utf-8", errors="ignore")
                if not title: title = str(path).split("/")[-1].replace("_", " ").strip()
                content = content_bytes.decode("utf-8", errors="replace")
                yield str(title).strip(), str(path).strip(), content
            except Exception: continue

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
        vocab = cls.get_vocab()
        arr   = array.array("i")
        arr.frombytes(data)
        return vocab.detokenize(arr.tolist()).decode("utf-8", errors="ignore")


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
    if len(data) >= 4 and data[:4] == b"\xfd\x2f\xb5\x28":
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


def _iter_zim_entries(
    zim_path: str,
    verbose:  bool = True,
) -> Iterator[tuple[str, str, str]]:
    """
    Itera todas as entradas HTML de um ZIM usando pyzim.
    Yield: (title, path, html_content)
    """
    import pyzim  # já verificado antes de chamar

    p = Path(zim_path).absolute()

    with pyzim.Zim.open(str(p), mode="r") as zim:
        total_yielded  = 0
        total_redirect = 0
        total_non_html = 0
        total_empty    = 0
        total_error    = 0

        for entry in zim.iter_entries():
            # --- Redirect ---
            if getattr(entry, "is_redirect", False):
                total_redirect += 1
                continue

            # --- Namespace (ZIM format 5: "A" = artigos) ---
            ns = getattr(entry, "namespace", None)
            if ns is not None:
                if isinstance(ns, bytes):
                    ns = ns.decode("utf-8", errors="ignore")
                ns = str(ns).strip()
                # Aceita "A", "C" (artigos em alguns ZIMs) e "" (format 6+)
                if ns not in ("A", "C", ""):
                    total_non_html += 1
                    continue

            # --- Ler conteúdo ---
            content_bytes = _read_entry_content(entry)
            if not content_bytes:
                total_empty += 1
                continue

            # --- Filtro HTML ---
            head = content_bytes[:200].lower()
            is_html = (
                content_bytes[:1] == b"<"
                or b"<html" in head
                or b"<!doctype" in head
                or b"<body" in head
                or b"<p>" in head
                or b"<div" in head
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
                f"  [ZIM] Resultado: {total_yielded} artigos | "
                f"{total_redirect} redirects | "
                f"{total_non_html} não-HTML | "
                f"{total_empty} vazios | "
                f"{total_error} erros",
                flush=True,
            )


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
    t0 = time.monotonic()

    con = sqlite3.connect(db_path, isolation_level=None)
    con.execute("PRAGMA page_size=4096")
    con.execute("PRAGMA synchronous=NORMAL")

    con.execute("BEGIN")
    for tbl in ("articles_fts", "pages", "content_pool", "meta"): con.execute(f"DROP TABLE IF EXISTS {tbl}")
    
    con.execute("CREATE TABLE content_pool (hash TEXT PRIMARY KEY, token_blob BLOB)")
    con.execute("CREATE TABLE pages (id INTEGER PRIMARY KEY, title TEXT, path TEXT, content_hash TEXT)")
    con.execute("CREATE VIRTUAL TABLE articles_fts USING fts5(title, body, content='', content_rowid='id', tokenize='unicode61 remove_diacritics 1')")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO meta VALUES ('source_id', ?)", (source_id,))
    con.execute("INSERT INTO meta VALUES ('sicdox_ver', '6.0')",)
    con.execute("COMMIT")

    count = deduplicated = 0
    buf_pages, buf_fts, seen_hashes = [],[], set()

    con.execute("BEGIN")
    for title, path, html in _iter_zim_entries(zim_path, verbose=verbose):
        body = _strip_html(html, max_chars=8000)
        if len(body.strip()) < 50: continue

        # 🧠 A MÁGICA: Converte para Array Int C++
        try: payload = TokenizerBridge.text_to_bytes(body)
        except Exception: continue

        h = hashlib.md5(payload).hexdigest()

        if h not in seen_hashes:
            seen_hashes.add(h)
            con.execute("INSERT INTO content_pool VALUES (?, ?)", (h, _compress(payload)))
        else: deduplicated += 1

        count += 1
        buf_pages.append((count, title, path, h))
        buf_fts.append((count, title, body)) # SQLite FTS5 precisa do texto puro para a árvore de busca

        if len(buf_pages) >= batch_size:
            con.executemany("INSERT INTO pages (id, title, path, content_hash) VALUES (?,?,?,?)", buf_pages)
            con.executemany("INSERT INTO articles_fts (rowid, title, body) VALUES (?,?,?)", buf_fts)
            con.execute("COMMIT")
            con.execute("BEGIN")
            buf_pages.clear(); buf_fts.clear()
            if verbose: print(f"  [BUILD] {count} artigos tokenizados...", end="\r", flush=True)

    if buf_pages:
        con.executemany("INSERT INTO pages (id, title, path, content_hash) VALUES (?,?,?,?)", buf_pages)
        con.executemany("INSERT INTO articles_fts (rowid, title, body) VALUES (?,?,?)", buf_fts)
    con.execute("COMMIT")
    con.execute("INSERT INTO articles_fts(articles_fts) VALUES('optimize')")
    con.close()

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

        rows = con.execute("SELECT rowid FROM articles_fts WHERE articles_fts MATCH ? ORDER BY rank LIMIT ?", (query, limit)).fetchall()
        if not rows:
            prefix = " ".join(w + "*" for w in query.split() if len(w) > 2)
            if prefix: rows = con.execute("SELECT rowid FROM articles_fts WHERE articles_fts MATCH ? ORDER BY rank LIMIT ?", (prefix, limit)).fetchall()

        results: list[LocalResult] =[]
        for (doc_id,) in rows:
            row = con.execute("SELECT p.title, p.path, c.token_blob FROM pages p JOIN content_pool c ON p.content_hash = c.hash WHERE p.id = ?", (doc_id,)).fetchone()
            if row:
                title, path, blob = row
                
                # 🧠 REVERSA: Descompacta ZSTD -> Lê Array Int -> Detokeniza para Texto
                decompressed_bytes = _decompress(blob)
                body = TokenizerBridge.bytes_to_text(decompressed_bytes)
                
                results.append(LocalResult(label, title, body, path))

        con.close()

        if os.environ.get("VULCAN_TELEMETRY") == "1":
            print(f"\n[🔥 VULCAN PROFILER] search_semantic({source_id}) C++ ZSTD: {(time.perf_counter() - t_start)*1000:.2f}ms")
        return results

    except Exception as e:
        if os.environ.get("VULCAN_TELEMETRY") == "1": print(f"[ERRO search_local]: {e}")
        return[]

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

def probe_zim(zim_path: str) -> None:
    try:
        import pyzim
        with pyzim.Zim.open(zim_path, mode="r") as zim: print(f"\n  [PROBE] Total de Entradas: {zim.header.entry_count}")
    except Exception as e: print(f"  [PROBE] FALHOU: {e}")

_HELP = "ORN LocalIndex v6.0 — SiCDox (Semantic Compression)"
def _cli_main() -> None:
    import sys
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"): print(_HELP); return

    cmd = args[0]
    if cmd == "probe": probe_zim(args[1])
    elif cmd == "build": build_index(args[1], source_id=args[2] if len(args) > 2 else None)
    elif cmd == "search":
        t0 = time.perf_counter()
        results = search_local(" ".join(args[2:]), args[1])
        elapsed = round((time.perf_counter() - t0) * 1000, 2)
        if not results: print(f"\n  Nenhum resultado para a busca.")
        else:
            for r in results: print(f"\n  [{r.source}] {r.title}\n  {r.body[:400]}")
        print(f"\n  Tempo: {elapsed}ms | {len(results)} resultado(s)")
    elif cmd == "info":
        for k, v in index_info(args[1]).items(): print(f"  {k:<12}: {v}")
    elif cmd == "list":
        for info in list_indexes(): print(f"  {info['source_id']:<45} {info.get('articles', 0):>8}  {info.get('mode', '?')}")
    else: print("Comandos: probe | build | search | info | list")

if __name__ == "__main__": _cli_main()