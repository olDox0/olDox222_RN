# -*- coding: utf-8 -*-
"""Sessão de lousa (blackboard) para hipóteses e relações causais."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Hypothesis:
    source: str
    content: str
    confidence: float = 1.0


class DoxoBoard:
    """Blackboard simples com persistência local para melhorar respostas."""

    def __init__(self, store_path: Path | None = None, max_items: int = 64) -> None:
        self._store_path = store_path or Path("telemetry") / "blackboard_session.json"
        self._max_items = max(8, int(max_items))
        self._hypotheses: list[Hypothesis] = []
        self._causal_links: list[tuple[str, str]] = []
        self._load()

    def post_hypothesis(self, source: str, content: str, confidence: float = 1.0) -> None:
        if not source or not content:
            raise ValueError("source e content são obrigatórios.")
        clamped = max(0.0, min(1.0, float(confidence)))
        self._hypotheses.append(Hypothesis(source.strip(), content.strip(), clamped))
        self._trim()
        self._save()

    def add_causal_link(self, causa: str, efeito: str) -> None:
        if not causa or not efeito:
            raise ValueError("causa e efeito são obrigatórios.")
        self._causal_links.append((causa.strip(), efeito.strip()))
        if len(self._causal_links) > self._max_items:
            self._causal_links = self._causal_links[-self._max_items :]
        self._save()

    def get_summary(self) -> dict[str, Any]:
        return {
            "hypotheses": [
                {"source": h.source, "content": h.content, "confidence": h.confidence}
                for h in self._hypotheses
            ],
            "causal_links": list(self._causal_links),
            "items": len(self._hypotheses),
        }

    def build_context_block(self, query: str, limit: int = 4) -> str:
        """Monta bloco curto para injetar no prompt da IA."""
        if not self._hypotheses:
            return ""
        q = " ".join(query.lower().split())
        scored: list[tuple[float, Hypothesis]] = []
        for h in self._hypotheses:
            overlap = 0.25 if any(tok in h.content.lower() for tok in q.split()[:6]) else 0.0
            scored.append((h.confidence + overlap, h))
        best = [h for _, h in sorted(scored, key=lambda it: it[0], reverse=True)[: max(1, limit)]]
        bullets = "\n".join(f"- ({h.source}) {h.content[:120]}" for h in best)
        return f"[BLACKBOARD]\nMemórias relevantes:\n{bullets}\n[/BLACKBOARD]\n"

    def clear(self) -> None:
        self._hypotheses.clear()
        self._causal_links.clear()
        self._save()

    def _trim(self) -> None:
        if len(self._hypotheses) > self._max_items:
            self._hypotheses = self._hypotheses[-self._max_items :]

    def _load(self) -> None:
        try:
            if not self._store_path.exists():
                return
            payload = json.loads(self._store_path.read_text(encoding="utf-8"))
            self._hypotheses = [
                Hypothesis(str(h.get("source", "?")), str(h.get("content", "")), float(h.get("confidence", 1.0)))
                for h in payload.get("hypotheses", [])
                if h.get("content")
            ]
            self._causal_links = [tuple(x) for x in payload.get("causal_links", []) if isinstance(x, list) and len(x) == 2]
            self._trim()
        except Exception:
            self._hypotheses = []
            self._causal_links = []

    def _save(self) -> None:
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            self._store_path.write_text(json.dumps(self.get_summary(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
