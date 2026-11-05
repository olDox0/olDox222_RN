# -*- coding: utf-8 -*-
# engine/tools/consult_bridge.py
"""
Consult Bridge — RAG sobre o acervo FTS5 do Doxoade.

Conecta o ORN ao banco `~/.doxoade/consult_docs_fts5.db` (gerado pelo
subsistema `doxoade consult`) e expõe busca + formatação de contexto.

Graceful degradation: se o DB não existe, search() retorna [].

God: Hermes (bridge) + Thoth (conhecimento) + Hades (leitura).
OSL-15: qualquer erro de IO/SQLite vira return [], nunca propaga.
OSL-18: apenas stdlib (sqlite3, re).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_DB = Path.home() / ".doxoade" / "consult_docs_fts5.db"
_MAX_SNIPPET_CHARS = 500
_MAX_TOTAL_CHARS   = 2000

# Lista curta de stopwords PT/EN que não devem dominar a busca
_STOPWORDS = frozenset({
    "como", "usar", "para", "que", "com", "uma", "dos", "das",
    "the", "and", "for", "how", "use", "using", "what", "with",
    "em", "no", "na", "de", "do", "da", "se", "ou",
})

@dataclass
class ConsultResult:
    path:     str
    title:    str
    snippet:  str
    category: str = ""
    rank:     float = 0.0


class ConsultBridge:
    """Interface de leitura RAG com o banco FTS5 do Doxoade."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB

    # ------------------------------------------------------------------
    # Disponibilidade
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        try:
            return self.db_path.exists() and self.db_path.stat().st_size > 0
        except OSError:
            return False

    def _connect(self) -> sqlite3.Connection | None:
        if not self.is_available():
            return None
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=2.0)
            conn.execute("PRAGMA query_only = 1")
            conn.execute("PRAGMA cache_size = -8000")
            return conn
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Sanitização de query FTS5
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_query(query: str) -> str:
        words = re.findall(r"[A-Za-z0-9_]{2,}", query or "")
        if not words: return ""
        tokens = []
        for w in words[:8]:
            lw = w.lower()
            if lw in _STOPWORDS:
                continue
            tokens.append(f'"{w}"*' if len(w) > 2 else f'"{w}"')
        # fallback: se a query inteira era stopword, mantém ao menos os termos
        if not tokens:
            tokens = [f'"{w}"*' for w in words[:4]]
        # OR implícito → recall maior, BM25 rankeia
        return " OR ".join(tokens)

    # ------------------------------------------------------------------
    # Busca
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 5,
        category: str | None = None,
    ) -> list[ConsultResult]:
        """Busca no FTS5. Retorna [] se DB ausente ou query inválida."""
        fts_q = self._sanitize_query(query)
        if not fts_q or limit <= 0:
            return []

        conn = self._connect()
        if conn is None:
            return []

        try:
            sql = """
                SELECT f.path, f.title, f.snippet,
                       COALESCE(d.category, '') AS category
                FROM (
                    SELECT path, title,
                           snippet(docs_fts, 3, '', '', '...', 32) AS snippet,
                           rank AS rank
                    FROM docs_fts
                    WHERE docs_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                ) AS f
                LEFT JOIN docs d ON d.path = f.path
                LIMIT ?
            """
            rows = conn.execute(sql, (fts_q, max(limit * 3, 10), limit)).fetchall()
        except sqlite3.OperationalError:
            return []
        except Exception:
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

        results: list[ConsultResult] = []
        for path, title, snippet, cat in rows:
            if category and cat.lower() != category.lower():
                continue
            snip = snippet or ""
            if len(snip) > _MAX_SNIPPET_CHARS:
                snip = snip[:_MAX_SNIPPET_CHARS] + "..."
            results.append(ConsultResult(
                path=path or "",
                title=title or "",
                snippet=snip,
                category=cat or "",
            ))
        return results

    # ------------------------------------------------------------------
    # Formatação para injeção em prompt
    # ------------------------------------------------------------------

    @staticmethod
    def format_context(
        results: list[ConsultResult],
        max_chars: int = _MAX_TOTAL_CHARS,
    ) -> str:
        """Formata resultados em bloco [CONSULT-BEGIN]...[/CONSULT-END]."""
        if not results:
            return ""

        parts = ["[CONSULT-BEGIN]\n"]
        total = len(parts[0])

        for i, r in enumerate(results, 1):
            block = (
                f"[{i}] path: {r.path}\n"
                f"    title: {r.title}\n"
                f"    ---\n"
                f"{r.snippet}\n\n"
            )
            if total + len(block) > max_chars:
                remaining = max_chars - total
                if remaining > 80:
                    parts.append(block[:remaining].rstrip() + "\n[truncado]\n")
                break
            parts.append(block)
            total += len(block)

        parts.append("[/CONSULT-END]\n")
        return "".join(parts)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def list_categories(self) -> dict[str, int]:
        conn = self._connect()
        if conn is None:
            return {}
        try:
            rows = conn.execute(
                "SELECT category, COUNT(*) FROM docs "
                "WHERE category IS NOT NULL AND category != '' "
                "GROUP BY category ORDER BY COUNT(*) DESC"
            ).fetchall()
            return {str(c): int(n) for c, n in rows}
        except Exception:
            return {}
        finally:
            try: conn.close()
            except Exception: pass

    def stats(self) -> dict:
        if not self.is_available():
            return {"available": False, "db_path": str(self.db_path)}

        conn = self._connect()
        if conn is None:
            return {"available": False, "db_path": str(self.db_path)}

        try:
            total_docs = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
            total_fts  = conn.execute("SELECT COUNT(*) FROM docs_fts").fetchone()[0]
            size_mb    = round(self.db_path.stat().st_size / (1024 * 1024), 2)
            categories = self.list_categories()
            return {
                "available":  True,
                "db_path":    str(self.db_path),
                "size_mb":    size_mb,
                "total_docs": int(total_docs),
                "total_fts":  int(total_fts),
                "categories": categories,
            }
        except Exception:
            return {"available": False, "db_path": str(self.db_path)}
        finally:
            try: conn.close()
            except Exception: pass
