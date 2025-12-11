"""
LABORATÓRIO DE TREINAMENTO v2.0
"""
import numpy as np
import random
from sklearn.datasets import load_digits
from sklearn.preprocessing import OneHotEncoder
from sklearn.model_selection import train_test_split
from doxonet import RedeNeural
from doxovis import desenhar_grafico_custo, cabecalho, info, sucesso, erro

# 1. Configuração
ARQUIVO_CEREBRO = "cerebro_vencedor.pkl"
MUTANTES = 5
EPOCHS_FINAL = 5000 # Podemos aumentar pois o Early Stopping vai parar quando necessário
PACIENCIA = 500     # Se ficar 500 épocas sem melhorar, para.

# 2. Dados
cabecalho("PREPARANDO LABORATÓRIO")
digits = load_digits()
X = digits.data / 16.0 
encoder = OneHotEncoder(sparse_output=False)
y = encoder.fit_transform(digits.target.reshape(-1, 1))
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
info(f"Dados carregados: {len(X_train)} amostras de treino.")

# 3. Evolução
def criar_mutante():
    h1 = random.randint(30, 90)
    h2 = random.choice([None, random.randint(20, 50)])
    camadas = [64, h1, h2, 10] if h2 else [64, h1, 10]
    return camadas, random.choice([0.1, 0.5, 1.0]), random.choice([0.0, 0.001])

cabecalho(f"SELEÇÃO NATURAL: {MUTANTES} ESPÉCIMES")
melhor_acc = 0
melhor_config = {}
melhor_rede = None # type: ignore

for i in range(MUTANTES):
    camadas, lr, decay = criar_mutante()
    print(f"   🧬 Mutante {i+1}: {camadas} | LR={lr} | Decay={decay}")
    
    try:
        rede = RedeNeural(camadas)
        # Treino rápido de seleção
        acc, _ = rede.treinar(X_train, y_train, X_test, y_test, epochs=600, taxa_aprendizado=lr, decay=decay, paciencia=200)
        
        if acc > melhor_acc:
            melhor_acc = acc
            melhor_config = {'camadas': camadas, 'lr': lr, 'decay': decay}
            melhor_rede = rede
            sucesso(f"   -> NOVO LÍDER ({acc*100:.2f}%) 🏆")
    except Exception as e:
        erro(f"   -> Falha: {e}")

# 4. Treino Final
cabecalho(f"TREINAMENTO DE ELITE")
info(f"Configuração Vencedora: {melhor_config}")

acc_final, hist = melhor_rede.treinar(X_train, y_train, X_test, y_test, 
                                      epochs=EPOCHS_FINAL, 
                                      taxa_aprendizado=melhor_config['lr'], 
                                      decay=melhor_config['decay'], 
                                      paciencia=PACIENCIA, # Usa a paciência aqui
                                      verbose=True)

sucesso(f"Acurácia Final: {acc_final*100:.2f}%")
desenhar_grafico_custo(hist)

melhor_rede.salvar(ARQUIVO_CEREBRO)