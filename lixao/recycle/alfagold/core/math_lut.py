# alfagold/core/math_lut.py
import numpy as np

# No topo do arquivo
try:
    from ..config.hardware import HW_CONFIG
    DEFAULT_RES = HW_CONFIG['LUT_RESOLUTION']
except ImportError:
    DEFAULT_RES = 65536
    
try:
    from ..config.hardware import get_resolution
except ImportError:
    def get_resolution(): return 65536

class MathLUT:
    """
    Lookup Table v2.3 (Input Clamping).
    Força os inputs para dentro do range válido ANTES do cálculo de índice.
    Elimina 'invalid value encountered in cast'.
    """
    def __init__(self, resolution=None, range_min=-10.0, range_max=10.0):
        if resolution is None:
            resolution = get_resolution()
            
        self.min = float(range_min)
        self.max = float(range_max)
        self.resolution = resolution
        self.step = (range_max - range_min) / (resolution - 1)
        self.inv_step = 1.0 / self.step
        
        self._ready = False
        self.gelu_table = None
        self.d_gelu_table = None
        self.exp_table = None

    def _lazy_init(self):
        if self._ready: return
        
        x = np.linspace(self.min, self.max, self.resolution).astype(np.float32)
        
        # GELU
        SQRT_2_OVER_PI = np.sqrt(2 / np.pi).astype(np.float32)
        COEF = 0.044715
        inner = SQRT_2_OVER_PI * (x + COEF * (x * x * x))
        self.gelu_table = 0.5 * x * (1 + np.tanh(inner))
        
        # Derivada GELU
        self.d_gelu_table = np.gradient(self.gelu_table, self.step)
        
        # EXP
        self.exp_table = np.exp(x)
        self._ready = True

    def _lookup_interpolated(self, x, table_name):
        if not self._ready: self._lazy_init()
        
        # [FIX CRÍTICO] Input Clamping
        # Força x para dentro dos limites da tabela (-10 a 10)
        # Isso resolve NaN, Inf e Overflow de índice de uma vez só
        x_clamped = np.clip(np.nan_to_num(x), self.min, self.max)
        
        if table_name == 'gelu': table = self.gelu_table
        elif table_name == 'd_gelu': table = self.d_gelu_table
        elif table_name == 'exp': table = self.exp_table
        else: return x_clamped

        # Mapeamento Seguro
        x_idx = (x_clamped - self.min) * self.inv_step
        idx_i = np.floor(x_idx).astype(np.int32)
        
        # Clip adicional de segurança nos índices (bordas da tabela)
        idx_i = np.clip(idx_i, 0, self.resolution - 2)
        
        t = x_idx - idx_i
        # t também precisa ser clipado por segurança numérica float
        t = np.clip(t, 0.0, 1.0)
        
        y0 = table[idx_i]
        y1 = table[idx_i + 1]
        
        return y0 + t * (y1 - y0)

    def gelu(self, x): return self._lookup_interpolated(x, 'gelu')
    def d_gelu(self, x): return self._lookup_interpolated(x, 'd_gelu')
    def exp(self, x): return self._lookup_interpolated(x, 'exp')

try:
    LUT = MathLUT()
except Exception:
    LUT = None