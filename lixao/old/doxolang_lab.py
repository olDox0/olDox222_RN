"""
DOXOLANG LAB v2.0 (LSTM)
Treinamento com Lógica Temporal.
"""
import numpy as np
import pickle
import os
import time
from doxolang import Tokenizer, CamadaEmbedding, LSTM, softmax
from doxovis import cabecalho, info, sucesso, erro

ARQUIVO_MODELO = "cerebro_logos.pkl"

def treinar_novo_modelo():
    # Dados de treino (Mais complexos para provar a lógica)
    dados = "def soma ( a , b ) : return a + b"
    cabecalho("TREINANDO DOXOLANG (LSTM)")
    info(f"Dataset: '{dados}'")

    tok = Tokenizer()
    tok.treinar([dados])
    ids = tok.converter_para_ids(dados)
    
    # Arquitetura LSTM
    EMBED_DIM = 16
    HIDDEN_SIZE = 64 # Memória robusta
    embed = CamadaEmbedding(tok.contador, EMBED_DIM)
    
    # Usando a nova classe LSTM em vez de RNN
    lstm = LSTM(input_size=EMBED_DIM, hidden_size=HIDDEN_SIZE, output_size=tok.contador)
    
    input_ids = ids[:-1]
    target_ids = ids[1:]
    
    print("\n   [Progresso do Treino]")
    start = time.time()
    
    # Otimização: Learning Rate Decay manual
    lr = 0.5 
    
    for epoch in range(1500):
        # Forward
        vetores = embed.forward(input_ids)
        logits, _, _ = lstm.forward(vetores) # LSTM retorna 3 valores
        
        probs = softmax(logits.reshape(len(input_ids), tok.contador))
        
        loss = 0
        dY = probs.copy()
        for t, target in enumerate(target_ids):
            loss += -np.log(probs[t][target] + 1e-8)
            dY[t][target] -= 1
        loss /= len(input_ids)
        
        # Backward
        dInputs = lstm.backward(dY, lr=lr)
        embed.backward(dInputs, lr=lr)
        
        if epoch % 100 == 0:
            print(f"   Epoca {epoch}: Erro = {loss:.4f}")
            if loss < 0.05: break # Parar se aprendeu
        
        # Reduzir LR se estiver travado
        if epoch == 800: lr = 0.1
            
    tempo = time.time() - start
    sucesso(f"Treino concluído em {tempo:.2f}s. Erro final: {loss:.4f}")
    
    modelo = {"embed": embed, "lstm": lstm, "tokenizer": tok}
    with open(ARQUIVO_MODELO, 'wb') as f:
        pickle.dump(modelo, f)
    sucesso(f"Modelo salvo em '{ARQUIVO_MODELO}'")

def gerar_codigo():
    if not os.path.exists(ARQUIVO_MODELO):
        erro("Modelo não encontrado.")
        return

    with open(ARQUIVO_MODELO, 'rb') as f:
        modelo = pickle.load(f)
    
    embed = modelo["embed"]
    lstm = modelo["lstm"] # Agora é LSTM
    tok = modelo["tokenizer"]
    
    cabecalho("GERADOR DE CÓDIGO (LSTM)")
    prompt = input("   Digite o início (ex: 'def'): ")
    if not prompt: prompt = "def"
    
    try:
        input_ids = tok.converter_para_ids(prompt)
    except:
        erro("Token desconhecido.")
        return

    curr_id = input_ids[0]
    h, c = None, None # Estados da LSTM
    texto_gerado = [tok.inverso.get(curr_id, "?")]
    
    # Aquecimento
    for next_id in input_ids[1:]:
        x = embed.forward(np.array([curr_id]))
        _, h, c = lstm.forward(x, h_prev=h, c_prev=c)
        curr_id = next_id
        texto_gerado.append(tok.inverso.get(curr_id, "?"))
        
    print(f"\n   Prompt: {' '.join(texto_gerado)}", end=" ", flush=True)
    
    # Geração
    for _ in range(15):
        time.sleep(0.1)
        x = embed.forward(np.array([curr_id]))
        out, h, c = lstm.forward(x, h_prev=h, c_prev=c)
        
        pred_id = np.argmax(out[0])
        palavra = tok.inverso.get(pred_id, "?")
        
        print(f"{palavra}", end=" ", flush=True)
        texto_gerado.append(palavra)
        curr_id = pred_id
        
        if palavra == "b" and len(texto_gerado) > 10: break # Evitar loop infinito se houver
        
    print("\n")
    sucesso("Lógica concluída.")

if __name__ == "__main__":
    treinar_novo_modelo()