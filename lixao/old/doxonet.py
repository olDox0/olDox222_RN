"""
DOXONET CORE v1.0
Biblioteca de Redes Neurais Artificiais (Pure NumPy).
"""

import numpy as np
import pickle
import os
from typing import List, Dict, Optional

class RedeNeural:
    def __init__(self, camadas: List[int], seed: Optional[int] = None):
        # Validação básica
        assert len(camadas) >= 2, "A rede precisa de pelo menos 2 camadas."
        
        self.camadas = camadas
        self.parametros: Dict[str, np.ndarray] = {}
        self.velocidade: Dict[str, np.ndarray] = {}
        self.L = len(camadas) - 1
        
        if seed:
            np.random.seed(seed)
        
        # Inicialização de He (Otimizada)
        for l in range(1, self.L + 1):
            fator_escala = np.sqrt(2. / camadas[l-1])
            self.parametros['W' + str(l)] = np.random.randn(camadas[l-1], camadas[l]) * fator_escala
            self.parametros['b' + str(l)] = np.zeros((1, camadas[l]))
            self.velocidade['W' + str(l)] = np.zeros_like(self.parametros['W' + str(l)])
            self.velocidade['b' + str(l)] = np.zeros_like(self.parametros['b' + str(l)])
            
    def sigmoide(self, z: np.ndarray) -> np.ndarray:
        return 1 / (1 + np.exp(-np.clip(z, -500, 500)))
    
    def sigmoide_derivada(self, A: np.ndarray) -> np.ndarray:
        return A * (1 - A)

    def forward(self, X: np.ndarray) -> np.ndarray:
        self.cache = {}
        A = X
        for l in range(1, self.L + 1):
            A_anterior = A 
            W = self.parametros['W' + str(l)]
            b = self.parametros['b' + str(l)]
            Z = np.dot(A_anterior, W) + b
            A = self.sigmoide(Z)
            
            self.cache['A' + str(l-1)] = A_anterior
            self.cache['Z' + str(l)] = Z
            self.cache['A' + str(l)] = A
        return A

    def backward(self, Y: np.ndarray) -> Dict[str, np.ndarray]:
        gradientes = {}
        L = self.L
        m = Y.shape[0]
        A_final = self.cache['A' + str(L)]
        A_anterior = self.cache['A' + str(L-1)]
        
        dZ = A_final - Y
        gradientes['dW' + str(L)] = (1/m) * np.dot(A_anterior.T, dZ)
        gradientes['db' + str(L)] = (1/m) * np.sum(dZ, axis=0, keepdims=True)
        
        for l in reversed(range(1, L)):
            W_proximo = self.parametros['W' + str(l+1)]
            dA = np.dot(dZ, W_proximo.T)
            A_atual = self.cache['A' + str(l)]
            dZ = dA * self.sigmoide_derivada(A_atual)
            A_anterior = self.cache['A' + str(l-1)]
            gradientes['dW' + str(l)] = (1/m) * np.dot(A_anterior.T, dZ)
            gradientes['db' + str(l)] = (1/m) * np.sum(dZ, axis=0, keepdims=True)
        return gradientes

    def update(self, gradientes: Dict[str, np.ndarray], lr_atual: float, momentum: float = 0.9):
        for l in range(1, self.L + 1):
            self.velocidade['W' + str(l)] = (momentum * self.velocidade['W' + str(l)]) - (lr_atual * gradientes['dW' + str(l)])
            self.velocidade['b' + str(l)] = (momentum * self.velocidade['b' + str(l)]) - (lr_atual * gradientes['db' + str(l)])
            self.parametros['W' + str(l)] += self.velocidade['W' + str(l)]
            self.parametros['b' + str(l)] += self.velocidade['b' + str(l)]

    def treinar(self, X: np.ndarray, Y: np.ndarray, X_val: np.ndarray, y_val: np.ndarray, 
                epochs: int, taxa_aprendizado: float, decay: float = 0.0, 
                paciencia: int = 200, verbose: bool = False): # Nova variável: paciencia
        
        historico_custo = []
        lr_inicial = taxa_aprendizado
        
        # Variáveis para Early Stopping
        melhor_custo = float('inf')
        contador_paciencia = 0
        melhor_estado_parametros = None
        
        for i in range(epochs):
            lr_atual = lr_inicial * (1 / (1 + decay * i))
            A_final = self.forward(X)
            gradientes = self.backward(Y)
            self.update(gradientes, lr_atual)
            
            # Checagem de Custo e Early Stopping
            if i % 100 == 0: # Checa mais frequentemente
                custo = -1/Y.shape[0] * np.sum(Y * np.log(A_final + 1e-8) + (1-Y) * np.log(1 - A_final + 1e-8))
                historico_custo.append(custo)
                
                if verbose:
                    print(f"  > Epoca {i}: Custo={custo:.5f} | LR={lr_atual:.5f}")
                
                # Lógica de Parada
                if custo < melhor_custo:
                    melhor_custo = custo
                    contador_paciencia = 0
                    # Guardamos uma cópia profunda dos melhores pesos até agora
                    melhor_estado_parametros = pickle.loads(pickle.dumps(self.parametros))
                else:
                    contador_paciencia += 100 # Incrementamos pelo intervalo
                    
                if contador_paciencia >= paciencia:
                    if verbose: print(f"  🛑 Early Stopping ativado na época {i}. O aprendizado estagnou.")
                    self.parametros = melhor_estado_parametros # Restaura o melhor momento
                    break
        
        prev_val = self.forward(X_val)
        acertos = np.sum(np.argmax(prev_val, axis=1) == np.argmax(y_val, axis=1))
        return acertos / len(y_val), historico_custo

    def salvar(self, nome_arquivo: str):
        dados = {"parametros": self.parametros, "camadas": self.camadas, "velocidade": self.velocidade}
        with open(nome_arquivo, 'wb') as f:
            pickle.dump(dados, f)
        print(f"💾 Rede salva em '{nome_arquivo}'")

    @classmethod
    def carregar(cls, nome_arquivo: str):
        if not os.path.exists(nome_arquivo):
            raise FileNotFoundError(f"Arquivo '{nome_arquivo}' não encontrado.")
        with open(nome_arquivo, 'rb') as f:
            dados = pickle.load(f)
        rede = cls(camadas=dados['camadas'])
        rede.parametros = dados['parametros']
        rede.velocidade = dados['velocidade']
        print(f"📂 Rede carregada de '{nome_arquivo}'")
        return rede