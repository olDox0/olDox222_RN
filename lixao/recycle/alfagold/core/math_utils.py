# alfagold/core/math_utils.py
import numpy as np

# Tenta carregar a LUT, mas funciona sem ela (Fallback robusto)
try:
    from .math_lut import LUT
except ImportError:
    LUT = None

def softmax(x):
    """
    Função Softmax estável com proteção contra underflow.
    """
    # Garante float32 para velocidade/memória
    if x.dtype != np.float32:
        x = x.astype(np.float32)

    # Shift para estabilidade (x - max)
    shift_x = x - np.max(x, axis=-1, keepdims=True)
    
    if LUT:
        e_x = LUT.exp(shift_x)
    else:
        e_x = np.exp(shift_x)
        
    # [FIX] Adição de epsilon para evitar divisão por zero
    return e_x / (np.sum(e_x, axis=-1, keepdims=True) + 1e-9)

def gelu(x):
    """Gaussian Error Linear Unit (Aproximação Tanh)."""
    if LUT:
        return LUT.gelu(x)
    
    # Fallback Micro-otimizado
    S2PI = 0.7978845608 # sqrt(2/pi)
    COEF = 0.044715
    
    # x*x*x é mais rápido que pow(x, 3)
    inner = S2PI * (x + COEF * (x * x * x))
    return 0.5 * x * (1 + np.tanh(inner))

def d_gelu(x):
    """
    Derivada da GELU (Consistente com a aproximação Tanh).
    Corrigido para bater matematicamente com o Forward.
    """
    if LUT:
        return LUT.d_gelu(x)
        
    # Constantes
    S2PI = 0.7978845608
    COEF = 0.044715
    
    # Cálculos intermediários reutilizáveis
    x2 = x * x
    x3 = x2 * x
    
    inner = S2PI * (x + COEF * x3)
    tanh_inner = np.tanh(inner)
    
    # Derivada da tanh é (1 - tanh^2)
    sech2 = 1.0 - (tanh_inner * tanh_inner)
    
    # Regra da Cadeia aplicada à aproximação:
    # d/dx = 0.5 * (1 + tanh) + 0.5 * x * sech2 * S2PI * (1 + 3 * COEF * x^2)
    term1 = 0.5 * (1 + tanh_inner)
    term2 = 0.5 * x * sech2 * S2PI * (1.0 + 3.0 * COEF * x2)
    
    return term1 + term2

def dropout(x, p=0.1, training=True):
    """
    Inverted Dropout seguro.
    """
    # [FIX] Proteção contra probabilidades inválidas
    p = np.clip(p, 0.0, 0.99)
    
    if not training or p <= 0.0:
        return x, None
    
    keep_prob = 1.0 - p
    # Máscara: 1 se mantiver, 0 se desligar
    mask = (np.random.rand(*x.shape) < keep_prob).astype(np.float32)
    
    # Escala inversa para manter a magnitude
    scale = 1.0 / keep_prob
    return x * mask * scale, mask

def d_dropout(dout, mask, p=0.1):
    """Backprop do Dropout."""
    if mask is None:
        return dout
    
    # Recalcula scale para consistência (ou poderia vir no cache)
    p = np.clip(p, 0.0, 0.99)
    scale = 1.0 / (1.0 - p)
    
    return dout * mask * scale