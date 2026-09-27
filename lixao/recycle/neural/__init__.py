"""
Pacote Neural do Doxoade (Ouroboros).
Expõe as classes principais do core, adaptador e lógica.
"""
from .core import LSTM, Tokenizer, CamadaEmbedding, softmax, load_json, save_json
from .adapter import BrainLoader
from .logic import ArquitetoLogico
from .reasoning import Sherlock
from .critic import Critic
from .memory import VectorDB
from .rl_engine import QLearner

# Define explicitamente o que é exportado para silenciar avisos de 'unused'
__all__ = [
    'LSTM', 'Tokenizer', 'CamadaEmbedding', 'softmax', 'load_json', 'save_json',
    'BrainLoader',
    'ArquitetoLogico',
    'Sherlock',
    'Critic',
    'VectorDB',
    'QLearner'
]