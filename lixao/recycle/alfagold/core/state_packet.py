# alfagold/core/state_packet.py
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class StatePacket:
    """
    O Neurotransmissor Digital.
    Carrega todo o contexto cognitivo de um passo de tempo.
    """
    # 1. Entrada Bruta
    input_text: str = ""
    token_ids: List[int] = field(default_factory=list)
    
    # 2. Estado Neural (Latente)
    embedding_vector: Optional[np.ndarray] = None # (D_model,)
    
    # 3. Estado Simbólico (Broca/Arquiteto) -> [FIX: Reintroduzido]
    syntax_state: str = "INICIO" # NOME, ARGS, CORPO
    
    # 4. Estado Executivo (HRL/Planner) -> [FIX: Reintroduzido]
    current_goal: str = "GENERIC" 
    
    # 5. Sinais dos Experts
    logits: Optional[np.ndarray] = None           # Sinal Excitátorio (Generator)
    inhibition_mask: Optional[np.ndarray] = None  # Sinal Inibitório (Syntax)
    
    # 6. Saída Final
    generated_token: str = ""
    
    def clone(self):
        from copy import deepcopy
        return deepcopy(self)