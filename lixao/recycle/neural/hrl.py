# doxoade/neural/hrl.py
import numpy as np
import os
import sys

# [FIX] Garante acesso à raiz para importar alfagold
current_dir = os.path.dirname(os.path.abspath(__file__)) # .../doxoade/neural
project_root = os.path.dirname(os.path.dirname(current_dir)) # .../
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Agora o import funciona
from alfagold.core.persistence import save_model_state, load_model_state
from .core import softmax

class HRLManager:
    """
    HRL Manager v5.0 (Stabilized & Entropic).
    - Normalização Global de Estado.
    - Regularização por Entropia (Evita colapso de modo).
    - Inércia Temporal (Recebe a opção anterior como input).
    """
    def __init__(self, input_dim=64, vocab_size=2000, num_options=3):
        self.input_dim = input_dim
        self.num_options = num_options
        self.vocab_size = vocab_size
        
        # State Dim: Embedding(64) + Simbólico(6) + LastOption(3)
        self.state_dim = 6 
        self.total_input_dim = input_dim + self.state_dim + num_options
        
        # Pesos (Xavier Initialization)
        scale = np.sqrt(2.0 / self.total_input_dim)
        self.W1 = np.random.randn(self.total_input_dim, 64).astype(np.float32) * scale
        self.W2 = np.random.randn(64, num_options).astype(np.float32) * 0.1
        
        # Bias de Opção (Matrix de Influência)
        self.option_embeddings = np.zeros((num_options, vocab_size), dtype=np.float32)
        
        self.cache = {}
        self.episode_buffer = [] 
        self.current_option = 0
        self.last_option = 0 # Memória de curto prazo (Inércia)

    def _normalize(self, x):
        """LayerNorm manual para o vetor de entrada."""
        mean = np.mean(x)
        std = np.std(x) + 1e-8
        return (x - mean) / std

    def forward(self, full_input):
        # Normalização Global (Resolve o problema de escala 2.0 vs 0.05)
        norm_input = self._normalize(full_input)
        
        h = np.maximum(0, np.dot(norm_input, self.W1))
        logits = np.dot(h, self.W2)
        
        # Clip logits
        logits = np.clip(logits, -20, 20)
        probs = softmax(logits.reshape(1, -1)).flatten()
        
        self.cache['input'] = norm_input # Guarda o normalizado para o backprop
        self.cache['h'] = h
        self.cache['probs'] = probs
        
        return probs

    def select_option(self, token_vector, state_idx, epsilon=0.1):
        # 1. Monta o vetor de estado completo
        # Parte A: Estado Simbólico (One-Hot)
        state_vec = np.zeros(self.state_dim, dtype=np.float32)
        idx = min(state_idx, self.state_dim - 1)
        state_vec[idx] = 1.0
        
        # Parte B: Opção Anterior (One-Hot) - Dá noção de continuidade
        prev_opt_vec = np.zeros(self.num_options, dtype=np.float32)
        prev_opt_vec[self.last_option] = 1.0
        
        # Concatena tudo
        full_input = np.concatenate((token_vector, state_vec, prev_opt_vec))
        
        probs = self.forward(full_input)
        
        if np.random.rand() < epsilon:
            option = np.random.randint(self.num_options)
        else:
            option = np.argmax(probs)
            
        # Atualiza memória
        self.last_option = self.current_option
        self.current_option = option
        
        self.cache['last_action'] = option
        return option

    def register_step(self, reward):
        if 'input' in self.cache:
            self.episode_buffer.append({
                'input': self.cache['input'],
                'h': self.cache['h'],
                'probs': self.cache['probs'],
                'action': self.cache['last_action'],
                'reward': reward
            })

    def train_episode(self, lr=0.01, entropy_beta=0.05):
        """
        Policy Gradient com Bônus de Entropia.
        """
        if not self.episode_buffer: return 0
        
        total_reward = sum(step['reward'] for step in self.episode_buffer)
        baseline = total_reward / len(self.episode_buffer)
        
        loss_sum = 0
        
        for step in self.episode_buffer:
            advantage = step['reward'] - baseline
            advantage = np.clip(advantage, -2.0, 2.0)
            
            probs = step['probs']
            action = step['action']
            
            # Entropia: -sum(p * log(p))
            # Queremos maximizar a entropia, então o gradiente é na direção de uniformizar as probs
            # Gradiente da entropia em relação aos logits é complexo, simplificação:
            # penaliza certeza excessiva
            
            # Gradiente do Objetivo Principal (J = log_prob * A)
            d_logits = probs.copy()
            d_logits[action] -= 1
            d_logits *= -advantage
            
            # Gradiente da Entropia (Regularização)
            # H = -p log p
            # dH/dlogits = p * (log p + 1) - p * sum(...) -> Aproximação: atrai para 0
            # Adicionamos um termo que empurra probs para distribuição uniforme
            d_entropy = probs * (np.log(probs + 1e-9) + 1)
            
            # Soma os gradientes: Queremos minimizar Loss (Maximizar Reward + Entropia)
            # dLoss = d_Policy - beta * d_Entropy
            total_grad = d_logits - (entropy_beta * d_entropy)
            
            # Backprop
            d_W2 = np.outer(step['h'], total_grad)
            d_h = np.dot(self.W2, total_grad)
            d_h[step['h'] <= 0] = 0
            d_W1 = np.outer(step['input'], d_h)
            
            # Update com Clipping
            self.W1 -= np.clip(lr * d_W1, -0.1, 0.1)
            self.W2 -= np.clip(lr * d_W2, -0.1, 0.1)
            
            # Cálculo real da Loss (Policy Loss - Entropy Bonus)
            log_prob = np.log(probs[action] + 1e-9)
            entropy = -np.sum(probs * np.log(probs + 1e-9))
            policy_loss = -log_prob * advantage
            loss_sum += (policy_loss - entropy_beta * entropy)

        self.episode_buffer = []
        return loss_sum

    def update_option_bias(self, option_idx, token_id, reward, lr=0.05):
        if token_id >= self.vocab_size: return
        delta = np.clip(lr * reward, -0.5, 0.5)
        # Decay (Esquecimento leve) para evitar saturação
        self.option_embeddings[option_idx, token_id] *= 0.999 
        self.option_embeddings[option_idx, token_id] += delta
        self.option_embeddings[option_idx, token_id] = np.clip(
            self.option_embeddings[option_idx, token_id], -5.0, 5.0
        )

class HRLAgent:
    def __init__(self, worker_model):
        self.worker = worker_model
        if hasattr(worker_model, 'params') and 'w_token' in worker_model.params:
            vocab_size = worker_model.params['w_token'].shape[0]
            d_model = worker_model.d_model
        else:
            vocab_size = len(worker_model.tokenizer.vocab)
            d_model = 64
            
        self.manager = HRLManager(input_dim=d_model, vocab_size=vocab_size)
        self.path_base = os.path.expanduser("~/.doxoade/hrl_manager_v5") # V5
        self.load()

    def step(self, context_ids, symbolic_state="INICIO", training=False):
        mapa = {"INICIO":0, "NOME":1, "ARGS_PRE":2, "ARGS":3, "TRANSICAO":4, "CORPO":5}
        state_idx = mapa.get(symbolic_state, 0)

        window = 5
        if len(context_ids) > 0:
            ids_to_embed = context_ids[-window:]
            if hasattr(self.worker, 'params'):
                vecs = self.worker.params['w_token'][ids_to_embed]
            else:
                vecs = self.worker.token_embedding[ids_to_embed]
            token_vector = np.mean(vecs, axis=0)
        else:
            token_vector = np.zeros(self.manager.input_dim)

        eps = 0.3 if training else 0.0
        option_idx = self.manager.select_option(token_vector, state_idx, epsilon=eps)
        
        logits, _ = self.worker.forward(context_ids)
        bias = self.manager.option_embeddings[option_idx]
        
        # Safety resize
        if len(bias) != len(logits[-1]):
             new_bias = np.zeros(len(logits[-1]))
             m = min(len(bias), len(logits[-1]))
             new_bias[:m] = bias[:m]
             bias = new_bias
             
        return logits[-1] + bias, option_idx

    def register_feedback(self, token_id, reward):
        self.manager.register_step(reward)
        self.manager.update_option_bias(self.manager.current_option, token_id, reward)

    def end_episode(self):
        return self.manager.train_episode()

    def save(self):
        params = {
            'W1': self.manager.W1,
            'W2': self.manager.W2,
            'option_embeddings': self.manager.option_embeddings
        }
        config = {
            'input_dim': self.manager.input_dim,
            'num_options': self.manager.num_options,
            'vocab_size': self.manager.vocab_size,
            'state_dim': self.manager.state_dim
        }
        save_model_state(self.path_base, params, config)
            
    def load(self):
        # Tenta carregar V5
        try:
            if os.path.exists(self.path_base + ".npz"):
                params, config = load_model_state(self.path_base)
                # Verifica compatibilidade dimensional
                if params['W1'].shape == self.manager.W1.shape:
                    self.manager.W1 = params['W1']
                    self.manager.W2 = params['W2']
                    self.manager.option_embeddings = params['option_embeddings']
                    print("   🧠 HRL Manager v5 (Entropy+Norm) carregado.")
                else:
                    print("⚠️ [HRL] Dimensões mudaram. Reiniciando.")
        except Exception as e:
            import sys, os
            _, exc_obj, exc_tb = sys.exc_info()
            f_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            line_n = exc_tb.tb_lineno
            print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: load\033[0m")
            print(f"\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033[0m")
