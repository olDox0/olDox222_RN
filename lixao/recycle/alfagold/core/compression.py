# alfagold/core/compression.py
import numpy as np
from colorama import Fore

def compress_weights_svd(W, preservation_ratio=0.9):
    """
    Aplica Decomposição SVD para fatorar a matriz W em duas menores (A e B).
    W (M x N) ~ A (M x R) @ B (R x N)
    
    preservation_ratio: Quanto da 'energia' (variância) manter. 
    Reduzir isso diminui o Rank (R) e os FLOPs.
    """
    M, N = W.shape
    
    # 1. Decomposição de Valores Singulares (Heavy Math)
    # U: Base do espaço de entrada
    # S: Força de cada dimensão (Valores Singulares)
    # Vt: Base do espaço de saída
    try:
        U, S, Vt = np.linalg.svd(W, full_matrices=False)
    except np.linalg.LinAlgError:
        print(Fore.RED + "   ❌ SVD falhou (matriz instável). Mantendo original.")
        return None, None

    # 2. Determinar Rank O ideal (R)
    # Queremos manter X% da soma dos valores singulares
    total_energy = np.sum(S)
    cumulative_energy = np.cumsum(S)
    
    # Encontra o índice onde a energia acumulada passa do ratio
    rank = np.searchsorted(cumulative_energy, total_energy * preservation_ratio) + 1
    
    # Limite de segurança: O rank deve ser menor que M e N para valer a pena
    if rank >= min(M, N):
        # Não compensa comprimir
        return None, None
        
    print(f"   📉 Comprimindo: {M}x{N} -> Rank {rank} (Retém {preservation_ratio*100:.0f}% energia)")
    
    # 3. Truncar Matrizes
    U_k = U[:, :rank]
    S_k = np.diag(S[:rank])
    Vt_k = Vt[:rank, :]
    
    # 4. Fundir S nas matrizes U e V para evitar uma 3ª multiplicação
    # A = U * sqrt(S)
    # B = sqrt(S) * V
    sqrt_S = np.sqrt(S_k)
    
    matrix_A = np.dot(U_k, sqrt_S)
    matrix_B = np.dot(sqrt_S, Vt_k)
    
    # Validação de FLOPs
    original_flops = M * N
    new_flops = (M * rank) + (rank * N)
    reduction = 1.0 - (new_flops / original_flops)
    
    print(f"      FLOPs: {original_flops} -> {new_flops} (Redução: {reduction:.1%})")
    
    return matrix_A, matrix_B