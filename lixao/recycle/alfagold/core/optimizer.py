# alfagold/core/optimizer.py
import numpy as np

class AdamW:
    def __init__(self, params, lr=1e-3, beta1=0.9, beta2=0.999, eps=1e-8, weight_decay=0.01):
        self.params = params 
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.wd = weight_decay
        
        self.m = {}
        self.v = {}
        self.t = 0
        
        for key, param in self.params.items():
            self.m[key] = np.zeros_like(param)
            self.v[key] = np.zeros_like(param)

    def step(self, grads):
        self.t += 1
        
        # Pré-calcula escalares de correção de viés (Scalar Bias Correction)
        bias_correction1 = 1.0 - self.beta1 ** self.t
        bias_correction2 = 1.0 - self.beta2 ** self.t
        
        # Otimização: lr corrigido para aplicar multiplicativamente
        # step_size = lr / bias_correction1
        step_size = self.lr * (np.sqrt(bias_correction2) / bias_correction1)
        
        for key in self.params:
            if key not in grads: continue
            
            param = self.params[key]
            grad = grads[key]
            m = self.m[key]
            v = self.v[key]
            
            # --- OPERAÇÕES IN-PLACE (Velocidade Extrema) ---
            
            # 1. Weight Decay: param *= (1 - lr * wd)
            if self.wd > 0:
                param *= (1.0 - self.lr * self.wd)
            
            # 2. Update Momentos (In-Place)
            # m = b1*m + (1-b1)*g  ->  m *= b1; m += (1-b1)*g
            m *= self.beta1
            m += (1.0 - self.beta1) * grad
            
            # v = b2*v + (1-b2)*g^2
            v *= self.beta2
            v += (1.0 - self.beta2) * (grad * grad) # grad**2 aloca, grad*grad é mais rápido
            
            # 3. Update Pesos (Usando step_size pré-calculado)
            # param -= step_size * m / (sqrt(v) + eps)
            denom = np.sqrt(v)
            denom += self.eps
            
            update = m / denom
            param -= step_size * update