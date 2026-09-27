"""
ADVERSÁRIO v1.0
Gera exemplos adversariais para enganar a Doxonet.
Técnica: Iterative Gradient Sign Method.
"""
import numpy as np
import pickle
import random
from sklearn.datasets import load_digits
from doxonet import RedeNeural
from doxovis import desenhar_numero

ARQUIVO_CEREBRO = "cerebro_vencedor.pkl"

def gerar_ataque(ia, imagem_original, alvo_falso, passos=50, alpha=0.5):
    """
    Modifica a imagem pixel a pixel para que a IA pense que é o 'alvo_falso'.
    alpha: o quão agressiva é a mudança por passo.
    """
    # Copia a imagem para não estragar a original
    imagem_hackeada = imagem_original.copy()
    
    # Formato para cálculo (1, 64)
    X = imagem_hackeada.reshape(1, -1)
    
    # One-hot do alvo falso (queremos que a rede pense que é ISSO)
    Y_target = np.zeros((1, 10))
    Y_target[0, alvo_falso] = 1
    
    print(f"🔨 Hackeando... Tentando transformar em {alvo_falso}")
    
    for i in range(passos):
        # 1. Forward Pass (O que a rede vê agora?)
        # Precisamos refazer o forward manual para guardar os Zs e As
        # (A classe RedeNeural original guarda o cache, vamos usar isso)
        A_final = ia.forward(X)
        
        predicao_atual = np.argmax(A_final)
        prob = A_final[0][alvo_falso]
        
        if predicao_atual == alvo_falso and prob > 0.9:
            print(f"🔓 Sucesso no passo {i}! A IA foi enganada.")
            break
            
        # 2. Backward Pass (Calcular a sensibilidade)
        # Queremos MINIMIZAR a distância entre a previsão e o ALVO FALSO
        # Então usamos o gradiente normal como se o alvo falso fosse a verdade
        gradientes = ia.backward(Y_target)
        
        # 3. O Pulo do Gato: Backpropagation até os Pixels
        # A classe RedeNeural para em dW1. Nós precisamos de dX (gradiente da entrada).
        # dX = W1 . dZ1
        W1 = ia.parametros['W1']
        dZ1 = np.dot(A_final - Y_target, ia.parametros[f'W{ia.L}'].T) * \
              ia.sigmoide_derivada(ia.cache[f'A{ia.L-1}']) 
              # Nota: Isso é uma aproximação simplificada para Deep Nets, 
              # mas funciona para puxar a imagem na direção certa.
              
        # Recuperando o erro da primeira camada
        # dZ1 (erro na oculta) -> projetado pelos pesos W1 -> dX (erro nos pixels)
        # dZ1 shape: (1, neurônios_ocultos)
        # W1 shape: (64, neurônios_ocultos)
        # Queremos algo shape (1, 64)
        
        # Cálculo manual do gradiente da entrada (dX)
        # Recuperamos o dZ1 real calculado dentro do backward da classe se possível,
        # mas como a classe limpa o cache ou é complexo acessar, vamos usar uma heurística de ataque:
        # Apenas adicionar ruído aleatório guiado pela diferença? Não, vamos ser matemáticos.
        
        # Vamos fazer um "truque" já que não expusemos dX na doxonet.py:
        # Ataque de Força Bruta Direcionada (Random Walk + Check)
        # Se não temos o gradiente exato da entrada, testamos pixels aleatórios
        # e mantemos se a probabilidade do alvo subir.
        
        # --- MÉTODO ALTERNATIVO: Pixel Jittering (funciona sem dX explícito) ---
        melhor_X = X.copy()
        melhor_prob = prob
        
        # Tenta mudar pixels aleatórios
        ruido = np.random.randn(1, 64) * alpha
        X_teste = X - ruido # Subtrair ruído aleatório as vezes ajuda a escapar de mínimos
        
        # Mas o ideal é Gradient Ascent. Vamos implementar o cálculo real de dX aqui fora.
        # Recalculando dZ1 corretamente:
        dZ_last = A_final - Y_target # Erro na saída
        # Propagando para trás camada por camada até a entrada
        dZ_curr = dZ_last
        for l in range(ia.L, 0, -1):
            W = ia.parametros[f'W{l}']
            b = ia.parametros[f'b{l}']
            A_prev = ia.cache[f'A{l-1}'] # A0 é o X (input)
            
            if l > 1:
                dA_prev = np.dot(dZ_curr, W.T)
                dZ_prev = dA_prev * ia.sigmoide_derivada(A_prev)
                dZ_curr = dZ_prev
            else:
                # Chegamos na camada 1. O input é X.
                # O gradiente em relação a X é dZ1 * W1.T
                dX = np.dot(dZ_curr, W.T)
        
        # 4. Atualizar a Imagem (Gradient Descent no Input)
        # Queremos que a imagem se pareça com o alvo, então movemos X na direção oposta ao erro.
        # X_novo = X - (taxa * dX)
        X = X - (alpha * dX)
        
        # Clipar para manter imagem válida (não pode ter pixel -50 ou +50)
        X = np.clip(X, 0, 1.0) # Assumindo normalização 0-1
        
    return X.reshape(64,)

def executar_sabotagem():
    # 1. Carregar
    try:
        ia = RedeNeural.carregar(ARQUIVO_CEREBRO)
    except:
        return

    # 2. Pegar vítima
    digits = load_digits()
    idx = random.randint(0, len(digits.data) - 1)
    X_original = digits.data[idx] / 16.0
    y_real = digits.target[idx]
    
    print(f"\n🎯 Vítima selecionada: Imagem #{idx} (É um '{y_real}')")
    desenhar_numero(X_original)
    
    # Escolher um alvo diferente
    alvos = list(range(10))
    alvos.remove(y_real)
    alvo_falso = random.choice(alvos)
    
    print(f"\n🕵️  Iniciando ataque... Objetivo: Fazer a IA pensar que é um '{alvo_falso}'")
    
    # 3. Executar Ataque
    X_fake = gerar_ataque(ia, X_original, alvo_falso, passos=2000, alpha=0.05)
    
    # 4. Resultado
    print("\n" + "="*40)
    print("RESULTADO DA SABOTAGEM")
    print("="*40)
    
    print("\n1. Como a imagem ficou (Visual Humano):")
    desenhar_numero(X_fake)
    
    print("\n2. O que a IA diz (Visual Máquina):")
    X_input = X_fake.reshape(1, -1)
    prob = ia.forward(X_input).flatten()
    pred = np.argmax(prob)
    conf = prob[pred] * 100
    
    print(f"👁️  Previsão: {pred}")
    print(f"📊 Confiança: {conf:.4f}%")
    
    if pred == alvo_falso:
        print("\n✅ HACK BEM SUCEDIDO! A IA está alucinando.")
    elif pred == y_real:
        print("\n🛡️  FALHA NO ATAQUE. A IA resistiu.")
    else:
        print(f"\n⚠️  RESULTADO IMPREVISTO. Virou um {pred}.")

if __name__ == "__main__":
    executar_sabotagem()