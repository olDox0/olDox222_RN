# -*- coding: utf-8 -*-
# ia_core/blackboard.py

"""
ORN — Blackboard (Hades)
Memória de hipóteses e causalidade da sessão atual.

OSL-6: Escopo mínimo — dados de sessão não vazam para módulos externos.
OSL-12: get_summary() retorna estado serializável para telemetria/debug.
God: Hades — invisível, persistente, guarda o que foi pensado.

TODO Fase 3: implementar post_hypothesis, add_causal_link.
"""

# [DOX-UNUSED] import time
from typing import Any
#from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Hypothesis:
    """Uma hipótese registrada no blackboard."""
    source:     str          # módulo que gerou a hipótese
    content:    str          # texto da hipótese
    confidence: float = 1.0  # 0.0–1.0

class DoxoBoard:
    """Quadro de hipóteses e links causais da sessão.

    OSL-3: Sem alocação dinâmica externa — usa listas Python simples.
    """

    def __init__(self) -> None:
        self._hypotheses: list[Hypothesis]         = []
        self._causal_links: list[tuple[str, str]]  = []

    def post_hypothesis(self, source: str, content: str,
                        confidence: float = 1.0) -> None:
        """Registra uma nova hipótese.

        OSL-5.2: valida source e content.
        """
        if not source or not content:
            raise ValueError("source e content são obrigatórios.")
        self._hypotheses.append(Hypothesis(source, content, confidence))

    def add_causal_link(self, causa: str, efeito: str) -> None:
        """Registra um link causal entre dois conceitos."""
        if not causa or not efeito:
            raise ValueError("causa e efeito são obrigatórios.")
        self._causal_links.append((causa, efeito))

    def get_summary(self) -> dict[str, Any]:
        """Retorna estado atual serializável.

        OSL-6: Não expõe referências internas — retorna cópia.
        """
        return {
            "hypotheses":   [{"source": h.source, "content": h.content,
                               "confidence": h.confidence}
                             for h in self._hypotheses],
            "causal_links": list(self._causal_links),
        }

    def clear(self) -> None:
        """Limpa o blackboard (usado por `orn brain --clear`)."""
        self._hypotheses.clear()
        self._causal_links.clear()