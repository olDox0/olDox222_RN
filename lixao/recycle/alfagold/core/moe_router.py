# alfagold/core/moe_router.py
import numpy as np
# [FIX] Import centralizado
from .math_utils import softmax

class MoERouter:
    """
    MoE Router (Gating Network).
    Responsável por distribuir a carga cognitiva entre os experts disponíveis.
    """
    def __init__(self, input_dim, num_experts):
        # Pesos da rede de roteamento (Gating Network)
        self.W_gate = np.random.randn(input_dim, num_experts) * 0.1
        
    def route(self, state_vector):
        """
        Calcula os pesos de ativação para cada expert.
        """
        logits = np.dot(state_vector, self.W_gate)
        weights = softmax(logits.reshape(1, -1)).flatten()
        return weights