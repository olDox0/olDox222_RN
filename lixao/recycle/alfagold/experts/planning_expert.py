# alfagold/experts/planning_expert.py
import numpy as np
import os
# [DOX-UNUSED] from typing import Any

from ..core.state_packet import StatePacket
from ..core.math_utils import softmax
# [FIX] Persistência Segura
from ..core.persistence import save_model_state, load_model_state

class PlanningExpert:
    """
    Expert de Planejamento (Lobo Frontal).
    Decide a 'Intenção' (Option) baseada no estado atual e aplica viés no vocabulário.
    Implementa persistência segura (Aegis) e contratos explícitos (MPoT-5).
    """
    def __init__(self, d_model: int = 64, vocab_size: int = 2000, num_options: int = 3):
        self.d_model = d_model
        self.num_options = num_options
        self.vocab_size = vocab_size
        self.state_dim = 6 # INICIO, NOME, ARGS_PRE, ARGS, TRANSICAO, CORPO
        
        # Inicialização de Pesos
        self.W_ctx = np.random.randn(d_model, 32).astype(np.float32) * 0.05
        self.W_state = np.random.randn(self.state_dim, 32).astype(np.float32) * 0.5 
        self.W_final = np.random.randn(32, num_options).astype(np.float32) * 0.1
        self.option_bias = np.zeros((num_options, vocab_size), dtype=np.float32)
        
        # Memória de Treino (Transiente)
        self.cache = {}
        self.episode_buffer = []
        self.current_option = 0
        
        self.path_base = os.path.expanduser("~/.doxoade/moe_planner_v1")
        self.load()

    def process(self, packet: StatePacket, training: bool = False) -> StatePacket:
        """Processa o pacote de estado e injeta viés de intenção."""
        # [MPoT-5] Contrato de Entrada
        if packet is None:
            raise ValueError("PlanningExpert recebeu pacote nulo.")

        # 1. Recupera Inputs
        ctx_vector = packet.embedding_vector
        if ctx_vector is None: 
            ctx_vector = np.zeros(self.d_model, dtype=np.float32)
            
        mapa = {"INICIO":0, "NOME":1, "ARGS_PRE":2, "ARGS":3, "TRANSICAO":4, "CORPO":5}
        state_idx = mapa.get(packet.syntax_state, 0)
        state_vec = np.zeros(self.state_dim, dtype=np.float32)
        state_vec[min(state_idx, 5)] = 1.0
        
        # 2. Forward
        h_ctx = np.dot(ctx_vector, self.W_ctx)
        h_state = np.dot(state_vec, self.W_state)
        h_comb = np.maximum(0, h_ctx + h_state)
        
        logits = np.dot(h_comb, self.W_final)
        probs = softmax(logits.reshape(1, -1)).flatten()
        
        # 3. Decisão
        if training and np.random.rand() < 0.2:
            self.current_option = np.random.randint(self.num_options)
        else:
            self.current_option = int(np.argmax(probs))
            
        packet.current_goal = f"OPTION_{self.current_option}"
        
        # Cache
        self.cache['ctx'] = ctx_vector
        self.cache['state'] = state_vec
        self.cache['h'] = h_comb
        self.cache['probs'] = probs
        self.cache['action'] = self.current_option
        
        # 4. Injeção de Viés
        bias_vector = self.option_bias[self.current_option]
        if packet.logits is not None:
            # Resize seguro se o vocabulário mudou
            if len(bias_vector) != len(packet.logits):
                new_b = np.zeros(len(packet.logits), dtype=np.float32)
                m = min(len(bias_vector), len(packet.logits))
                new_b[:m] = bias_vector[:m]
                bias_vector = new_b
            packet.logits += bias_vector
            
        return packet

    def register_feedback(self, token_id: int, reward: float):
        """Registra feedback para RL."""
        if 'ctx' in self.cache:
            self.episode_buffer.append({
                'ctx': self.cache['ctx'],
                'state': self.cache['state'],
                'h': self.cache['h'],
                'probs': self.cache['probs'],
                'action': self.cache['action'],
                'reward': reward
            })
            
        if token_id < self.vocab_size:
            lr = 0.05
            delta = np.clip(lr * reward, -0.5, 0.5)
            self.option_bias[self.current_option, token_id] += delta
            # Clip in-place
            np.clip(self.option_bias[self.current_option, token_id], -5.0, 5.0, out=self.option_bias[self.current_option, token_id:token_id+1])

    def train_episode(self, lr: float = 0.01) -> float:
        """Aplica REINFORCE."""
        if not self.episode_buffer: return 0.0
        
        total_reward = sum(step['reward'] for step in self.episode_buffer)
        baseline = total_reward / len(self.episode_buffer)
        loss_sum = 0.0
        
        for step in self.episode_buffer:
            adv = np.clip(step['reward'] - baseline, -2.0, 2.0)
            
            d_logits = step['probs'].copy()
            d_logits[step['action']] -= 1
            d_logits *= -adv
            
            d_W_final = np.outer(step['h'], d_logits)
            
            d_h = np.dot(self.W_final, d_logits)
            d_h[step['h'] <= 0] = 0
            
            d_W_ctx = np.outer(step['ctx'], d_h)
            d_W_state = np.outer(step['state'], d_h)
            
            self.W_final -= lr * d_W_final
            self.W_ctx -= lr * d_W_ctx
            self.W_state -= lr * d_W_state
            
            loss_sum += np.mean(d_logits**2)
            
        self.episode_buffer = []
        return float(loss_sum)

    def save(self):
        """Salva usando JSON+NPZ."""
        params = {
            'W_ctx': self.W_ctx,
            'W_state': self.W_state,
            'W_final': self.W_final,
            'option_bias': self.option_bias
        }
        config = {
            'd_model': self.d_model,
            'num_options': self.num_options,
            'vocab_size': self.vocab_size
        }
        save_model_state(self.path_base, params, config)
            
    def load(self):
        """Carrega usando JSON+NPZ."""
        # Tenta carregar o novo formato primeiro
        try:
            if os.path.exists(self.path_base + ".npz"):
                params, config = load_model_state(self.path_base)
                self.W_ctx = params['W_ctx']
                self.W_state = params['W_state']
                self.W_final = params['W_final']
                self.option_bias = params['option_bias']
                # Atualiza config se necessário
                print("   🧠 [Planner] Córtex Frontal (Aegis) carregado.")
                return
        except Exception as e:
            print(f"   [Planner] Erro ao carregar Aegis: {e}. Iniciando limpo.")

        # Fallback para migração de Pickle antigo
        old_pickle = self.path_base + ".pkl"
        if os.path.exists(old_pickle):
            print("   ⚠️ [Planner] Migrando memória legada (.pkl)...")
            try:
                import pickle
                with open(old_pickle, 'rb') as f:
                    data = pickle.load(f)
                    # Migração manual de chaves
                    if 'W_ctx' in data: self.W_ctx = data['W_ctx']
                    if 'W_state' in data: self.W_state = data['W_state']
                    if 'W_final' in data: self.W_final = data['W_final']
                    if 'option_bias' in data: self.option_bias = data['option_bias']
                # Salva no novo formato
                self.save()
            except Exception as e:
                print(f"   [Planner] Falha na migração: {e}")