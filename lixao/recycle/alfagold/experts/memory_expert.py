# alfagold/experts/memory_expert.py
import numpy as np
import os
# [DOX-UNUSED] import json
from typing import List, Optional

# [FIX] Persistência Segura
from ..core.persistence import save_model_state, load_model_state

MEMORY_BASE = os.path.expanduser("~/.doxoade/vector_db")

class MemoryExpert:
    """
    Expert de Memória (Hipocampo).
    Armazena vetores semânticos em formato binário otimizado (NPZ).
    """
    def __init__(self):
        self.vectors = np.empty((0, 0), dtype=np.float32) # Matriz vazia inicial
        self.payloads: List[str] = []
        self.load()

    def add(self, vector: np.ndarray, payload: str):
        """Adiciona uma memória ao banco."""
        # [MPoT-5] Validação de Contrato
        if not isinstance(vector, np.ndarray):
            raise ValueError("Vetor de memória deve ser um numpy array.")
            
        vector = vector.astype(np.float32)
        
        # Inicializa matriz se estiver vazia
        if self.vectors.shape[0] == 0:
            self.vectors = vector.reshape(1, -1)
        else:
            # Verifica dimensão
            if vector.shape[0] != self.vectors.shape[1]:
                # Se dimensão mudou (ex: modelo novo 64 vs 128), reseta
                print("   ♻️ [Memory] Dimensão mudou. Reiniciando hipocampo.")
                self.vectors = vector.reshape(1, -1)
                self.payloads = []
            else:
                self.vectors = np.vstack([self.vectors, vector])
                
        self.payloads.append(payload)
        self.save()

    def search(self, query_vector: np.ndarray, threshold: float = 0.85) -> Optional[str]:
        """Busca o vizinho mais próximo (Cosseno)."""
        if self.vectors.shape[0] == 0: return None

        # Similaridade de Cosseno: (A . B) / (|A| * |B|)
        # Assumindo que query_vector não é normalizado
        norm_q = np.linalg.norm(query_vector)
        if norm_q == 0: return None
        
        # Produto escalar em lote
        # (N_memories, D) dot (D,) -> (N_memories,)
        scores = np.dot(self.vectors, query_vector)
        
        # Normalização (Vetorizamos as normas do banco para velocidade)
        norms_db = np.linalg.norm(self.vectors, axis=1)
        scores /= (norms_db * norm_q + 1e-9)
        
        best_idx = np.argmax(scores)
        best_score = scores[best_idx]
        
        if best_score >= threshold:
            return self.payloads[best_idx]
            
        return None

    def save(self):
        """Salva vetores em NPZ e textos em JSON."""
        params = {'vectors': self.vectors}
        config = {'payloads': self.payloads}
        save_model_state(MEMORY_BASE, params, config)

    def load(self):
        """Carrega do disco."""
        try:
            # Tenta carregar formato seguro
            if os.path.exists(MEMORY_BASE + ".npz"):
                params, config = load_model_state(MEMORY_BASE)
                self.vectors = params['vectors']
                self.payloads = config.get('payloads', [])
                # print(f"   🧠 [Memory] {len(self.payloads)} memórias carregadas.")
                return
        except Exception:
            pass
            
        # Fallback legado (apagar se existir para limpar formato antigo)
        old_json = MEMORY_BASE + ".json"
        if os.path.exists(old_json) and not os.path.exists(MEMORY_BASE + ".npz"):
            # Se só existir o JSON (formato antigo textual), ignora e começa limpo
            # pois converter lista de lista de float é lento e inseguro
            pass