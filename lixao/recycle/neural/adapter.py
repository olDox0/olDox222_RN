# -*- coding: utf-8 -*-
"""
Motor de Internalização Relacional (MIR) v1.0.
Converte logs, incidentes e código real em triplas lógicas (A -> B).
Em conformidade com PASC v1.1 e MPoT v75.
"""

# [DOX-UNUSED] import numpy as np
import logging
import os
from ..database import get_db_connection

class ConceptAdapter:
    """
    Responsável por traduzir a base de dados Sapiens para a Memória Relacional.
    Implementa o M2A2 (Memória de Meta-Ação e Atividade).
    """
    def __init__(self, project_root: str):
        self.root = project_root
        # Regra 5.1: Validação de Contrato
        if not os.path.exists(project_root):
            raise ValueError(f"Caminho do projeto inválido: {project_root}")

    def internalizar_incidencias(self, limit: int = 100):
        """
        Lê a tabela 'solutions' e 'open_incidents' para criar pares de Causalidade.
        Raciocínio Indutivo: 'Este tipo de erro costuma ser resolvido assim'.
        """
        # Regra 6.2: Lazy Import para preservar RAM
# [DOX-UNUSED]         import sqlite3
        
        causalidade = []
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Busca relação Problema -> Solução (O coração do M2A2)
            query = """
                SELECT s.finding_hash, s.stable_content, i.message, i.category
                FROM solutions s
                JOIN open_incidents i ON s.finding_hash = i.finding_hash
                LIMIT ?
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            
            for row in rows:
                # Criamos a tripla: (Erro) --[RESOLVIDO_POR]--> (Código_Estável)
                tripla = {
                    "source": row[2],  # Mensagem de Erro (A)
                    "relation": "SOLVED_BY",
                    "target": row[1],  # Código Corrigido (B)
                    "meta": row[3]     # Categoria (X)
                }
                causalidade.append(tripla)
            
            conn.close()
        except Exception as e:
            logging.error(f"[SiCDox-Adapter] Falha na internalização: {e}")
            
        return causalidade

    def racionalizar_para_blackboard(self, tripla: dict):
        """
        Prepara os dados para o DoxoBoard, filtrando incertezas.
        Se a relação for fraca, prepara flag para consulta humana.
        """
        confianca = 1.0
        # Lógica de racionalização baseada em MPoT
        if "eval" in tripla["target"] or "exec" in tripla["target"]:
            confianca -= 0.5 # Risco Aegis detectado
            
        internalizado = {
            "token_relacional": f"{tripla['source']} -> {tripla['meta']}",
            "payload": tripla["target"],
            "confianca": confianca,
            "precisa_validacao": confianca < 0.8
        }
        return internalizado

    def get_reasoning_batch(self, size: int = 32):
        """
        Gera tensores para o Córtex baseados na realidade do código.
        Raciocínio Dedutivo: 'Dada esta estrutura, este é o contrato'.
        """
        # Placeholder para o novo Tokenizer de Conceitos que faremos
        data = self.internalizar_incidencias(limit=size)
        return [self.racionalizar_para_blackboard(d) for d in data]