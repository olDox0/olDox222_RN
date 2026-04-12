# -*- coding: utf-8 -*-
# engine/tools/local_index/_build.py
"""
ORN — LocalIndex / Build (Hefesto)
Constrói o banco SQLite tokenizado + índice invertido opcional a partir de ZIPs ZIM.

Responsabilidades deste módulo:
  - Iterar entradas de um arquivo .zim  (_iter_zim_entries)
  - Processar cada entrada em worker thread (_process_zim_entry)
  - Montar/retomar o banco SQLite (_init_db, _check_resume, _cleanup_stale)
  - Drenar o pool de futures e gravar em lote (_drain_futures)
  - Orquestrar o pipeline completo (build_index)

OSL-4:  Cada função faz uma coisa.
OSL-7:  build_index() retorna Path ou levanta — sem retorno silencioso None.
OSL-15: Erros em workers individuais são ignorados (continue), não derrubam o build.
OSL-18: stdlib + dependências de projeto; pyzim/pyzstd importados lazy.
"""

from __future__ import annotations

import array
import concurrent.futures
import hashlib
import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, List, Optional

from engine.telemetry.core import orn_span
from engine.tools.inverted_index import InvertedIndexBuilder

if TYPE_CHECKING:
    from engine.tools.local_index._tokenizer import TokenizerBridge

# ---------------------------------------------------------------------------
# Config herdada do pacote pai (injetada por __init__.py ou definida aqui
# como fallback para uso standalone)
# ---------------------------------------------------------------------------

try:
    from engine.tools.local_index._config import ZIM_DIR, INDEX_DIR
except ImportError:
    ZIM_DIR  = Path(os.environ.get("SICDOX_ZIM_DIR",  "data/zim"))
    INDEX_DIR = Path(os.environ.get("SICDOX_INDEX_DIR", "data/index"))

logger = logging.getLogger("engine.tools.local_index.build")

# ── Configuração do pitstop ──────────────────────────────────────────────────
_PITSTOP_EVERY: int = 5000   # a cada N entradas processadas, faz pitstop
_PITSTOP_GC_EVERY: int = 8   # a cada N pitstops, força gc.collect()

# ---------------------------------------------------------------------------
# Helpers de path (sem lógica de negócio)
# ---------------------------------------------------------------------------

def _simple_hash_tokens(text: str) -> list[int]:
    """Fallback de tokenização sem TokenizerBridge (OSL-15)."""
    import hashlib
    import struct
    tokens: list[int] = []
    for word in text.lower().split():
        h = struct.unpack(">I", hashlib.md5(word.encode("utf-8", errors="ignore")).digest()[:4])[0]
        tokens.append(h % (2**30))
    return tokens


def _process_entry_with_pitstop(
    idx: int,
    title: str,
    path: str,
    html: str,
    tok: "TokenizerBridge | None" = None,
) -> "tuple[int, str, str, list[int], str] | None":
    """Versão de _process_entry com pitstop do tokenizador.

    Retorna (doc_id, title, path, tokens, body_clean) ou None se inválido.

    O doc_id é derivado do idx para manter compatibilidade com o DB.
    Os tokens são os IDs reais do vocabulário Qwen (via TokenizerBridge).
    """
    try:
        # ── Limpeza HTML → texto (mesmo pipeline de antes) ──────────────
        from engine.tools.local_index._text_utils import (   # lazy OSL-3
            extract_code_blocks,
            restore_code_placeholders,
            clean_body,
            strip_html,
        )

        html_no_code, code_blocks = extract_code_blocks(html)
        raw_text = strip_html(html_no_code)
        body = restore_code_placeholders(raw_text, code_blocks)
        body = clean_body(body)

        if not body or not body.strip():
            return None

        doc_id = idx  # 1-to-1 com o índice de entrada do ZIM

        # ── PITSTOP: tokenização real ────────────────────────────────────
        if tok is not None:
            tokens = tok.tokenize(body)
        else:
            tokens = _simple_hash_tokens(body)
        # ─────────────────────────────────────────────────────────────────

        if not tokens:
            return None

        return doc_id, title, path, tokens, body

    except Exception as exc:
        logger.debug("[PROCESS_ENTRY] idx=%d erro=%s", idx, exc)
        return None


# ─── TRECHO DO build_index() COM PITSTOP (para substituição direta) ──────────

def _build_index_pitstop_block(
    zim_path: str | Path,
    use_tokenizer_pitstop: bool = True,
) -> "TokenizerBridge | None":
    """Executa o pitstop e retorna o tokenizer pronto (ou None).

    Chamar ANTES do loop de entradas em build_index():

        tok = _build_index_pitstop_block(zim_path, use_tokenizer_pitstop)
        try:
            for idx, title, path, html in _iter_zim_entries(...):
                result = _process_entry_with_pitstop(idx, title, path, html, tok)
                ...
        finally:
            _build_index_pitstop_teardown(tok)
    """
    if not use_tokenizer_pitstop:
        return None

    from engine.tools.local_index._tokenizer import TokenizerBridge  # lazy

    tok = TokenizerBridge()
    mode = tok.pitstop()

    _MODE_LABELS = {
        "server": "servidor ORN (porta 8371) — zero overhead de carregamento",
        "vocab":  "vocab_only GGUF — carregado localmente sem pesos",
        "hash":   "FALLBACK hash deterministico — inicie o orn-server para qualidade maxima",
    }
    logger.info("[BUILD] Pitstop tokenizador: %s", _MODE_LABELS.get(mode, mode))

    return tok


def _build_index_pitstop_teardown(tok: "TokenizerBridge | None") -> None:
    """Loga estatísticas e fecha o tokenizador no finally do build_index()."""
    if tok is None:
        return
    stats = tok.stats()
    logger.info(
        "[BUILD] Pitstop finalizado — tokenizados=%d fallback=%d erros=%d modo=%s",
        stats.get("tokenized", 0),
        stats.get("fallback", 0),
        stats.get("errors", 0),
        stats.get("mode", "?"),
    )
    tok.close()

def zim_to_source_id(zim_path: str | Path) -> str:
    """Deriva um source_id estável a partir do stem do arquivo ZIM."""
    name = Path(zim_path).stem
    name = name.replace("-", "_").replace(".", "_")
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return re.sub(r"_+", "_", name).strip("_").lower()


def source_id_to_db(source_id: str) -> Path:
    return INDEX_DIR / f"{source_id}.db"


def find_zim_for_source(source_id: str) -> Optional[Path]:
    if ZIM_DIR.exists():
        for zim in ZIM_DIR.glob("*.zim"):
            if zim_to_source_id(zim) == source_id:
                return zim
    return None


# ---------------------------------------------------------------------------
# Iterador de entradas ZIM
# ---------------------------------------------------------------------------

def _iter_zim_entries(
    zim_path: str,
    verbose: bool = True,
    start_scanned: int = 0,
) -> Iterator[tuple[int, str, str, str]]:
    """Itera entradas HTML válidas de um ZIM.

    Yields:
        (scanned_idx, title, path, html_content)
    """
    import pyzim  # lazy — OSL-3

    p = Path(zim_path).absolute()
    stats = dict(scanned=0, yielded=0, redirect=0, non_html=0, empty=0, error=0)

    with pyzim.Zim.open(str(p), mode="r") as zim:
        for entry in zim.iter_entries():
            stats["scanned"] += 1
            idx = stats["scanned"]

            if start_scanned and idx <= start_scanned:
                continue

            if verbose and idx % 5000 == 0:
                logger.info(
                    "[ZIM] scanned=%d yielded=%d redirect=%d non_html=%d empty=%d",
                    idx, stats["yielded"], stats["redirect"],
                    stats["non_html"], stats["empty"],
                )

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

            if not _is_html(content_bytes):
                stats["non_html"] += 1
                continue

            try:
                title = _decode_attr(entry, "title") or ""
                path  = _decode_attr(entry, "url") or _decode_attr(entry, "path") or ""
                if not title:
                    title = path.split("/")[-1].replace("_", " ").strip()
                html = content_bytes.decode("utf-8", errors="replace")
                stats["yielded"] += 1
                yield idx, title, path, html
            except Exception:
                stats["error"] += 1
                continue

    if verbose:
        logger.info(
            "[ZIM] total: scanned=%d yielded=%d redirect=%d non_html=%d empty=%d error=%d",
            stats["scanned"], stats["yielded"], stats["redirect"],
            stats["non_html"], stats["empty"], stats["error"],
        )


def _is_html(content: bytes) -> bool:
    head = content[:400].lower()
    return (
        b"<html" in head or b"<!doctype" in head or b"<body" in head
        or b"<p" in head or b"<div" in head
        or b"<h1" in head or b"<h2" in head
        or content[:1] == b"<"
    )


def _decode_attr(entry, attr: str) -> str:
    val = getattr(entry, attr, None)
    if val is None:
        return ""
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="ignore")
    return str(val).strip()


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


# ---------------------------------------------------------------------------
# Worker de processamento de entrada (thread-safe, sem closures)
# ---------------------------------------------------------------------------

@dataclass
class _EntryResult:
    scanned_idx: int
    title: str
    path: str
    content_hash: str
    compressed: bytes
    combined_tokens: list
    title_trigrams: set


def _process_entry(
    scanned_idx: int,
    title: str,
    path: str,
    html: str,
    vocab,
    max_chars: int,
) -> Optional[_EntryResult]:
    """Processa uma entrada ZIM em thread worker.

    Retorna None se o conteúdo for inválido/curto demais (OSL-15).
    Não levanta exceções — falhas viram None.
    """
    from engine.tools.local_index._text_utils import (  # lazy — OSL-3
        strip_html, compress, normalize_text_for_match, trigrams_for,
    )

    body = strip_html(html, max_chars=max_chars)
    if len(body.strip()) < 50:
        return None

    try:
        body_bytes  = body.encode("utf-8")
        title_bytes = title.encode("utf-8")

        qtoks = vocab.tokenize(body_bytes,  add_bos=False)
        ttoks = vocab.tokenize(title_bytes, add_bos=False)

        body_arr = array.array("i", qtoks)
        payload  = body_arr.tobytes()
        h        = hashlib.md5(payload).hexdigest()
        compressed = compress(payload)

        try:
            combined = ttoks + ttoks + qtoks
        except Exception:
            combined = qtoks

        tnorm = normalize_text_for_match(title)
        trigs = trigrams_for(tnorm)

        return _EntryResult(
            scanned_idx=scanned_idx,
            title=title,
            path=path,
            content_hash=h,
            compressed=compressed,
            combined_tokens=combined,
            title_trigrams=trigs,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Setup e manutenção do banco SQLite
# ---------------------------------------------------------------------------

def _init_db(con: sqlite3.Connection) -> None:
    """Cria tabelas e índices se ainda não existirem."""
    con.execute("PRAGMA page_size=4096")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    try:
        con.execute("PRAGMA cache_size = -20000")
    except Exception:
        pass

    con.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_id INTEGER PRIMARY KEY,
            title TEXT,
            path TEXT,
            tokens BLOB,   -- MUDOU PARA BLOB
            body BLOB,     -- MUDOU PARA BLOB
            body_hash TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_documents_title ON documents(title)")
    con.commit()
    con.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            id            INTEGER PRIMARY KEY,
            title         TEXT,
            path          TEXT,
            content_hash  TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS content_pool (
            hash       TEXT PRIMARY KEY,
            token_blob BLOB
        )
    """)
    con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_pages_hash       ON pages(content_hash)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS title_trigrams (
            trigram TEXT,
            doc_id  INTEGER
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_title_trigrams_trigram ON title_trigrams(trigram)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_title_trigrams_doc     ON title_trigrams(doc_id)")


@dataclass
class _ResumeState:
    mode: bool = False
    start_scanned: int = 0
    start_doc_id: int = 0


def _check_resume(db_path: str) -> _ResumeState:
    """Lê meta do DB para decidir se é retomada ou rebuild."""
    state = _ResumeState()
    db_p = Path(db_path)
    if not db_p.exists():
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
                state.mode         = True
                state.start_scanned = int(meta.get("build_scanned_entries", "0") or 0)
                state.start_doc_id  = int(meta.get("build_docs_processed",  "0") or 0)
        finally:
            probe.close()
    except Exception:
        pass

    return state


def _cleanup_stale(db_path: str, inv_dir: Path) -> None:
    """Remove arquivos de build anterior (não-resume)."""
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


# ---------------------------------------------------------------------------
# Drenagem de futures (antes era código duplicado em dois lugares)
# ---------------------------------------------------------------------------

@dataclass
class _BuildAccumulator:
    """Buffers que acumulam resultados entre commits."""
    seen_hashes: set         = field(default_factory=set)
    content_pending: dict    = field(default_factory=dict)
    buf_pages: list          = field(default_factory=list)
    title_trigrams: list     = field(default_factory=list)
    count: int               = 0
    deduplicated: int        = 0
    last_scanned: int        = 0


def _drain_futures(
    futures: list,
    acc: _BuildAccumulator,
    inv_builder: Optional[InvertedIndexBuilder],
    content_flush_batch: int,
) -> None:
    """Coleta resultados de futures e acumula nos buffers.

    OSL-4: só acumula — não faz I/O de DB. Chamador decide quando flushar.
    """
    for future in concurrent.futures.as_completed(futures):
        res: Optional[_EntryResult] = future.result()
        if res is None:
            continue

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

        # Flush parcial de content_pending para não explodir RAM
        if len(acc.content_pending) >= content_flush_batch:
            # Sinaliza para o chamador que há dados para flushar;
            # o flush real acontece em _flush_content (precisa da conexão).
            pass  # flush controlado externamente via len(acc.content_pending)


def _flush_content(con: sqlite3.Connection, acc: _BuildAccumulator) -> None:
    """Grava content_pending no banco e limpa o buffer."""
    if not acc.content_pending:
        return
    items = list(acc.content_pending.items())
    with orn_span("build.sql_insert", category="index"):
        try:
            con.executemany(
                "INSERT OR IGNORE INTO content_pool (hash, token_blob) VALUES (?, ?)",
                items,
            )
        except Exception:
            for k, v in items:
                try:
                    con.execute(
                        "INSERT OR IGNORE INTO content_pool (hash, token_blob) VALUES (?, ?)",
                        (k, v),
                    )
                except Exception:
                    pass
    acc.content_pending.clear()


def _commit_batch(
    con: sqlite3.Connection,
    acc: _BuildAccumulator,
    verbose: bool,
) -> None:
    """Grava pages, trigrams e metadata; faz COMMIT e abre nova transação."""
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
        acc.title_trigrams.clear()

    con.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('build_scanned_entries', ?)",
        (str(acc.last_scanned),),
    )
    con.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('build_docs_processed', ?)",
        (str(acc.count),),
    )
    con.execute("COMMIT")
    con.execute("BEGIN")
    acc.buf_pages.clear()

    if verbose:
        logger.info("[BUILD] ⏳ %d artigos processados e salvos no DB...", acc.count)


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def build_index(
    zim_path: str,
    source_id: Optional[str] = None,
    batch_size: int = 1000,
    verbose: bool = True,
) -> Path:
    """Constrói (ou retoma) o índice SQLite a partir de um arquivo ZIM.

    Args:
        zim_path:   Caminho para o arquivo .zim.
        source_id:  Identificador do índice. Derivado do nome do ZIM se None.
        batch_size: Número de entries por batch de commit.
        verbose:    Emite logs de progresso.

    Returns:
        Path para o arquivo .db gerado.

    Raises:
        FileNotFoundError: ZIM não encontrado.
        ImportError:       pyzim não instalado.
    """
    try:
        import pyzim  # noqa: F401 — valida antes de qualquer trabalho
    except ImportError:
        raise ImportError("pyzim não instalado. Execute: pip install pyzim")

    zim_path = str(zim_path)
    if not Path(zim_path).exists():
        available = sorted(z.name for z in ZIM_DIR.glob("*.zim")) if ZIM_DIR.exists() else []
        hint = "\nZIMs disponíveis: " + ", ".join(available[:5]) if available else ""
        raise FileNotFoundError(f"ZIM não encontrado: {zim_path}{hint}")

    # Importações lazy de dependências do pacote (OSL-3)
    from engine.tools.local_index._tokenizer import TokenizerBridge
    from engine.tools.local_index._cache    import LocalIndexCache

    vocab = TokenizerBridge.get_vocab()

    if source_id is None:
        source_id = zim_to_source_id(zim_path)

    LocalIndexCache.evict(source_id)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    db_path = str(source_id_to_db(source_id))
    inv_dir = INDEX_DIR / source_id

    build_inverted = os.environ.get("SICDOX_BUILD_INVERTED", "0").strip().lower() not in ("0", "false", "no")
    max_chars      = int(os.environ.get("SICDOX_MAX_CHARS",      "64000"))
    content_batch  = int(os.environ.get("SICDOX_CONTENT_BATCH",  "256"))

    # Decide resume vs rebuild
    resume = _check_resume(db_path)
    if Path(db_path).exists() and not resume.mode:
        logger.info("[BUILD] DB existente encontrado, removendo para rebuild: %s", db_path)
        _cleanup_stale(db_path, inv_dir)

    if verbose:
        if resume.mode:
            logger.info("[BUILD] Retomando build... DB=%s start_scanned=%d", db_path, resume.start_scanned)
        else:
            logger.info("[BUILD] Construindo banco tokenizado... DB: %s", db_path)

    inv_builder: Optional[InvertedIndexBuilder] = InvertedIndexBuilder() if build_inverted else None
    acc = _BuildAccumulator(count=resume.start_doc_id, last_scanned=resume.start_scanned)
    t0  = time.monotonic()
    workers = (os.cpu_count() or 4) + 2

    con = sqlite3.connect(db_path, isolation_level=None)
    try:
        _init_db(con)

        con.execute("BEGIN")
        con.execute("INSERT OR REPLACE INTO meta VALUES ('build_status', 'in_progress')")
        con.execute("INSERT OR REPLACE INTO meta VALUES ('build_scanned_entries', ?)", (str(resume.start_scanned),))
        con.execute("INSERT OR REPLACE INTO meta VALUES ('build_docs_processed',  ?)", (str(resume.start_doc_id),))

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures: list = []

            for scanned_idx, title, path, html in _iter_zim_entries(
                zim_path, verbose=verbose, start_scanned=resume.start_scanned
            ):
                futures.append(
                    pool.submit(_process_entry, scanned_idx, title, path, html, vocab, max_chars)
                )

                if len(futures) >= batch_size:
                    _drain_futures(futures, acc, inv_builder, content_batch)
                    futures.clear()
                    if len(acc.content_pending) >= content_batch:
                        _flush_content(con, acc)
                    _commit_batch(con, acc, verbose)

            # Flush final da fila
            if futures:
                _drain_futures(futures, acc, inv_builder, content_batch)
                futures.clear()

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
            logger.info("[BUILD] Escrevendo índice invertido em disco: %s", inv_dir)
        inv_builder.write(inv_dir)

    if verbose:
        logger.info(
            "[BUILD] ✅ CONCLUÍDO: %d artigos (dedup: %d) em %.1fs",
            acc.count, acc.deduplicated, time.monotonic() - t0,
        )

    return Path(db_path)