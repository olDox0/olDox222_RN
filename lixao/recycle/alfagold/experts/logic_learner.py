# alfagold/experts/logic_learner.py
import sqlite3
# [DOX-UNUSED] from ..core.blackboard import DoxoBoard

class RationalizerLearner:
    """Aprende novas 'Terceiras Vias' observando o Arquiteto Humano."""
    def __init__(self, db_path: str):
        self.db_path = db_path

    def aprender_com_rejeicao(self, conflito: dict, solucao_ia: str, correcao_humana: str):
        """
        Analisa a diferença entre o que a IA quis e o que o Humano fez.
        Cria um novo 'Template de Racionalização'.
        """
        # Extrai o padrão da correção (A -> B)
        # Salva no banco de dados para que o Synthesizer use na próxima vez
        pattern = self._abstrair_correcao(solucao_ia, correcao_humana)
        
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO solution_templates (problem_pattern, solution_template, confidence)
            VALUES (?, ?, 1)
        """, (conflito['description'], pattern))
        conn.commit()
        conn.close()

    def _abstrair_correcao(self, ia, humano):
        # Lógica de diff semântico (PASC-1.1)
        return f"REPLACE {ia} WITH {humano}"