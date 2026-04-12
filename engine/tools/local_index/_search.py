# -*- coding: utf-8 -*-
# engine/tools/local_index/_search.py
"""
ORN — LocalIndex / Search
Pipeline de busca local sobre o banco SQLite tokenizado.

Fases de search_local:
  1. Exact title match   — retorno imediato se título == query
  2. Candidate harvest   — IDs via InvertedIndex + LIKE + fuzzy title
  3. Scoring             — cada candidato recebe score BM25-like
  4. Result assembly     — top-N candidatos viram LocalResult

Tipos exportados: LocalResult
Funções exportadas: search_local, index_info, list_indexes

OSL-4:  Cada função faz uma coisa.
OSL-7:  search_local() sempre retorna lista (nunca None).
OSL-15: Erros de DB/decode viram candidatos ignorados, não exceções.
OSL-18: stdlib + dependências de projeto.
"""

from __future__ import annotations

import array
import hashlib
import logging
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from engine.tools.local_index._text_utils import decompress

logger = logging.getLogger("engine.tools.local_index.search")

# ---------------------------------------------------------------------------
# Imports lazy de dependências do pacote (OSL-3)
# ---------------------------------------------------------------------------
# Resolvidos em tempo de chamada para evitar importação circular.
#
#   from engine.tools.local_index._cache     import LocalIndexCache
#   from engine.tools.local_index._tokenizer import TokenizerBridge
#   from engine.tools.local_index._text_utils import (
#       normalize_text_for_match, trigrams_for, similarity_ratio,
#       decompress, clean_body, like_escape,
#       score_code_only_match, format_code_only_body,
#   )
#   from engine.tools.local_index._config import ZIM_DIR, INDEX_DIR
#   from engine.tools.local_index._build  import (
#       zim_to_source_id, source_id_to_db, find_zim_for_source
#   )

# ---------------------------------------------------------------------------
# Constantes de scoring
# ---------------------------------------------------------------------------

_SCORE_WEIGHTS_NORMAL = dict(
    title_boost=120.0,
    early_density=300.0,
    density=120.0,
    tf=30.0,
    front_bonus=80.0,
)
_SCORE_WEIGHTS_CODE = dict(
    title_boost=45.0,
    early_density=420.0,
    density=220.0,
    tf=55.0,
    front_bonus=20.0,
)


# ===========================================================================
# LocalResult — tipo de retorno de search_local
# ===========================================================================

class LocalResult:
    """Resultado de uma busca local com snippet extraível.

    Attributes:
        source: Identificador da fonte (ex: "wikipedia_en-local").
        title:  Título do artigo.
        body:   Texto limpo do artigo.
        path:   Caminho interno no ZIM.
    """

    __slots__ = ("source", "title", "body", "path")

    def __init__(self, source: str, title: str, body: str, path: str = "") -> None:
        self.source = source
        self.title  = title
        self.body   = body
        self.path   = path

    @property
    def ok(self) -> bool:
        return bool(self.title and self.body.strip())

    # ------------------------------------------------------------------
    # Snippet com highlight de termos e proteção de blocos
    # ------------------------------------------------------------------

    def get_snippet(self, query: str = "", max_chars: int = 1200, n_snippets: int = 3) -> str:
        """Retorna trecho relevante do body com termos da query em **negrito**.

        Nunca corta um bloco [CODE-BEGIN] ou [MATH-BEGIN] no meio.
        """
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
    """Posições de ocorrência de cada palavra da query em `text`."""
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
    """Estende `right` para não cortar um bloco [CODE-END] ou [MATH-END] aberto."""
    for open_tag, close_tag in (("[CODE-BEGIN", "[CODE-END]"), ("[MATH-BEGIN", "[MATH-END]")):
        last_open  = text.rfind(open_tag, 0, right)
        last_close = text.rfind(close_tag, 0, right)
        if last_open > last_close:
            end_idx = text.find(close_tag, right)
            if end_idx != -1:
                right = max(right, end_idx + len(close_tag))
    return right


def _highlight_words(part: str, words: list[str]) -> str:
    """Envolve cada palavra (exceto marcadores internos) em **negrito**."""
    skip = {"code", "begin", "end", "math"}
    for w in words:
        if w.upper() in skip:
            continue
        try:
            part = re.sub(
                rf"(?i)\b{re.escape(w)}\b",
                lambda m: f"**{m.group(0)}**",
                part,
            )
        except Exception:
            pass
    return part


def _build_snippet_from_positions(
    text: str,
    positions: list[int],
    q: str,
    max_chars: int,
    n_snippets: int,
) -> str:
    words    = re.findall(r"[A-Za-z0-9_]{2,}", q.lower())
    windows: list[tuple[int, int]] = []

    for pos in positions:
        if len(windows) >= n_snippets:
            break
        left  = max(0, pos - 120)
        right = min(len(text), pos + 420)
        # Evita sobreposição com janela anterior
        if windows and left < windows[-1][1]:
            left = windows[-1][1] + 1
        right = _safe_extend_right(text, right)
        windows.append((left, right))

    parts: list[str] = []
    total = 0
    for left, right in windows:
        part = text[left:right]
        part = _highlight_words(part, words)
        if left  > 0:          part = "..." + part
        if right < len(text):  part = part  + "..."
        parts.append(part)
        total += len(part)
        if total >= max_chars:
            break

    return "\n\n".join(parts)


def _leading_snippet(text: str, max_chars: int) -> str:
    """Fallback: retorna o início do texto sem cortar blocos abertos."""
    end = _safe_extend_right(text, max_chars)
    # Só vai além se não estourar 3× o limite
    if end > max_chars * 3:
        end = max_chars
    leading = text[:end].strip()
    if len(leading) < len(text):
        leading += "..."
    return leading


# ===========================================================================
# Helpers internos de search_local
# ===========================================================================

def _normalize_source_id(source_id: str) -> str:
    s = source_id.replace("-", "_").replace(".", "_")
    s = re.sub(r"[^a-zA-Z0-9_]", "_", s)
    return re.sub(r"_+", "_", s).strip("_").lower()


def _simple_query_tokens(text: str) -> list[int]:
    """Tokenização leve por hash MD5 (modo SICDOX_FAST_MODE)."""
    return [
        int(hashlib.md5(w.encode("utf-8")).hexdigest()[:8], 16) & 0x7FFFFFFF
        for w in re.findall(r"[A-Za-z0-9_]+|[^\w\s]", text)
    ]


def _fuzzy_title_search(
    con: sqlite3.Connection,
    query: str,
    candidate_limit: int = 30,
    final_limit: int = 10,
) -> list[int]:
    """Busca por trigramas de título + re-rankeamento por similaridade."""
    from engine.tools.local_index._text_utils import (
        normalize_text_for_match, trigrams_for, similarity_ratio,
    )

    qnorm = normalize_text_for_match(query)
    trigs = list(trigrams_for(qnorm))
    if not trigs:
        return []

    ph  = ",".join("?" * len(trigs))
    sql = f"""
        SELECT doc_id, COUNT(*) AS cnt
        FROM   title_trigrams
        WHERE  trigram IN ({ph})
        GROUP BY doc_id
        ORDER BY cnt DESC
        LIMIT ?
    """
    rows = con.execute(sql, (*trigs, candidate_limit)).fetchall()
    if not rows:
        return []

    doc_ids = [r[0] for r in rows]
    ph2     = ",".join("?" * len(doc_ids))
    title_map = {
        r[0]: r[1]
        for r in con.execute(
            f"SELECT id, title FROM pages WHERE id IN ({ph2})", doc_ids
        ).fetchall()
    }

    scored: list[tuple[int, float]] = []
    for doc_id in doc_ids:
        title = title_map.get(doc_id, "")
        tnorm = normalize_text_for_match(title)
        score = similarity_ratio(qnorm, tnorm)
        if tnorm == qnorm:
            score += 0.6
        elif tnorm.startswith(qnorm):
            score += 0.35
        scored.append((doc_id, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [doc_id for doc_id, _ in scored[:final_limit]]


# ---------------------------------------------------------------------------
# Coleta de candidatos
# ---------------------------------------------------------------------------

def _harvest_candidates(
    con: sqlite3.Connection,
    searcher,
    q_raw: str,
    code_only: bool,
) -> tuple[list[int], set[int]]:
    """Coleta IDs de candidatos via InvertedIndex + LIKE + fuzzy.

    Returns:
        (candidates, inverted_hit_ids)
        inverted_hit_ids: IDs que vieram do índice invertido (boost leve no score).
    """
    from engine.tools.local_index._text_utils import like_escape
    from engine.tools.local_index._tokenizer  import TokenizerBridge
    import os

    candidates:   list[int] = []
    inverted_ids: set[int]  = set()

    # 1. Índice invertido
    if searcher:
        try:
            if os.environ.get("SICDOX_FAST_MODE", "").strip().lower() not in ("", "0", "false", "no"):
                qtoks = _simple_query_tokens(q_raw)
            else:
                vocab = TokenizerBridge.get_vocab()
                qtoks = vocab.tokenize(q_raw.encode("utf-8"), add_bos=False)
            body_ids = searcher.search(qtoks, limit=120 if code_only else 80) or []
            candidates.extend(body_ids)
            inverted_ids = set(body_ids)
        except Exception:
            pass

    # 2. LIKE por título
    q_esc = like_escape(q_raw)
    try:
        rows = con.execute(
            "SELECT p.id FROM pages p "
            "WHERE p.title = ? OR p.title LIKE ? ESCAPE '\\' OR p.title LIKE ? ESCAPE '\\' "
            "LIMIT 80",
            (q_raw, f"{q_esc}%", f"%{q_esc}%"),
        ).fetchall()
        title_ids = [r[0] for r in rows]
    except Exception:
        title_ids = []

    # 3. Fuzzy fallback quando LIKE não encontrou nada
    if not title_ids:
        try:
            title_ids = _fuzzy_title_search(con, q_raw, candidate_limit=200, final_limit=60)
        except Exception:
            title_ids = []

    for tid in title_ids:
        if tid not in candidates:
            candidates.append(tid)

    return candidates, inverted_ids


# ---------------------------------------------------------------------------
# Decodificação de blob
# ---------------------------------------------------------------------------

@dataclass
class _DecodedBody:
    tokens:    Optional[list[int]]
    body_text: str


def _decode_blob(blob: bytes, title: str) -> _DecodedBody:
    """Descomprime e decodifica o token_blob de uma linha do DB."""
    from engine.tools.local_index._text_utils import decompress, clean_body
    from engine.tools.local_index._tokenizer  import TokenizerBridge

    try:
        raw = decompress(blob)
        arr = array.array("i")
        arr.frombytes(raw)
        tokens = arr.tolist()

        body_text = TokenizerBridge.bytes_to_text(raw)
        body_text = clean_body(body_text, max_chars=100_000)
        if body_text.lower().startswith(title.lower()):
            body_text = re.sub(
                rf"^{re.escape(title)}\s*", "", body_text, flags=re.IGNORECASE
            ).lstrip()

        return _DecodedBody(tokens=tokens, body_text=body_text)

    except Exception:
        try:
            from engine.tools.local_index._text_utils import decompress
            from engine.tools.local_index._tokenizer  import TokenizerBridge
            body_text = TokenizerBridge.bytes_to_text(decompress(blob))
            return _DecodedBody(tokens=None, body_text=body_text)
        except Exception:
            return _DecodedBody(tokens=None, body_text="")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _title_boost(qnorm: str, title: str) -> float:
    from engine.tools.local_index._text_utils import normalize_text_for_match, similarity_ratio
    tnorm = normalize_text_for_match(title)
    if tnorm == qnorm:        return 3.0
    if tnorm.startswith(qnorm): return 1.8
    return 0.9 * similarity_ratio(qnorm, tnorm)


def _score_candidate(
    decoded: _DecodedBody,
    title: str,
    qnorm: str,
    q_raw: str,
    qwords: list[str],
    qtoken_set: set[int],
    code_only: bool,
    formula_like: bool,
) -> Optional[float]:
    """Calcula o score de um candidato.

    Returns None se o candidato deve ser descartado (não passa filtro code_only).
    """
    from engine.tools.local_index._text_utils import score_code_only_match

    tokens    = decoded.tokens
    body_text = decoded.body_text
    dl        = max(1, len(tokens) if tokens is not None else max(1, len(body_text.split())))

    # --- Filtro e TF para code_only ---
    if code_only:
        passed, tf, matched, total = score_code_only_match(body_text, q_raw, qwords)
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

    w = _SCORE_WEIGHTS_CODE if code_only else _SCORE_WEIGHTS_NORMAL

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
        if q_raw in body_text:
            score += 6.0
        elif q_raw.lower() in body_text.lower():
            score += 2.0

    return score


# ---------------------------------------------------------------------------
# Montagem de resultado
# ---------------------------------------------------------------------------

def _assemble_result(
    label: str,
    title: str,
    path: str,
    body_text: str,
    code_only: bool, 
) -> LocalResult:
    from engine.tools.local_index._text_utils import format_code_only_body

    body = body_text or ""
    if code_only:
        code_body = format_code_only_body(body)
        if code_body:
            body = code_body

    body = re.sub(r"\n\s*\n", "\n\n", body).strip()
    body = re.sub(rf"^\s*{re.escape(title)}\s*[:\-\|]?\s*(\r?\n)+", "", body, flags=re.IGNORECASE)
    body = re.sub(r"\n{3,}", "\n\n", body).lstrip()
    
    return LocalResult(
        source=label,
        title=title,
        body=body,
        path=path,
    )


# ===========================================================================
# API pública
# ===========================================================================

def search_local(
    query: str,
    source_id: str,
    limit: int = 3,
    code_only: bool = False,
) -> List[LocalResult]:
    """Busca `query` no índice local de `source_id`.

    Returns:
        Lista de até `limit` LocalResult, ordenados por relevância.
        Lista vazia em caso de erro ou sem resultados.
    """
    if not query.strip():
        return []

    from engine.tools.local_index._cache     import LocalIndexCache
    from engine.tools.local_index._tokenizer import TokenizerBridge
    from engine.tools.local_index._text_utils import (
        normalize_text_for_match, decompress,
    )

    source_id = _normalize_source_id(source_id)
    label     = f"{source_id}-local"

    try:
        con, searcher = LocalIndexCache.get(source_id)
        if not con:
            return []

        q_raw  = query.strip()
        qnorm  = normalize_text_for_match(q_raw)
        qwords = re.findall(r"[A-Za-z0-9_]+", q_raw.lower())

        # ── Fase 1: exact title match ──────────────────────────────────
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

        # ── Fase 2: coleta de candidatos ───────────────────────────────
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

        # Conjunto de tokens da query para busca rápida por posição
        try:
            vocab = TokenizerBridge.get_vocab()
            qtoks = vocab.tokenize(q_raw.encode("utf-8"), add_bos=False)
        except Exception:
            qtoks = _simple_query_tokens(q_raw)
        qtoken_set = set(int(t) for t in qtoks)

        # ── Fase 3: scoring ────────────────────────────────────────────
        scored: list[tuple[int, float, str, str, str]] = []
        for cid in candidates:
            r = row_map.get(cid)
            if not r:
                continue
            doc_id, title, path, blob = r

            decoded = _decode_blob(blob, title)
            score   = _score_candidate(
                decoded, title, qnorm, q_raw, qwords, qtoken_set, code_only, formula_like
            )
            if score is None:
                continue

            if cid in inverted_ids:
                score *= 1.03  # boost leve para hits do índice invertido

            scored.append((doc_id, score, title, path, decoded.body_text))

        scored.sort(key=lambda x: x[1], reverse=True)

        # ── Fase 4: montagem ───────────────────────────────────────────
        return [
            _assemble_result(label, title, path, body_text, code_only)
            for _, _, title, path, body_text in scored[:limit]
        ]

    except Exception:
        logger.exception("search_local failed for source_id=%s", source_id)
        return []


# ===========================================================================
# Info / listagem
# ===========================================================================

def index_info(source_id: str) -> dict:
    """Retorna metadados do índice de `source_id`."""
    from engine.tools.local_index._build  import source_id_to_db, find_zim_for_source

    db_path = source_id_to_db(source_id)
    zim     = find_zim_for_source(source_id)
    info    = {
        "source_id": source_id,
        "exists":    False,
        "articles":  0,
        "mode":      "Aguardando Build",
        "zim_path":  str(zim) if zim else "?",
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
    """Lista todos os índices conhecidos (DB existente ou ZIM disponível)."""
    from engine.tools.local_index._build  import zim_to_source_id
    import os

    try:
        from engine.tools.local_index._config import ZIM_DIR, INDEX_DIR
    except ImportError:
        ZIM_DIR   = Path(os.environ.get("SICDOX_ZIM_DIR",   "data/zim"))
        INDEX_DIR = Path(os.environ.get("SICDOX_INDEX_DIR", "data/index"))

    seen: set[str] = set()
    result: List[dict] = []

    if INDEX_DIR.exists():
        for db_file in sorted(INDEX_DIR.glob("*.db")):
            sid = db_file.stem
            seen.add(sid)
            result.append(index_info(sid))

    if ZIM_DIR.exists():
        for zim_file in sorted(ZIM_DIR.glob("*.zim")):
            sid = zim_to_source_id(zim_file)
            if sid not in seen:
                result.append({
                    "source_id": sid,
                    "articles":  0,
                    "zim_path":  str(zim_file),
                    "mode":      "Aguardando Build",
                    "exists":    False,
                })
                seen.add(sid)

    return result