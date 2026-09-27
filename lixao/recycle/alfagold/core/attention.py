# alfagold/core/attention.py
import numpy as np

class AttentionPrecompute:
    def __init__(self, max_seq=4096, d_k=64, dtype=np.float32):
        self.scale = 1.0 / np.sqrt(d_k).astype(dtype)
        self.causal_mask = np.triu(np.ones((max_seq, max_seq)), k=1) * -1e9

PRECOMP = AttentionPrecompute()

def multi_head_attention(Q, K, V, n_heads, mask_type=None):
    """
    Mecanismo de Atenção Multi-Head (Hydra).
    """
    # 1. Normalização de Input (Garante 3D: Batch, Seq, Dim)
    is_2d = Q.ndim == 2
    if is_2d:
        Q = Q[np.newaxis, ...] # (1, Seq, Dim)
        K = K[np.newaxis, ...]
        V = V[np.newaxis, ...]
    
    batch_size, seq_len, d_model = Q.shape
    d_head = d_model // n_heads
    
    # 2. Split Heads
    # (Batch, Seq, Heads, D_head) -> (Batch, Heads, Seq, D_head)
    Q_s = Q.reshape(batch_size, seq_len, n_heads, d_head).swapaxes(1, 2)
    K_s = K.reshape(batch_size, seq_len, n_heads, d_head).swapaxes(1, 2)
    V_s = V.reshape(batch_size, seq_len, n_heads, d_head).swapaxes(1, 2)
    
    # 3. Scaled Dot-Product
    # scale ajustado para d_head
    scale = 1.0 / np.sqrt(d_head)
    scores = np.matmul(Q_s, K_s.swapaxes(-1, -2)) * scale
    
    if mask_type == 'causal':
        mask = PRECOMP.causal_mask[:seq_len, :seq_len]
        scores += mask
    
    # 4. Softmax
    scores_shifted = scores - np.max(scores, axis=-1, keepdims=True)
    exp_scores = np.exp(scores_shifted)
    weights = exp_scores / np.sum(exp_scores, axis=-1, keepdims=True)
    
    # 5. Output Ponderado
    attn_out_s = np.matmul(weights, V_s)
    
    # 6. Merge Heads
    # (Batch, Heads, Seq, D_head) -> (Batch, Seq, Heads, D_head) -> (Batch, Seq, D_model)
    out = attn_out_s.swapaxes(1, 2).reshape(batch_size, seq_len, d_model)
    
    if is_2d:
        return out[0], weights[0]
        
    return out, weights

execute_attention = multi_head_attention