"""
Módulo Principal - Engine de Rede Neural Evolutiva.

Este script implementa uma Rede Neural Artificial (MLP) do zero usando NumPy,
incluindo funcionalidades avançadas como Momentum, Learning Rate Decay e
um Algoritmo Genético para otimização de hiperparâmetros (Meta-Learning).

Autor: olDox222
"""

import numpy as np
import random
from typing import List, Tuple, Dict, Optional
from sklearn.datasets import load_digits
from sklearn.preprocessing import OneHotEncoder
from sklearn.model_selection import train_test_split

# --- 1. A ESPÉCIE (A CLASSE) ---

class RedeNeural:
    """
    Representa uma Rede Neural Perceptron Multicamadas (MLP).
    Suporta N camadas ocultas, Momentum e Inicialização de He.
    """

    def __init__(self, camadas: List[int], seed: Optional[int] = None):
        """
        Inicializa a rede neural.

        Args:
            camadas (List[int]): Lista definindo a arquitetura. Ex: [64, 32, 10].
            seed (int, opcional): Semente para reprodutibilidade.
        """
        assert len(camadas) >= 2, "A rede precisa de pelo menos 2 camadas (Entrada e Saída)."
        
        self.camadas = camadas
        self.parametros: Dict[str, np.ndarray] = {}
        self.velocidade: Dict[str, np.ndarray] = {}
        self.L = len(camadas) - 1
        
        if seed:
            np.random.seed(seed)
        
        for l in range(1, self.L + 1):
            # Inicialização de He (Otimizada para ReLU/Sigmoid profunda)
            fator_escala = np.sqrt(2. / camadas[l-1])
            
            self.parametros['W' + str(l)] = np.random.randn(camadas[l-1], camadas[l]) * fator_escala
            self.parametros['b' + str(l)] = np.zeros((1, camadas[l]))
            
            # Inicializa vetores de velocidade para o Momentum
            self.velocidade['W' + str(l)] = np.zeros_like(self.parametros['W' + str(l)])
            self.velocidade['b' + str(l)] = np.zeros_like(self.parametros['b' + str(l)])
            
    def sigmoide(self, z: np.ndarray) -> np.ndarray:
        """
        Função de ativação Sigmoide.
        Inclui 'clip' para evitar overflow numérico em redes profundas.
        """
        return 1 / (1 + np.exp(-np.clip(z, -500, 500)))
    
    def sigmoide_derivada(self, A: np.ndarray) -> np.ndarray:
        """Calcula a derivada da sigmoide dado o valor de ativação A."""
        return A * (1 - A)

    def forward(self, X: np.ndarray) -> np.ndarray:
        """
        Realiza a propagação direta (feedforward).
        
        Args:
            X: Dados de entrada de formato (batch_size, input_dim).
        """
        # Verificação de segurança dimensional
        assert X.shape[1] == self.camadas[0], \
            f"Erro de Dimensão: Esperado {self.camadas[0]} inputs, recebido {X.shape[1]}"

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
        """
        Calcula os gradientes usando Backpropagation.
        
        Args:
            Y: Labels verdadeiros (One-Hot Encoded).
        """
        gradientes = {}
        L = self.L
        m = Y.shape[0]
        
        A_final = self.cache['A' + str(L)]
        
        # Assert para garantir que não estamos comparando laranjas com bananas
        assert A_final.shape == Y.shape, \
            f"Erro de Shape: Previsão {A_final.shape} vs Target {Y.shape}"

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
        """
        Atualiza os pesos usando Gradient Descent com Momentum.
        """
        for l in range(1, self.L + 1):
            # Física: V_nova = (Atrito * V_antiga) - (Aceleração * Gradiente)
            self.velocidade['W' + str(l)] = (momentum * self.velocidade['W' + str(l)]) - (lr_atual * gradientes['dW' + str(l)])
            self.velocidade['b' + str(l)] = (momentum * self.velocidade['b' + str(l)]) - (lr_atual * gradientes['db' + str(l)])
            
            # Atualiza posição
            self.parametros['W' + str(l)] += self.velocidade['W' + str(l)]
            self.parametros['b' + str(l)] += self.velocidade['b' + str(l)]

    def treinar(self, X: np.ndarray, Y: np.ndarray, X_val: np.ndarray, y_val: np.ndarray, 
                epochs: int, taxa_aprendizado: float, decay: float = 0.0, verbose: bool = False) -> Tuple[float, List[float]]:
        """
        Loop principal de treinamento com Learning Rate Decay.
        
        Returns:
            acuracia (float): Acurácia final no conjunto de validação.
            historico_custo (List[float]): Lista com a evolução do erro.
        """
        assert X.shape[0] == Y.shape[0], "Número de exemplos X e Y deve ser igual."
        
        historico_custo = []
        lr_inicial = taxa_aprendizado
        
        for i in range(epochs):
            # Adaptação Dinâmica (Decay)
            lr_atual = lr_inicial * (1 / (1 + decay * i))
            
            A_final = self.forward(X)
            gradientes = self.backward(Y)
            self.update(gradientes, lr_atual)
            
            if verbose and i % 200 == 0:
                custo = -1/Y.shape[0] * np.sum(Y * np.log(A_final + 1e-8) + (1-Y) * np.log(1 - A_final + 1e-8))
                print(f"  > Epoca {i}: Custo={custo:.4f} | LR={lr_atual:.5f}")
                historico_custo.append(custo)
        
        # Avaliação Final
        prev_val = self.forward(X_val)
        acertos = np.sum(np.argmax(prev_val, axis=1) == np.argmax(y_val, axis=1))
        acuracia = acertos / len(y_val)
        
        return acuracia, historico_custo

# --- 2. O LABORATÓRIO ---

digits = load_digits()
X = digits.data / 16.0 
y_orig = digits.target.reshape(-1, 1)
encoder = OneHotEncoder(sparse_output=False)
y = encoder.fit_transform(y_orig)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# --- 3. EVOLUÇÃO COM PARÂMETROS ADAPTATIVOS ---

def criar_mutante() -> Tuple[List[int], float, float]:
    """
    Gera aleatoriamente uma arquitetura e hiperparâmetros.
    Retorna: (lista_camadas, learning_rate, decay)
    """
    h1 = random.randint(30, 90)
    h2 = random.choice([None, random.randint(20, 50)])
    
    if h2:
        camadas = [64, h1, h2, 10]
    else:
        camadas = [64, h1, 10]
        
    lr = random.choice([0.1, 0.5, 1.0, 2.0]) 
    decay = random.choice([0.0, 0.0001, 0.001, 0.01])
    
    return camadas, lr, decay

# --- 4. EXECUÇÃO ---

if __name__ == "__main__":
    print("--- EVOLUÇÃO 3.0: CÓDIGO LIMPO & ROBUSTO ---")
    print("Verificando integridade estrutural...\n")

    melhor_acuracia = 0.0
    melhor_config = {}
    melhor_cerebro = None # type: ignore

    num_mutantes = 6

    for i in range(num_mutantes):
        camadas_teste, lr_teste, decay_teste = criar_mutante()
        print(f"🧬 Mutante {i+1}: Arq={camadas_teste} | LR={lr_teste} | Decay={decay_teste}")
        
        try:
            cerebro = RedeNeural(camadas=camadas_teste)
            acc, _ = cerebro.treinar(X_train, y_train, X_test, y_test, epochs=500, taxa_aprendizado=lr_teste, decay=decay_teste)
            print(f"   Aptidão: {acc*100:.2f}%")
            
            if acc > melhor_acuracia:
                melhor_acuracia = acc
                melhor_config = {'camadas': camadas_teste, 'lr': lr_teste, 'decay': decay_teste}
                melhor_cerebro = cerebro
                print("   -> NOVO LÍDER! 🏆")
        except AssertionError as e:
            print(f"   [FALHA GENÉTICA] Mutante morreu ao nascer: {e}")
            
        print("-" * 30)

    print("\n" + "="*50)
    print(f"VENCEDOR: {melhor_config}")
    print("="*50)

    if melhor_cerebro:
        print("\nTreinando o Vencedor até a perfeição (3000 épocas)...")
        acc_final, hist = melhor_cerebro.treinar(X_train, y_train, X_test, y_test, 
                                                 epochs=3000, 
                                                 taxa_aprendizado=melhor_config['lr'], 
                                                 decay=melhor_config['decay'], 
                                                 verbose=True)

        print(f"\n🎯 ACURÁCIA FINAL: {acc_final*100:.2f}%")

        print("\nGráfico de Aprendizado (Queda do Custo):")
        max_val = max(hist) if hist else 1
        for val in hist:
            barras = int((val / max_val) * 20)
            print(f"{val:.4f} | " + "█" * barras)