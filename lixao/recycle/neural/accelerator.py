"""
DOXOADE ACCELERATOR.
Gerencia a compilação JIT (Just-In-Time) via Numba.
"""
# [DOX-UNUSED] import os
import warnings

# Suprime avisos de compilação para limpar o terminal
warnings.filterwarnings("ignore")

try:
    from numba import njit, prange
    
    # Configuração de Alta Performance
    # fastmath=True: Permite simplificações algébricas agressivas (pode perder precisão ínfima)
    # cache=True: Salva o binário compilado no disco para o próximo start ser instantâneo
    def jit(func):
        return njit(func, fastmath=True, cache=True, nogil=True)
    
    IS_ACCELERATED = True
    
except ImportError:
    # Fallback silencioso: Se não tem Numba, devolve a função original
    def jit(func):
        return func
    
    # prange vira range normal
    prange = range
    IS_ACCELERATED = False

def status():
    return "🚀 Numba JIT (Turbo)" if IS_ACCELERATED else "🐢 NumPy Puro (Compatibilidade)"