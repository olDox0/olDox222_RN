# ia_core/blackboard.py
import time
from typing import Dict, List, Any, Optional

class DoxoBoard:
    """
    Quadro Negro Cognitivo v1.0.
    Espaço de cruzamento sofisticado para o SiCDox (MPoT-3).
    """
    def __init__(self):
        # Memória de Curto Prazo (Snapshots de Contexto)
        self.hypotheses: Dict[str, Dict[str, Any]] = {}
        # Histórico de Meta-Ação (M2A2)
        self.causal_chain: List[str] = []

    def post_hypothesis(self, source: str, data: Any, confidence: float = 0.5):
        """Posta uma ideia no quadro para validação."""
        h_id = f"H-{int(time.time() * 1000)}"
        self.hypotheses[h_id] = {
            "source": source,
            "data": data,
            "confidence": confidence,
            "status": "PENDING"
        }
        return h_id

    def add_causal_link(self, node_a: str, node_b: str, relation: str):
        """Implementa o cruzamento A -> B solicitado pelo Arquiteto."""
        link = f"{node_a} --[{relation}]--> {node_b}"
        self.causal_chain.append(link)

    def get_summary(self) -> str:
        """Retorna a situação atual do pensamento da IA para o humano."""
        return "\n".join(self.causal_chain)