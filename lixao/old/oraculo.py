"""
ORÁCULO v3.0 (Modular)
Interface de inferência usando Doxonet e Doxovis.
"""
import numpy as np
import random
from sklearn.datasets import load_digits
from doxonet import RedeNeural
from doxovis import desenhar_numero

ARQUIVO_CEREBRO = "cerebro_vencedor.pkl"

def consultar():
    # 1. Carregar
    try:
        ia = RedeNeural.carregar(ARQUIVO_CEREBRO)
    except:
        print("❌ Treine a rede primeiro: 'doxoade run treinar.py'")
        return

    # 2. Pegar dados reais
    digits = load_digits()
    idx = random.randint(0, len(digits.data) - 1)
    
    X_raw = digits.data[idx]
    y_real = digits.target[idx]
    
    # 3. Visualizar
    print(f"\n🔮 Oráculo analisando imagem #{idx}...")
    # Normalizar para desenho e inferência
    X_norm = X_raw / 16.0
    desenhar_numero(X_norm)
    
    # 4. Inferir
    # Formato (1, 64)
    X_input = X_norm.reshape(1, -1)
    probabilidades = ia.forward(X_input).flatten()
    
    previsao = np.argmax(probabilidades)
    confianca = probabilidades[previsao] * 100
    
    # 5. Resultado
    print(f"👁️  Visão da IA: {previsao}")
    print(f"📝 Realidade:    {y_real}")
    print(f"📊 Confiança:    {confianca:.4f}%")
    
    if previsao == y_real:
        print("✅ ACERTOU")
    else:
        print("❌ ERROU")

if __name__ == "__main__":
    consultar()