# alfagold/experts/generator_expert.py
# [DOX-UNUSED] import numpy as np # [DOX-UNUSED] Mantido para expansão
import os
from ..core.transformer import Alfagold
from ..core.state_packet import StatePacket

class GeneratorExpert:
    """
    Expert responsável pela geração de tokens (Wernicke/Broca).
    Usa o Transformer do Core.
    """
    def __init__(self, model_path=None):
        self.model = Alfagold()
        path = model_path or os.path.expanduser("~/.doxoade/alfagold_v1.pkl")
        
        if os.path.exists(path):
            try:
                self.model.load(path)
                print("   [Generator] Pesos carregados.")
            except Exception as e:
                print(f"   [Generator] Erro ao carregar ({e}). Iniciando com pesos aleatórios.")

    def process(self, packet: StatePacket) -> StatePacket:
        """
        Recebe o estado cognitivo, roda o Forward Pass e anexa os Logits.
        """
        # Se não houver tokens, usa o input de texto para iniciar
        if not packet.token_ids and packet.input_text:
            packet.token_ids = self.model.tokenizer.encode(packet.input_text)
        
        # Forward no Transformer
        # [FIX] Desempacota 3 valores (Token Head, Phase Head, Cache)
        logits_token, _, cache = self.model.forward(packet.token_ids)
        
        # Pega a previsão do próximo token (último passo)
        next_token_logits = logits_token[-1]
        
        # Anexa ao pacote de estado
        packet.logits = next_token_logits
        
        # Opcional: Atualiza o embedding do estado atual no pacote
        if 'x_final' in cache:
            packet.embedding_vector = cache['x_final'][-1]
            
        return packet

    def decode(self, token_id: int) -> str:
        """Decodifica um ID de token para string."""
        return self.model.tokenizer.decode([token_id])