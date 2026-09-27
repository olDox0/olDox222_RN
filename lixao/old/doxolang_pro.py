"""
DOXOLANG PRO (Continuous Learning)
Treina a LSTM com fluxo infinito de código sintético.
"""
import numpy as np
import pickle
import time
import random
from doxolang import Tokenizer, CamadaEmbedding, LSTM, softmax
from codex_gen import gerar_funcao_simples, obter_vocabulario_completo
from doxovis import cabecalho, info, sucesso, erro

ARQUIVO_MODELO = "cerebro_codex.pkl"

def treinar_generalista():
    cabecalho("TREINAMENTO DE SINTAXE PYTHON")
    
    # 1. Preparar Tokenizer com TODO o vocabulário possível
    tok = Tokenizer()
    vocab_base = obter_vocabulario_completo()
    # Adicionamos manualmente para garantir ordem e completude
    for v in vocab_base:
        tok.adicionar_token(v)
        
    info(f"Vocabulário total: {tok.contador} tokens.")
    
    # 2. Arquitetura
    EMBED_DIM = 24       # Aumentado para lidar com mais variedade
    HIDDEN_SIZE = 128    # Memória muito maior para entender contexto de variáveis
    
    embed = CamadaEmbedding(tok.contador, EMBED_DIM)
    lstm = LSTM(input_size=EMBED_DIM, hidden_size=HIDDEN_SIZE, output_size=tok.contador)
    
    # Hiperparâmetros
    lr = 0.1
    epochs = 5000 # Treino longo pois os dados mudam sempre
    
    print("\n   [Iniciando Fluxo de Dados Infinito]")
    media_loss = 0
    start = time.time()
    
    for epoch in range(epochs):
        # A CADA ÉPOCA, UM CÓDIGO NOVO!
        dados = gerar_funcao_simples()
        ids = tok.converter_para_ids(dados)
        
        input_ids = ids[:-1]
        target_ids = ids[1:]
        
        # Forward
        vetores = embed.forward(input_ids)
        logits, _, _ = lstm.forward(vetores)
        probs = softmax(logits.reshape(len(input_ids), tok.contador))
        
        # Loss
        loss = 0
        dY = probs.copy()
        for t, target in enumerate(target_ids):
            loss += -np.log(probs[t][target] + 1e-8)
            dY[t][target] -= 1
        loss /= len(input_ids)
        
        # Backward
        dInputs = lstm.backward(dY, lr=lr)
        embed.backward(dInputs, lr=lr)
        
        # Smooth Loss para visualização
        if epoch == 0: media_loss = loss
        else: media_loss = 0.99 * media_loss + 0.01 * loss
        
        # Feedback e Ajuste de LR
        if epoch % 500 == 0:
            print(f"   Epoca {epoch}: Erro Médio = {media_loss:.4f} | Ex: {dados}")
            
        if epoch == 2000: lr = 0.05
        if epoch == 4000: lr = 0.01
            
    tempo = time.time() - start
    sucesso(f"Treino finalizado em {tempo:.2f}s. Erro estabilizado em: {media_loss:.4f}")
    
    modelo = {"embed": embed, "lstm": lstm, "tokenizer": tok}
    with open(ARQUIVO_MODELO, 'wb') as f:
        pickle.dump(modelo, f)
    sucesso(f"Cérebro salvo em '{ARQUIVO_MODELO}'")

def completar_codigo():
    try:
        with open(ARQUIVO_MODELO, 'rb') as f:
            modelo = pickle.load(f)
    except:
        erro("Modelo não encontrado.")
        return
        
    embed, lstm, tok = modelo["embed"], modelo["lstm"], modelo["tokenizer"]
    
    cabecalho("AUTO-COMPLETE INTELIGENTE")
    print("   Escreva o início de uma função.")
    print("   Ex: 'def mult', 'def f1 ( x', 'def calc ( a , b ) : return'")
    
    prompt = input("\n   >> Código: ")
    if not prompt: return
    
    try:
        input_ids = tok.converter_para_ids(prompt)
    except:
        erro("Uso de palavras fora do vocabulário controlado.")
        return

    curr_id = input_ids[0]
    h, c = None, None
    texto = [tok.inverso.get(curr_id)]
    
    # Processar o que o usuário digitou (Aquecer memória)
    for next_id in input_ids[1:]:
        x = embed.forward(np.array([curr_id]))
        _, h, c = lstm.forward(x, h_prev=h, c_prev=c)
        curr_id = next_id
        texto.append(tok.inverso.get(curr_id))
        
    print(f"\n   {' '.join(texto)}", end=" ", flush=True)
    
    # A IA tenta terminar
    for _ in range(10):
        time.sleep(0.05)
        x = embed.forward(np.array([curr_id]))
        out, h, c = lstm.forward(x, h_prev=h, c_prev=c)
        
        # Sampling com temperatura baixa (para ser mais preciso)
        pred_id = np.argmax(out[0])
        palavra = tok.inverso.get(pred_id, "?")
        
        print(f"{palavra}", end=" ", flush=True)
        texto.append(palavra)
        curr_id = pred_id
        
        if len(texto) > 12: break # Segurança
        
    print("\n")

if __name__ == "__main__":
    # Menu rápido
    print("1. Treinar (Code Understanding)")
    print("2. Testar")
    opt = input(">> ")
    if opt == '1': treinar_generalista()
    elif opt == '2': completar_codigo()