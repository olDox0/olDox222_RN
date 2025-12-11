"""
NEUROSCOPE v2.0 - Visão Retiniana.
Reconstrói a visão da rede neural formatando os pesos como imagens 8x8.
"""

import pickle
import numpy as np
import os
import sys

# --- CONFIGURAÇÃO VISUAL ---
# Caracteres de intensidade (Espaço = nada, @ = forte ativação)
# Inverti a lógica: espaço é zero, caracteres são intensidade
CHARS_POSITIVOS = " .:+*#@"
CHARS_NEGATIVOS = " .-~=%" # Para inibição (pesos negativos)

def desenhar_retina(pesos_array, titulo):
    """
    Recebe um array de 64 pesos e o desenha como um grid 8x8.
    """
    # Remodelar para 8x8
    grid = pesos_array.reshape(8, 8)
    
    print(f"\n👁️  {titulo}")
    print("   ┌────────┐")
    
    for i in range(8):
        linha_str = "   │"
        for j in range(8):
            val = grid[i, j]
            
            # Lógica de renderização
            if abs(val) < 0.2: # Ruído de fundo, ignora
                char = " "
            elif val > 0: # Excitátorio (Procura isso)
                idx = min(int(val * 2), len(CHARS_POSITIVOS) - 1)
                char = CHARS_POSITIVOS[idx]
            else: # Inibitório (Evita isso)
                idx = min(int(abs(val) * 2), len(CHARS_NEGATIVOS) - 1)
                char = "." # Simplificando negativos para não poluir, ou usar CHARS_NEGATIVOS
                
            linha_str += char
        print(linha_str + "│")
    print("   └────────┘")

def inspecionar_cerebro(arquivo):
    if not os.path.exists(arquivo):
        print(f"❌ Arquivo '{arquivo}' não encontrado.")
        return

    with open(arquivo, 'rb') as f:
        dados = pickle.load(f)
    
    W1 = dados['parametros']['W1']
    # W1 tem formato (64, N_ocultos)
    # Cada COLUNA é um neurônio especialista
    
    n_neuronio_mostrar = min(W1.shape[1], 12) # Vamos ver os 12 primeiros especialistas
    
    print("="*50)
    print("🔬 NEUROSCOPE v2: ANÁLISE DE FILTROS VISUAIS")
    print("="*50)
    print("O que os neurônios da 1ª camada estão procurando?")
    print("Cada quadrado abaixo é o 'foco de atenção' de um neurônio.\n")
    print("Legenda:")
    print(" ' ' (Vazio) = Neurônio ignora essa área")
    print(" '@' (Cheio) = Neurônio ativa forte se tiver tinta aqui")
    print("--------------------------------------------------")

    # Vamos mostrar lado a lado (batches de 4)
    for i in range(0, n_neuronio_mostrar, 4):
        # Pegamos até 4 neurônios
        batch = range(i, min(i+4, n_neuronio_mostrar))
        
        # Cabeçalhos
        header = "   ".join([f"Neurônio {k}".center(10) for k in batch])
        print(f"\n   {header}")
        
        # Topo das caixas
        print("   " + "   ".join(["┌────────┐" for _ in batch]))
        
        # Linhas 0 a 7 da imagem
        for row in range(8):
            line_str = "   "
            for k in batch:
                pesos_neuronio = W1[:, k].reshape(8, 8)
                pixels = ""
                for col in range(8):
                    val = pesos_neuronio[row, col]
                    if abs(val) < 0.25: 
                        char = " " # Limpeza de ruído
                    elif val > 0: 
                        # Escala de intensidade positiva
                        idx = min(int(val * 2.5), len(CHARS_POSITIVOS) - 1)
                        char = CHARS_POSITIVOS[idx]
                    else:
                        # Negativo (Inibição) - vamos representar levemente
                        char = "." 
                    pixels += char
                line_str += f"│{pixels}│   "
            print(line_str)
            
        # Base das caixas
        print("   " + "   ".join(["└────────┘" for _ in batch]))

if __name__ == "__main__":
    inspecionar_cerebro("cerebro_vencedor.pkl")