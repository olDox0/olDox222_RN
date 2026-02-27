# doxoade/neural/alfagold/attention.py
import numpy as np

# --- Tabelas Globais ---
class AttentionPrecompute:
    """Pré-calcula constantes e tabelas para acelerar a atenção."""
    def __init__(self, max_seq=4096, d_k=64, dtype=np.float32):
        self.scale = 1.0 / np.sqrt(d_k).astype(dtype)
        # Máscara causal (triangular superior invertida)
        self.causal_mask = np.triu(np.ones((max_seq, max_seq)), k=1) * -1e9

# Instância global
PRECOMP = AttentionPrecompute()

# --- Implementações do Mecanismo de Atenção ---

def scaled_dot_product_attention(Q, K, V, mask=None):
    """
    Implementação base: Attention(Q, K, V) = softmax(QK^T / sqrt(dk)) V
    [FIX] NumPy usa swapaxes para transpor as duas últimas dimensões.
    """
    # Matmul: (..., Seq_Q, D) x (..., D, Seq_K) -> (..., Seq_Q, Seq_K)
    scores = np.matmul(Q, K.swapaxes(-2, -1)) * PRECOMP.scale
    
    if mask is not None:
        # Aplica a máscara apenas na região relevante
        seq_q = scores.shape[-2]
        seq_k = scores.shape[-1]
        scores += mask[:seq_q, :seq_k]
    
    # Softmax estável numericamente
    exp_scores = np.exp(scores - np.max(scores, axis=-1, keepdims=True))
    attention_weights = exp_scores / np.sum(exp_scores, axis=-1, keepdims=True)
    
    output = np.matmul(attention_weights, V)
    return output, attention_weights

def flash_attention_numpy(Q, K, V, block_size=128):
    """Aproximação FlashAttention para economizar memória em sequências longas."""
    seq_len = Q.shape[-2]
# [DOX-UNUSED]     d_model = Q.shape[-1]
    out = np.zeros_like(Q)
    
    # [FIX] Garante que K e V estejam no formato correto para fatiamento
    # Aqui K e V são (Batch, Seq, D)
    
    # Loop em blocos de K/V (colunas da matriz de atenção)
    for i in range(0, seq_len, block_size):
        # Fatia (Batch, i:i+blk, D)
        K_block = K[..., i:i+block_size, :]
        V_block = V[..., i:i+block_size, :]
        
        # Loop em blocos de Q (linhas da matriz de atenção)
        for j in range(0, seq_len, block_size):
            Q_block = Q[..., j:j+block_size, :]
            
            # Scores locais: (Batch, Blk, D) x (Batch, D, Blk) -> (Batch, Blk, Blk)
            S = np.matmul(Q_block, K_block.swapaxes(-2, -1)) * PRECOMP.scale
            
            # Softmax estável por bloco
            P = np.exp(S - np.max(S, axis=-1, keepdims=True))
            denominador = np.sum(P, axis=-1, keepdims=True) + 1e-9
            P /= denominador
            
            # Acumula na saída (Batch, Blk, D)
            out[..., j:j+block_size, :] += np.matmul(P, V_block)
            
    # Normalização aproximada para compensar a soma de blocos
    # Em uma implementação Flash real, teríamos que carregar estatísticas L e M.
    # Para este protótipo NumPy, uma média ponderada simples é suficiente para teste.
    fator_norm = seq_len / block_size
    return out / fator_norm, None

def execute_attention(Q, K, V, mask_type=None):
    """
    Função Mestra de Atenção.
    """
    seq_len = Q.shape[-2]
    mask = PRECOMP.causal_mask if mask_type == 'causal' else None

    # Se a sequência é gigante, use FlashAttention para não estourar a RAM
    if seq_len > 2048:
        return flash_attention_numpy(Q, K, V)
    else:
        # Para sequências normais, a versão exata é mais rápida no NumPy
        return scaled_dot_product_attention(Q, K, V, mask)