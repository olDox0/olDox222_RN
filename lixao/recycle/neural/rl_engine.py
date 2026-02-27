"""
DOXOADE RL ENGINE (Q-Learning).
Gerencia uma tabela Q para aprender transições válidas entre tipos de tokens.
"""
import json
import os
# [DOX-UNUSED] import numpy as np

Q_PATH = os.path.expanduser("~/.doxoade/q_table.json")

class QLearner:
    def __init__(self, learning_rate=0.1, discount=0.9):
        self.lr = learning_rate
        self.gamma = discount
        # Tabela Q: Chave "TokenAnterior->TokenAtual" : Valor
        self.q_table = {}
        self.load()

    def get_q(self, prev_token, curr_token):
        """Retorna o valor Q da transição."""
        key = f"{prev_token}->{curr_token}"
        return self.q_table.get(key, 0.0)

    def update(self, prev_token, curr_token, reward):
        """Atualiza a tabela Q baseado na recompensa (Bellman Equation simplificada)."""
        key = f"{prev_token}->{curr_token}"
        current_q = self.q_table.get(key, 0.0)
        
        # Como é um processo passo-a-passo sem estados futuros complexos na geração de texto,
        # simplificamos para: Q(s,a) = Q(s,a) + alpha * (Reward - Q(s,a))
        new_q = current_q + self.lr * (reward - current_q)
        
        self.q_table[key] = new_q
        
    def save(self):
        with open(Q_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.q_table, f, indent=2)

    def load(self):
        if os.path.exists(Q_PATH):
            try:
                with open(Q_PATH, 'r', encoding='utf-8') as f:
                    self.q_table = json.load(f)
            except Exception: pass
            
    def get_boost(self, prev_token, candidate_token):
        """Retorna um boost para os logits baseado no Q-Value."""
        q = self.get_q(prev_token, candidate_token)
        # Normaliza o boost: Q positivo ajuda muito, Q negativo pune muito
        return q * 5.0 # Fator de amplificação