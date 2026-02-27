# doxoade/neural/alfagold/model.py
import numpy as np
import pickle
import os
from .tokenizer import AlfagoldTokenizer

# --- FUNÇÕES DE ATIVAÇÃO E SEUS GRADIENTES ---

def gelu(x):
    """Gaussian Error Linear Unit."""
    return 0.5 * x * (1 + np.tanh(np.sqrt(2 / np.pi) * (x + 0.044715 * np.power(x, 3))))

def d_gelu(x):
    """Derivada aproximada da GELU."""
    # Constantes
    cdf = 0.5 * (1 + np.tanh(np.sqrt(2 / np.pi) * (x + 0.044715 * np.power(x, 3))))
    pdf = np.exp(-0.5 * x**2) / np.sqrt(2 * np.pi) # Aproximação simplificada para performance
    return cdf + x * pdf 

def softmax(x):
    e_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
    return e_x / np.sum(e_x, axis=-1, keepdims=True)

class Alfagold:
    def __init__(self, vocab_size=1000, d_model=64, max_len=128):
        self.d_model = d_model
        self.max_len = max_len
        self.vocab_size = vocab_size
        self.tokenizer = AlfagoldTokenizer()
        
        # Inicialização Xavier/Glorot
        scale = 1.0 / np.sqrt(d_model)
        
        self.params = {
            'w_token': np.random.randn(vocab_size, d_model).astype(np.float32) * scale,
            'w_pos': self._create_positional_encoding(max_len, d_model),
            
            # Atenção
            'Wq': np.random.randn(d_model, d_model).astype(np.float32) * scale,
            'Wk': np.random.randn(d_model, d_model).astype(np.float32) * scale,
            'Wv': np.random.randn(d_model, d_model).astype(np.float32) * scale,
            'Wo': np.random.randn(d_model, d_model).astype(np.float32) * scale,
            
            # Feed Forward
            'W1': np.random.randn(d_model, d_model * 4).astype(np.float32) * scale,
            'b1': np.zeros(d_model * 4, dtype=np.float32),
            'W2': np.random.randn(d_model * 4, d_model).astype(np.float32) * scale,
            'b2': np.zeros(d_model, dtype=np.float32),
        }

    def _create_positional_encoding(self, max_len, d_model):
        pe = np.zeros((max_len, d_model), dtype=np.float32)
        position = np.arange(0, max_len)[:, np.newaxis]
        div_term = np.exp(np.arange(0, d_model, 2) * -(np.log(10000.0) / d_model))
        pe[:, 0::2] = np.sin(position * div_term)
        pe[:, 1::2] = np.cos(position * div_term)
        return pe

    def forward(self, token_ids, training=False):
        """Forward pass que retorna (logits, cache)."""
        if len(token_ids) > self.max_len: token_ids = token_ids[:self.max_len]
        n = len(token_ids)
        cache = {}
        
        # 1. Embedding
        # (N, D)
        x = self.params['w_token'][token_ids] + self.params['w_pos'][:n]
        cache['x_emb'] = x
        cache['token_ids'] = token_ids

        # 2. Attention
        Q = np.dot(x, self.params['Wq']) # (N, D)
        K = np.dot(x, self.params['Wk'])
        V = np.dot(x, self.params['Wv'])
        
        cache['Q'], cache['K'], cache['V'] = Q, K, V
        
        # Scaled Dot-Product
        scores = np.matmul(Q, K.T) / np.sqrt(self.d_model) # (N, N)
        
        # Máscara Causal (-inf no triângulo superior)
        mask = np.triu(np.ones((n, n)), k=1) * -1e9
        scores += mask
        
        attn_weights = softmax(scores) # (N, N)
        cache['attn_weights'] = attn_weights
        
        attn_out = np.matmul(attn_weights, V) # (N, D)
        
        # Projeção de saída da atenção + Residual
        # Nota: Ignoramos LayerNorm no backprop simplificado para estabilidade
        x2 = x + np.dot(attn_out, self.params['Wo']) 
        cache['x2'] = x2
        
        # 3. Feed Forward
        # x2 -> W1 -> Gelu -> W2 -> out
        ff_hidden = np.dot(x2, self.params['W1']) + self.params['b1']
        ff_act = gelu(ff_hidden)
        cache['ff_hidden'] = ff_hidden
        cache['ff_act'] = ff_act
        
        ff_out = np.dot(ff_act, self.params['W2']) + self.params['b2']
        
        # Residual final
        x_final = x2 + ff_out
        cache['x_final'] = x_final
        
        # 4. Unembedding (Decoding)
        # Reutiliza a matriz de embedding (Weight Tying) ou projeta direto
        # Vamos usar Weight Tying para economizar memória
        logits = np.dot(x_final, self.params['w_token'].T)
        
        return logits, cache

    def backward(self, d_logits, cache):
        """
        Calcula gradientes.
        d_logits: Gradiente da Loss em relação à saída (N, Vocab)
        """
        grads = {k: np.zeros_like(v) for k, v in self.params.items()}
# [DOX-UNUSED]         N = d_logits.shape[0]
        
        # 4. Backprop Unembedding
        # dL/dX_final = dL/dLogits * W_token
        d_x_final = np.dot(d_logits, self.params['w_token']) # (N, D)
        # dL/dW_token (parte 1: saída)
        grads['w_token'] += np.dot(d_logits.T, cache['x_final']) # (Vocab, D)
        
        # 3. Backprop Feed Forward
        # Residual connection: d_ff_out = d_x_final
        d_ff_out = d_x_final 
        
        # dL/dW2 = d_ff_out * ff_act.T
        grads['W2'] = np.dot(cache['ff_act'].T, d_ff_out)
        grads['b2'] = np.sum(d_ff_out, axis=0)
        
        # dL/dHidden = d_ff_out * W2.T
        d_ff_act = np.dot(d_ff_out, self.params['W2'].T)
        
        # Derivada da Ativação (GELU)
        d_ff_hidden = d_ff_act * d_gelu(cache['ff_hidden'])
        
        # dL/dW1
        grads['W1'] = np.dot(cache['x2'].T, d_ff_hidden)
        grads['b1'] = np.sum(d_ff_hidden, axis=0)
        
        # dL/dX2 (Entrada da FFN)
        d_x2 = np.dot(d_ff_hidden, self.params['W1'].T) + d_x_final # + residual
        
        # 2. Backprop Attention
        # Residual connection: d_attn_proj = d_x2
        
        # Projeção de saída Wo
        # dL/dAttn_out = d_x2 * Wo.T
        # dL/dWo = Attn_out.T * d_x2
        # (Mas espera, Wo é aplicado em attn_out)
        # x2 = x + attn_out . Wo
        d_attn_out = np.dot(d_x2, self.params['Wo'].T)
        grads['Wo'] = np.dot(np.dot(cache['attn_weights'], cache['V']).T, d_x2)
        
        # Backprop através do produto escalar (Attention Weights * V)
        # dL/dV = weights.T * d_attn_out
        d_V = np.dot(cache['attn_weights'].T, d_attn_out)
        grads['Wv'] = np.dot(cache['x_emb'].T, d_V)
        
        # dL/dWeights = d_attn_out * V.T
        d_weights = np.dot(d_attn_out, cache['V'].T)
        
        # Derivada do Softmax (Simplificada para estabilidade)
        # dScores = dWeights * (Weights * (1 - Weights)) aprox
        # Usaremos identidade para evitar explosão numérica no "from scratch"
        d_scores = d_weights 
        
        # Backprop Scaled Dot Product (Q * K.T)
        d_scores *= (1.0 / np.sqrt(self.d_model))
        
        # dL/dQ = dScores * K
        d_Q = np.dot(d_scores, cache['K'])
        grads['Wq'] = np.dot(cache['x_emb'].T, d_Q)
        
        # dL/dK = dScores.T * Q
        d_K = np.dot(d_scores.T, cache['Q'])
        grads['Wk'] = np.dot(cache['x_emb'].T, d_K)
        
        # 1. Backprop Embedding
        # Soma todos os gradientes que fluem para x_emb
        d_x_emb = (d_x2 +  # Residual da FFN
                   np.dot(d_Q, self.params['Wq'].T) + 
                   np.dot(d_K, self.params['Wk'].T) + 
                   np.dot(d_V, self.params['Wv'].T))
                   
        # Adiciona ao gradiente do w_token (parte 2: entrada)
        # Precisamos somar nas linhas correspondentes aos tokens usados
        # np.add.at é crucial aqui para índices repetidos
        np.add.at(grads['w_token'], cache['token_ids'], d_x_emb)
        
        return grads

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # [FIX] Salva o pacote completo: Pesos + Cérebro Linguístico
        state = {
            'params': self.params,
            'tokenizer_state': self.tokenizer.__dict__
        }
        with open(path, 'wb') as f:
            pickle.dump(state, f)
            
    def load(self, path):
        if os.path.exists(path):
            with open(path, 'rb') as f:
                state = pickle.load(f)
            
            # Suporte para versões legadas (se houver)
            if 'params' in state:
                self.params = state['params']
                # [FIX] Restaura a memória do Tokenizer
                if 'tokenizer_state' in state:
                    self.tokenizer.__dict__.update(state['tokenizer_state'])
            else:
                # Fallback para o formato antigo (só pesos) - Tokenizer ficará vazio
                self.params = state