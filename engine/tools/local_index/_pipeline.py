# -*- coding: utf-8 -*-
# engine/tools/local_index/_pipeline.py
"""
ORN — LocalIndex / Pipeline em Rounds (Hefesto Cadenciado)
Substitui o loop ansioso de build_index() por um pipeline de 3 estágios
sobrepostos, com buffer controlado e commit em lote.

Diagnóstico (telemetria 2026-04-10):
  - con.execute("COMMIT")  → 158220 hits  ← GARGALO PRINCIPAL
  - inflight.popleft()     → 29021 hits   ← futures acumulando
  - for entry in zim       → 2712 hits    ← leitura bloqueante
  - Processamento ansioso + I/O ocioso = memória desperdiçada

Solução — 3 estágios em threads separadas com filas de tamanho fixo:

  ┌─────────────────────────────────────────────────────────────┐
  │  [Stage 1: Produtor ZIM]  thread_producer                   │
  │  Lê ZIM, descomprime, decodifica HTML                       │
  │  ↓ queue_raw (maxsize=PRE_LOAD) — controla memória          │
  │  [Stage 2: Pitstop]       thread_main (loop principal)      │
  │  strip_html + tokenize (TokenizerBridge)                    │
  │  ↓ queue_cooked (maxsize=WRITE_BUFFER)                      │
  │  [Stage 3: Writer]        thread_writer                     │
  │  INSERT + COMMIT a cada COMMIT_BATCH linhas                 │
  └─────────────────────────────────────────────────────────────┘

Parâmetros calibrados para N2808 (169 MB RAM disponível, 2 cores):
  PRE_LOAD    = 4   articles em RAM simultaneamente no buffer raw
  WRITE_BUFFER= 4   articles processados aguardando escrita
  COMMIT_BATCH= 500 INSERTs por COMMIT (era 1 — causava 158k commits)

OSL-3:  TokenizerBridge instanciado lazy no pitstop.
OSL-4:  Cada estágio em função própria.
OSL-7:  _SENTINEL sinaliza fim de pipeline sem exceções.
OSL-15: Erro em qualquer estágio → flag de abort, pipeline drena limpo.
OSL-18: stdlib only (threading, queue).
God: Hefesto — forja cadenciada; cada peça entra quando a anterior sai.
"""

from __future__ import annotations

import logging
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

import array
from engine.tools.local_index._text_utils import compress

logger = logging.getLogger("engine.tools.local_index.pipeline")

# ---------------------------------------------------------------------------
# Configuração do pipeline (calibrada para N2808)
# ---------------------------------------------------------------------------

PRE_LOAD     = 6      # artigos em buffer raw (Stage 1 → Stage 2)
WRITE_BUFFER = 6      # artigos processados aguardando escrita (Stage 2 → Stage 3)
COMMIT_BATCH = 2000    # INSERTs por COMMIT (era 1 por artigo → 158k commits)
QUEUE_TIMEOUT = 3.0   # segundos de espera por item antes de checar abort

_SENTINEL = object()  # sinal de fim de estágio


# ---------------------------------------------------------------------------
# Tipos de dados de estágio
# ---------------------------------------------------------------------------

@dataclass
class _RawEntry:
    """Saída do Stage 1: artigo bruto do ZIM."""
    idx:   int
    title: str
    path:  str
    html:  str


@dataclass
class _CookedEntry:
    """Saída do Stage 2: artigo processado pronto para INSERT."""
    doc_id:  int
    title:   str
    path:    str
    tokens:  bytes      # Mudou: agora armazenará o array binário (C-style)
    body:    bytes      # Mudou: agora armazenará o texto comprimido com zlib
    body_hash: str


# ---------------------------------------------------------------------------
# Contexto compartilhado do pipeline
# ---------------------------------------------------------------------------

@dataclass
class _PipelineCtx:
    """Estado compartilhado entre threads do pipeline."""
    abort:      threading.Event = field(default_factory=threading.Event)
    error:      Exception | None = None
    stats: dict = field(default_factory=lambda: {
        "read":    0,
        "cooked":  0,
        "written": 0,
        "commits": 0,
        "skipped": 0,
        "errors":  0,
    })
    lock: threading.Lock = field(default_factory=threading.Lock)

    def fail(self, exc: Exception) -> None:
        with self.lock:
            if self.error is None:
                self.error = exc
        self.abort.set()


# ---------------------------------------------------------------------------
# Stage 1: Produtor ZIM
# ---------------------------------------------------------------------------

def _stage_producer(
    zim_path: str,
    start_scanned: int,
    q_raw: "queue.Queue[_RawEntry | object]",
    ctx: _PipelineCtx,
    verbose: bool = True,
) -> None:
    """Thread produtora: lê ZIM e alimenta q_raw."""
    try:
        import pyzim  # lazy

        p = Path(zim_path).absolute()
        scanned = 0
        yielded = 0

        with pyzim.Zim.open(str(p), mode="r") as zim:
            for entry in zim.iter_entries():
                if ctx.abort.is_set():
                    break

                scanned += 1
                if start_scanned and scanned <= start_scanned:
                    continue

                if verbose and scanned % 5000 == 0:
                    logger.info(
                        "[PIPELINE:ZIM] scanned=%d yielded=%d", scanned, yielded
                    )

                # Filtra redirects e namespaces inválidos
                if getattr(entry, "is_redirect", False):
                    continue
                ns = getattr(entry, "namespace", None)
                if ns is not None:
                    if isinstance(ns, bytes):
                        ns = ns.decode("utf-8", errors="ignore")
                    if str(ns).strip() in ("I", "-", "X"):
                        continue

                # Lê conteúdo
                try:
                    content_bytes = entry.get_data().tobytes()
                    if not content_bytes:
                        continue

                    # Verifica se é HTML
                    sniff = content_bytes[:512].lower()
                    if b"<html" not in sniff and b"<!doctype" not in sniff:
                        continue

                    title = getattr(entry, "title", "") or ""
                    path  = getattr(entry, "url", "") or getattr(entry, "path", "") or ""
                    if not title:
                        title = path.split("/")[-1].replace("_", " ").strip()

                    html = content_bytes.decode("utf-8", errors="replace")

                    raw = _RawEntry(idx=scanned, title=title, path=path, html=html)

                    # Bloqueia se buffer cheio — controla memória
                    while not ctx.abort.is_set():
                        try:
                            q_raw.put(raw, timeout=QUEUE_TIMEOUT)
                            yielded += 1
                            break
                        except queue.Full:
                            continue  # aguarda Stage 2 consumir

                except Exception as exc:
                    logger.debug("[PIPELINE:ZIM] entry erro: %s", exc)
                    with ctx.lock:
                        ctx.stats["skipped"] += 1
                    continue

        logger.info(
            "[PIPELINE:ZIM] concluído — scanned=%d yielded=%d", scanned, yielded
        )
        with ctx.lock:
            ctx.stats["read"] = yielded

    except Exception as exc:
        logger.error("[PIPELINE:ZIM] erro fatal: %s", exc, exc_info=True)
        ctx.fail(exc)

    finally:
        q_raw.put(_SENTINEL)  # sinaliza fim para Stage 2


# ---------------------------------------------------------------------------
# Stage 2: Pitstop (processador — roda na thread principal)
# ---------------------------------------------------------------------------

def _stage_pitstop(
    q_raw:    "queue.Queue[_RawEntry | object]",
    q_cooked: "queue.Queue[_CookedEntry | object]",
    ctx:      _PipelineCtx,
    tok:      Any,  # TokenizerBridge | None
) -> None:
    """Loop principal: consome raw, tokeniza, alimenta q_cooked."""
    import hashlib
    import array  # <-- NOVO: import necessário para o array binário

    from engine.tools.local_index._text_utils import (  # lazy
        extract_code_blocks,
        restore_code_placeholders,
        clean_body,
        strip_html,
        compress,  # <-- NOVO: Importamos a função de compressão
    )

    def _process(raw: _RawEntry) -> "_CookedEntry | None":
        try:
            html_no_code, code_blocks = extract_code_blocks(raw.html)
            text = strip_html(html_no_code)
            body = restore_code_placeholders(text, code_blocks)
            body = clean_body(body)
            if not body or not body.strip():
                return None

            tokens = tok.tokenize(body) if tok else _hash_tokenize(body)
            if not tokens:
                return None

            body_hash = hashlib.sha1(body.encode("utf-8", errors="ignore")).hexdigest()

            # --- MÁGICA DA COMPACTAÇÃO ACONTECE AQUI ---
            # 1. Converte a lista [1, 2, 3] num binário C de alta performance
            tokens_blob = array.array("I", tokens).tobytes()
            # 2. Comprime o texto do artigo usando zlib
            body_blob = compress(body)
            # -------------------------------------------

            return _CookedEntry(
                doc_id=raw.idx,
                title=raw.title,
                path=raw.path,
                tokens=tokens_blob,   # <-- NOVO: Enviamos o BLOB binário
                body=body_blob,       # <-- NOVO: Enviamos o BLOB comprimido
                body_hash=body_hash,
            )
        except Exception as exc:
            logger.debug("[PIPELINE:PITSTOP] erro idx=%d: %s", raw.idx, exc)
            with ctx.lock:
                ctx.stats["errors"] += 1
            return None

    try:
        while not ctx.abort.is_set():
            try:
                item = q_raw.get(timeout=QUEUE_TIMEOUT)
            except queue.Empty:
                continue

            if item is _SENTINEL:
                break  # produtor terminou

            cooked = _process(item)  # type: ignore[arg-type]

            if cooked is not None:
                with ctx.lock:
                    ctx.stats["cooked"] += 1
                # Bloqueia se buffer de escrita cheio
                while not ctx.abort.is_set():
                    try:
                        q_cooked.put(cooked, timeout=QUEUE_TIMEOUT)
                        break
                    except queue.Full:
                        continue
            else:
                with ctx.lock:
                    ctx.stats["skipped"] += 1

    except Exception as exc:
        logger.error("[PIPELINE:PITSTOP] erro fatal: %s", exc, exc_info=True)
        ctx.fail(exc)

    finally:
        q_cooked.put(_SENTINEL)  # sinaliza fim para Stage 3


# ---------------------------------------------------------------------------
# Stage 3: Writer com commit em lote
# ---------------------------------------------------------------------------

def _stage_writer(
    q_cooked:   "queue.Queue[_CookedEntry | object]",
    con:        sqlite3.Connection,
    inv_builder: Any,  # InvertedIndexBuilder | None
    ctx:        _PipelineCtx,
    progress_cb: Callable[[int], None] | None = None,
) -> None:
    """Thread escritora: INSERTs em lote + COMMIT a cada COMMIT_BATCH."""
    batch_content:   list[tuple] = []
    batch_inv:       list[tuple[int, list[int]]] = []  # (doc_id, tokens)
    total_written = 0
    total_commits = 0

    def _flush():
        nonlocal total_written, total_commits
        if not batch_content:
            return
        try:
            con.executemany(
                "INSERT OR IGNORE INTO content_pool (hash, token_blob) VALUES (?, ?)",
                batch_content,
            )
            # Insere no índice invertido (em memória)
            if inv_builder is not None:
                for doc_id, tokens in batch_inv:
                    inv_builder.add_document(doc_id, tokens)

            con.execute("COMMIT")    # ← 1 COMMIT por COMMIT_BATCH (era 1 por artigo)
            con.execute("BEGIN")

            total_written += len(batch_content)
            total_commits += 1
            batch_content.clear()
            batch_inv.clear()

            with ctx.lock:
                ctx.stats["written"] = total_written
                ctx.stats["commits"] = total_commits

            if progress_cb:
                progress_cb(total_written)

        except Exception as exc:
            logger.error("[PIPELINE:WRITER] erro no flush: %s", exc, exc_info=True)
            ctx.fail(exc)

    try:
        con.execute("BEGIN")

        while not ctx.abort.is_set():
            try:
                item = q_cooked.get(timeout=QUEUE_TIMEOUT)
            except queue.Empty:
                continue

            if item is _SENTINEL:
                _flush()  # flush final
                break

            entry: _CookedEntry = item  # type: ignore[assignment]

            # Serializa tokens como blob de int32 little-endian
            import array as _array
            tok_arr = _array.array("i", entry.tokens)
            blob = tok_arr.tobytes()

            batch_content.append((entry.body_hash, blob))
            batch_inv.append((entry.doc_id, entry.tokens))

            if len(batch_content) >= COMMIT_BATCH:
                _flush()

        # Garante commit final mesmo se abortado
        if batch_content:
            _flush()

    except Exception as exc:
        logger.error("[PIPELINE:WRITER] erro fatal: %s", exc, exc_info=True)
        ctx.fail(exc)

    finally:
        with ctx.lock:
            ctx.stats["commits"] = total_commits
            ctx.stats["written"] = total_written


# ---------------------------------------------------------------------------
# Fallback de tokenização (sem TokenizerBridge)
# ---------------------------------------------------------------------------

def _hash_tokenize(text: str) -> list[int]:
    import hashlib
    import struct
    tokens = []
    for word in text.lower().split():
        h = struct.unpack(">I", hashlib.md5(word.encode("utf-8", errors="ignore")).digest()[:4])[0]
        tokens.append(h % (2**30))
    return tokens


# ---------------------------------------------------------------------------
# Função pública: run_pipeline()
# ---------------------------------------------------------------------------

def run_pipeline(
    zim_path:        str | Path,
    con:             sqlite3.Connection,
    inv_builder:     Any = None,
    start_scanned:   int = 0,
    tok:             Any = None,   # TokenizerBridge | None
    progress_every:  int = 400,
    verbose:         bool = True,
) -> dict:
    """Executa o pipeline de 3 estágios e retorna estatísticas.

    Args:
        zim_path:       Caminho do arquivo ZIM.
        con:            Conexão SQLite já aberta com tabelas criadas.
        inv_builder:    InvertedIndexBuilder (opcional — pode ser None).
        start_scanned:  Retomar a partir deste índice (resume).
        tok:            TokenizerBridge pré-aquecido (pitstop já feito).
        progress_every: Loga progresso a cada N artigos escritos.
        verbose:        Loga progresso do ZIM.

    Returns:
        dict com stats: read, cooked, written, commits, skipped, errors.
    """
    q_raw    = queue.Queue(maxsize=PRE_LOAD)
    q_cooked = queue.Queue(maxsize=WRITE_BUFFER)
    ctx      = _PipelineCtx()

    _last_progress = [0]

    def _progress_cb(n: int) -> None:
        if n - _last_progress[0] >= progress_every:
            _last_progress[0] = n
            with ctx.lock:
                s = dict(ctx.stats)
            logger.info(
                "[PIPELINE] ⏳ %d escritos | commits=%d | pitstop=%d | skipped=%d",
                s["written"], s["commits"], s["cooked"], s["skipped"],
            )

    # Stage 1: produtor em thread própria
    t_producer = threading.Thread(
        target=_stage_producer,
        args=(str(zim_path), start_scanned, q_raw, ctx, verbose),
        name="orn-zim-producer",
        daemon=True,
    )

    # Stage 3: writer em thread própria
    t_writer = threading.Thread(
        target=_stage_writer,
        args=(q_cooked, con, inv_builder, ctx, _progress_cb),
        name="orn-db-writer",
        daemon=True,
    )

    t0 = time.monotonic()
    t_producer.start()
    t_writer.start()

    # Stage 2: pitstop na thread principal
    try:
        _stage_pitstop(q_raw, q_cooked, ctx, tok)
    except KeyboardInterrupt:
        logger.warning("[PIPELINE] Interrompido pelo usuário — aguardando flush...")
        ctx.abort.set()

    # Aguarda threads
    t_producer.join(timeout=10.0)
    t_writer.join(timeout=30.0)  # writer pode estar no flush final

    elapsed = time.monotonic() - t0

    with ctx.lock:
        stats = dict(ctx.stats)

    stats["elapsed_s"]  = round(elapsed, 1)
    stats["commits_saved"] = max(0, stats["written"] - stats["commits"])
    stats["commit_batch"]  = COMMIT_BATCH

    # Loga resumo final
    if ctx.error:
        logger.error("[PIPELINE] Erro fatal: %s", ctx.error)
    else:
        logger.info(
            "[PIPELINE] ✅ Concluído em %.0fs — "
            "written=%d commits=%d (era ~%d sem lote) pitstop=%d skipped=%d",
            elapsed,
            stats["written"],
            stats["commits"],
            stats["written"],      # era 1 commit por artigo
            stats["cooked"],
            stats["skipped"],
        )

    if ctx.error:
        raise ctx.error

    return stats