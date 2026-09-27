# alfagold/core/transformer.py
import numpy as np
# [DOX-UNUSED] import os
from typing import Dict, Optional

from .attention import execute_attention
from .tokenizer import AlfagoldTokenizer
from .persistence import save_model_state, load_model_state
from .math_lut import LUT 

class Alfagold:
    """
    Alfagold v7.3 (Dynamic Resizing).
    Suporta carregamento de modelos com dimensões diferentes do padrão.
    """
    def __init__(self, vocab_size: int = 2000, d_model: int = 64, max_len: int = 128, num_phases: int = 6, n_heads: int = 4, dropout_rate: float = 0.1):
        self.d_model = d_model
        self.n_heads = n_heads
        self.max_len = max_len
        self.vocab_size = vocab_size
        self.num_phases = num_phases
        self.dropout_rate = dropout_rate
        self.tokenizer = AlfagoldTokenizer()
        
        # Validação básica
        if d_model % n_heads != 0:
            # Ajuste automático se necessário para evitar crash
            self.n_heads = 1
        
        # Calcula escala para d_head (usado na atenção, não aqui, mas bom ter)
        self.d_head = d_model // self.n_heads
        
        scale = 1.0 / np.sqrt(d_model)
        
        self.params = {
            'w_token': np.random.randn(vocab_size, d_model).astype(np.float32) * scale,
            'w_pos': self._create_positional_encoding(max_len, d_model),
            
            'ln1_gamma': np.ones(d_model, dtype=np.float32),
            'ln1_beta': np.zeros(d_model, dtype=np.float32),
            'ln2_gamma': np.ones(d_model, dtype=np.float32),
            'ln2_beta': np.zeros(d_model, dtype=np.float32),

            'Wq': np.random.randn(d_model, d_model).astype(np.float32) * scale,
            'Wk': np.random.randn(d_model, d_model).astype(np.float32) * scale,
            'Wv': np.random.randn(d_model, d_model).astype(np.float32) * scale,
            'Wo': np.random.randn(d_model, d_model).astype(np.float32) * scale,
            
            'W1': np.random.randn(d_model, d_model * 4).astype(np.float32) * scale,
            'b1': np.zeros(d_model * 4, dtype=np.float32),
            'W2': np.random.randn(d_model * 4, d_model).astype(np.float32) * scale,
            'b2': np.zeros(d_model, dtype=np.float32),
            
            'w_out': np.random.randn(d_model, vocab_size).astype(np.float32) * scale,
            'W_phase': np.random.randn(d_model, num_phases).astype(np.float32) * scale,
            'b_phase': np.zeros(num_phases, dtype=np.float32)
        }
        
        # Aloca memória
        self._init_cache()

    def _init_cache(self):
        """[FIX] Aloca o Master Cache baseado nas dimensões atuais."""
        # Se d_model mudou (ex: load), isso garante que o cache tenha o tamanho certo
        self.master_cache = {
            'x_emb': np.zeros((self.max_len, self.d_model), dtype=np.float32),
            'Q': np.zeros((self.max_len, self.d_model), dtype=np.float32),
            'K': np.zeros((self.max_len, self.d_model), dtype=np.float32),
            'V': np.zeros((self.max_len, self.d_model), dtype=np.float32),
            'x2': np.zeros((self.max_len, self.d_model), dtype=np.float32),
            'ff_hidden': np.zeros((self.max_len, self.d_model * 4), dtype=np.float32),
            'ff_act': np.zeros((self.max_len, self.d_model * 4), dtype=np.float32),
            'x_final': np.zeros((self.max_len, self.d_model), dtype=np.float32),
            'ln1': (None, None, None),
            'ln2': (None, None, None),
            'drop1_mask': None,
            'drop2_mask': None
        }

    def _create_positional_encoding(self, max_len: int, d_model: int) -> np.ndarray:
        pe = np.zeros((max_len, d_model), dtype=np.float32)
        position = np.arange(0, max_len)[:, np.newaxis]
        div_term = np.exp(np.arange(0, d_model, 2) * -(np.log(10000.0) / d_model))
        pe[:, 0::2] = np.sin(position * div_term)
        pe[:, 1::2] = np.cos(position * div_term)
        return pe

    def _layer_norm_forward(self, x, gamma, beta):
        mean = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        x_hat = (x - mean) / np.sqrt(var + 1e-5)
        out = gamma * x_hat + beta
        return out, (mean, var, x_hat)
        
    def _layer_norm_backward(self, dout, cache, gamma):
        mean, var, x_hat = cache
        N, D = dout.shape
        dgamma = np.sum(dout * x_hat, axis=0)
        dbeta = np.sum(dout, axis=0)
        dx_hat = dout * gamma
        ivar = 1.0 / np.sqrt(var + 1e-5)
        dx = (1.0 / D) * ivar * (D * dx_hat - np.sum(dx_hat, axis=1, keepdims=True) - x_hat * np.sum(dx_hat * x_hat, axis=1, keepdims=True))
        return dx, dgamma, dbeta

    def forward(self, token_ids: list, training: bool = False, kv_cache: Optional[Dict] = None):
        n_new = len(token_ids)
        start_pos = 0
        if kv_cache: start_pos = kv_cache['k'].shape[1]
        
        # Validação de Tamanho
        if start_pos + n_new > self.max_len:
            if training: token_ids = token_ids[:self.max_len - start_pos]
            else: return np.zeros((1, self.vocab_size)), np.zeros((1, self.num_phases)), kv_cache

        n = len(token_ids)
        pos_emb = self.params['w_pos'][start_pos : start_pos + n]
        x = self.params['w_token'][token_ids] + pos_emb
        
        if training: self.master_cache['x_emb'][:n] = x

        # 1. ATENÇÃO
        x_ln1, ln1_cache = self._layer_norm_forward(x, self.params['ln1_gamma'], self.params['ln1_beta'])
        if training: self.master_cache['ln1'] = ln1_cache
        
        Q_new = np.dot(x_ln1, self.params['Wq'])
        K_new = np.dot(x_ln1, self.params['Wk'])
        V_new = np.dot(x_ln1, self.params['Wv'])
        
        if training:
            # Atribuição segura
            self.master_cache['Q'][:n] = Q_new
            self.master_cache['K'][:n] = K_new
            self.master_cache['V'][:n] = V_new
            Q, K, V = self.master_cache['Q'][:n], self.master_cache['K'][:n], self.master_cache['V'][:n]
        else:
            Q = Q_new
            if kv_cache:
                K = np.concatenate([kv_cache['k'], K_new], axis=1)
                V = np.concatenate([kv_cache['v'], V_new], axis=1)
            else: K, V = K_new, V_new
        
        next_kv_cache = {'k': K, 'v': V} if not training else None
        
        attn_out, weights = execute_attention(Q, K, V, self.n_heads, mask_type='causal')
        
        x2 = x + np.dot(attn_out, self.params['Wo'])
        if training: self.master_cache['x2'][:n] = x2

        # 2. FFN
        x_ln2, ln2_cache = self._layer_norm_forward(x2, self.params['ln2_gamma'], self.params['ln2_beta'])
        if training: self.master_cache['ln2'] = ln2_cache
        
        ff_hidden = np.dot(x_ln2, self.params['W1']) + self.params['b1']
        if training: self.master_cache['ff_hidden'][:n] = ff_hidden
        
        ff_act = LUT.gelu(ff_hidden)
        if training: self.master_cache['ff_act'][:n] = ff_act
        
        x_final = x2 + np.dot(ff_act, self.params['W2']) + self.params['b2']
        if training: self.master_cache['x_final'][:n] = x_final
        
        logits_token = np.dot(x_final, self.params['w_out']) 
        logits_phase = np.dot(x_final, self.params['W_phase']) + self.params['b_phase']
        
        if training:
            context = {
                'token_ids': token_ids, 'n': n, 
                'attn_weights': weights,
                'attn_out': attn_out,
                'x_final': self.master_cache['x_final'][:n] 
            }
            return logits_token, logits_phase, context
        else:
            return logits_token, logits_phase, next_kv_cache

    def backward(self, d_logits_token, d_logits_phase, context):
        n = context['n']
        token_ids = context['token_ids']
        
        x_final = self.master_cache['x_final'][:n]
        ff_act = self.master_cache['ff_act'][:n]
        ff_hidden = self.master_cache['ff_hidden'][:n]
# [DOX-UNUSED]         x_emb = self.master_cache['x_emb'][:n]
        
        grads = {k: np.zeros_like(v) for k, v in self.params.items()}
        
        # Heads
        d_x_final = np.dot(d_logits_phase, self.params['W_phase'].T) + np.dot(d_logits_token, self.params['w_out'].T)
        grads['W_phase'] = np.dot(x_final.T, d_logits_phase)
        grads['b_phase'] = np.sum(d_logits_phase, axis=0)
        grads['w_out'] = np.dot(x_final.T, d_logits_token)
        
        # FFN
        d_ff_out = d_x_final
        grads['W2'] = np.dot(ff_act.T, d_ff_out); grads['b2'] = np.sum(d_ff_out, axis=0)
        d_ff_hidden = np.dot(d_ff_out, self.params['W2'].T) * LUT.d_gelu(ff_hidden)
        grads['W1'] = np.dot(self.master_cache['ln2'][0].T, d_ff_hidden); grads['b1'] = np.sum(d_ff_hidden, axis=0)
        d_x_ln2 = np.dot(d_ff_hidden, self.params['W1'].T)
        d_x2_norm, grads['ln2_gamma'], grads['ln2_beta'] = self._layer_norm_backward(d_x_ln2, self.master_cache['ln2'], self.params['ln2_gamma'])
        d_x2 = d_x2_norm + d_x_final
        
        # Attention
        d_attn_out = np.dot(d_x2, self.params['Wo'].T)
        grads['Wo'] = np.dot(context['attn_out'].T, d_x2)
        
        # Backprop Simplificado (Média das Cabeças para Wo->V)
        avg_weights = np.mean(context['attn_weights'], axis=0)
        V = self.master_cache['V'][:n]
        K = self.master_cache['K'][:n]
        Q = self.master_cache['Q'][:n]
        
        d_V = np.dot(avg_weights.T, d_attn_out)
        d_weights = np.dot(d_attn_out, V.T)
        d_scores = d_weights * (1.0 / np.sqrt(self.d_model // self.n_heads))
        d_Q = np.dot(d_scores, K)
        d_K = np.dot(d_scores.T, Q)
        
        grads['Wq'] = np.dot(self.master_cache['ln1'][0].T, d_Q)
        grads['Wk'] = np.dot(self.master_cache['ln1'][0].T, d_K)
        grads['Wv'] = np.dot(self.master_cache['ln1'][0].T, d_V)
        
        d_x_ln1 = np.dot(d_Q, self.params['Wq'].T) + np.dot(d_K, self.params['Wk'].T) + np.dot(d_V, self.params['Wv'].T)
        d_x_norm, grads['ln1_gamma'], grads['ln1_beta'] = self._layer_norm_backward(d_x_ln1, self.master_cache['ln1'], self.params['ln1_gamma'])
        
        d_x = d_x_norm + d_x2
        np.add.at(grads['w_token'], token_ids, d_x)
        return grads
        
    def save(self, path: str):
        base_path = path.replace('.pkl', '').replace('.npz', '')
        config = {
            'vocab_size': self.vocab_size, 'd_model': self.d_model, 
            'max_len': self.max_len, 'num_phases': self.num_phases, 
            'n_heads': self.n_heads, 'dropout_rate': self.dropout_rate,
            'tokenizer_state': self.tokenizer.get_state()
        }
        save_model_state(base_path, self.params, config)

    def load(self, path: str):
        base_path = path.replace('.pkl', '').replace('.npz', '')
        try:
            params, config = load_model_state(base_path)
            
            # [FIX] Atualiza dimensões ANTES de carregar pesos
            if 'd_model' in config: self.d_model = config['d_model']
            if 'max_len' in config: self.max_len = config['max_len']
            if 'n_heads' in config: self.n_heads = config['n_heads']
            
            # [FIX] Reconstrói o cache com as novas dimensões
            self._init_cache()
            
            for k, v in params.items():
                if k in self.params: self.params[k] = v
                
            if 'tokenizer_state' in config: self.tokenizer.set_state(config['tokenizer_state'])
        except Exception: pass