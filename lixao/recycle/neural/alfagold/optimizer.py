# doxoade/neural/alfagold/optimizer.py
import numpy as np

class AdamW:
    def __init__(self, params, lr=1e-3, beta1=0.9, beta2=0.999, eps=1e-8, weight_decay=0.01):
        """
        Otimizador Adam com Weight Decay (AdamW).
        params: Dicionário ou lista de arrays numpy (os pesos do modelo).
        """
        self.params = params 
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.wd = weight_decay
        
        # Estado do otimizador (Momentos)
        self.m = {}
        self.v = {}
        self.t = 0
        
        # Inicializa momentos
        for key, param in self.params.items():
            self.m[key] = np.zeros_like(param)
            self.v[key] = np.zeros_like(param)

    def step(self, grads):
        """Aplica os gradientes aos pesos."""
        self.t += 1
        
        for key in self.params:
            if key not in grads: continue
            
            param = self.params[key]
            grad = grads[key]
            
            # 1. Weight Decay (Evita overfitting explodindo pesos)
            param = param - (self.lr * self.wd * param)
            
            # 2. Adam (Momentum e RMSProp combinados)
            self.m[key] = self.beta1 * self.m[key] + (1 - self.beta1) * grad
            self.v[key] = self.beta2 * self.v[key] + (1 - self.beta2) * (grad ** 2)
            
            # 3. Correção de Viés (Bias Correction)
            m_hat = self.m[key] / (1 - self.beta1 ** self.t)
            v_hat = self.v[key] / (1 - self.beta2 ** self.t)
            
            # 4. Atualização Final
            # w = w - lr * m_hat / (sqrt(v_hat) + eps)
            self.params[key] = param - self.lr * m_hat / (np.sqrt(v_hat) + self.eps)