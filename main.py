# Mantenha os imports no topo
import numpy as np
from sklearn.datasets import load_digits
from sklearn.preprocessing import OneHotEncoder
from sklearn.model_selection import train_test_split

class RedeNeural:
    def __init__(self, camadas):
        self.camadas = camadas
        self.parametros = {}
        # AQUI MUDOU: Criamos um dicionário para guardar a velocidade (inércia)
        self.velocidade = {} 
        self.L = len(camadas) - 1
        
        np.random.seed(42)
        
        for l in range(1, self.L + 1):
            self.parametros['W' + str(l)] = np.random.randn(camadas[l-1], camadas[l]) * 0.1 # Reduzi para 0.1 (melhor para redes profundas com momentum)
            self.parametros['b' + str(l)] = np.zeros((1, camadas[l]))
            
            # Inicializamos a velocidade como Zero
            self.velocidade['W' + str(l)] = np.zeros_like(self.parametros['W' + str(l)])
            self.velocidade['b' + str(l)] = np.zeros_like(self.parametros['b' + str(l)])
            
    def sigmoide(self, z):
        # Proteção contra overflow numérico (para redes maiores)
        return 1 / (1 + np.exp(-np.clip(z, -500, 500)))
    
    def sigmoide_derivada(self, A):
        return A * (1 - A)

    def forward(self, X):
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

    def calcular_custo(self, A_final, Y):
        m = Y.shape[0]
        custo = -1/m * np.sum(Y * np.log(A_final + 1e-8) + (1-Y) * np.log(1 - A_final + 1e-8))
        return np.squeeze(custo)

    def backward(self, Y):
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

    # AQUI ESTÁ A MÁGICA DO MOMENTUM
    def update(self, gradientes, taxa_aprendizado, momentum=0.9):
        for l in range(1, self.L + 1):
            # Física: Velocidade Nova = (Atrito * Vel. Antiga) - (Aceleração do Erro)
            # momentum 0.9 significa que guardamos 90% da velocidade anterior
            
            # Atualiza Velocidade dos Pesos
            self.velocidade['W' + str(l)] = (momentum * self.velocidade['W' + str(l)]) - (taxa_aprendizado * gradientes['dW' + str(l)])
            
            # Atualiza Velocidade do Viés
            self.velocidade['b' + str(l)] = (momentum * self.velocidade['b' + str(l)]) - (taxa_aprendizado * gradientes['db' + str(l)])
            
            # Aplica o movimento
            self.parametros['W' + str(l)] += self.velocidade['W' + str(l)]
            self.parametros['b' + str(l)] += self.velocidade['b' + str(l)]

    def treinar(self, X, Y, epochs, taxa_aprendizado=0.5): # Momentum permite taxas menores ou maiores, vamos testar
        print(f"Treinando rede com arquitetura: {self.camadas} + Momentum")
        for i in range(epochs):
            A_final = self.forward(X)
            custo = self.calcular_custo(A_final, Y)
            gradientes = self.backward(Y)
            
            # Chamamos o update com momentum
            self.update(gradientes, taxa_aprendizado, momentum=0.9)
            
            if i % 1000 == 0:
                print(f"Época {i} - Custo: {custo:.5f}")
        return A_final

# --- 2. PREPARAÇÃO DOS DADOS (VISÃO) ---

print("Carregando imagens de dígitos (8x8)...")
digits = load_digits()

# X = As imagens "achatadas". Eram 8x8, viram vetores de 64 números.
X_orig = digits.data 
# Normalização: Os pixels vão de 0 a 16. Vamos passar para 0 a 1.
# Redes neurais ODEIAM números grandes.
X = X_orig / 16.0 

# Y = Os rótulos (0, 1, 2...). Precisamos do One-Hot Encoding.
y_orig = digits.target.reshape(-1, 1)
encoder = OneHotEncoder(sparse_output=False)
y = encoder.fit_transform(y_orig)

# Dividir em Treino e Teste (Para saber se ela decora ou aprende)
# Usamos 1437 imagens para treinar e 360 para provar que funciona
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

print(f"Formato de Entrada: {X_train.shape} (1437 imagens com 64 pixels)")
print(f"Formato de Saída: {y_train.shape} (1437 rótulos com 10 classes)")

# --- 3. EXECUÇÃO DO EXPERIMENTO ---

# Arquitetura:
# Entrada: 64 (os pixels)
# Oculta 1: 32 (neurônios para achar padrões)
# Oculta 2: 16 (refinamento)
# Saída: 10 (um para cada dígito)
cerebro = RedeNeural(camadas=[64, 32, 16, 10])

print("\nIniciando treinamento visual...")
# Nota: Treinar com imagens é mais pesado. 
# Usamos menos épocas (2000) mas a rede é maior.
cerebro.treinar(X_train, y_train, epochs=3000, taxa_aprendizado=0.5)

# --- 4. A PROVA FINAL (VALIDAÇÃO) ---

print("\n--- Teste com imagens nunca vistas ---")
previsoes = cerebro.forward(X_test)

# Converter de volta de One-Hot para números normais (argmax pega o índice do maior valor)
pred_numeros = np.argmax(previsoes, axis=1)
real_numeros = np.argmax(y_test, axis=1)

# Calcular precisão
acertos = np.sum(pred_numeros == real_numeros)
total = len(real_numeros)
acuracia = acertos / total * 100

print(f"Acurácia no teste: {acuracia:.2f}%")

# Vamos ver alguns exemplos
print("\nExemplos Reais:")
for i in range(5):
    print(f"Imagem {i}: Rede diz {pred_numeros[i]} | Verdade é {real_numeros[i]}")