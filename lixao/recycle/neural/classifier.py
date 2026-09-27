"""
NEURAL CLASSIFIER
Usa a LSTM para entender o propósito de uma função baseada em sua assinatura.
"""
import numpy as np
import pickle
import os
from .core import softmax

BRAIN_PATH = os.path.expanduser("~/.doxoade/cortex.pkl")

# Categorias de Intenção
CATEGORIAS = {
    0: "MATEMATICA",   # Cálculos, Return
    1: "DADOS/IO",     # Arquivos, Banco, Print
    2: "LOGICA",       # Loops, Ifs complexos
    3: "BOILERPLATE",  # Definições vazias, pass
    4: "SEGURANCA"     # Try/Except, asserts
}

class IntentionBrain:
    def __init__(self):
        if not os.path.exists(BRAIN_PATH):
            raise FileNotFoundError("Cérebro não treinado.")
            
        with open(BRAIN_PATH, 'rb') as f:
            model = pickle.load(f)
            
        self.embed = model['embed']
        self.lstm = model['lstm']
        self.tok = model['tokenizer']

    def classify(self, signature_text):
        """
        Recebe a assinatura estrutural (ex: 'DEF LOOP LOGIC_BRANCH')
        Retorna a categoria provável.
        """
        # 1. Converter assinatura em Vetores (Usando o embedding treinado)
        # Nota: O tokenizer precisa conhecer essas palavras-chave. 
        # Se não conhecer, vai dar <UNK>, mas ainda funciona pelo contexto.
        try:
            ids = self.tok.converter_para_ids(signature_text)
        except Exception:
            return "DESCONHECIDO"

        if len(ids) == 0: return "VAZIO"

        # 2. Passar pela LSTM para pegar o 'Sentimento' (Hidden State Final)
        # O vetor 'h' (hidden state) contém o resumo semântico da frase.
        vetores = self.embed.forward(ids)
        _, h_final, _ = self.lstm.forward(vetores)
        
        # 3. Classificação Simplificada (Clustering no vetor H)
        # Como não treinamos uma camada densa final para classificação,
        # vamos usar uma heurística baseada na soma dos pesos ativados.
        # (Em um sistema maior, treinariamos um classificador Softmax aqui)
        
        # Heurística: Projetar H em 5 dimensões (Categorias)
        # Usamos o próprio peso de saída da LSTM (Wy) como projetor
        logits = np.dot(h_final, self.lstm.Wy) # (1, Vocab Size)
        
        # Isso nos dá a probabilidade da próxima palavra.
        # Mas queremos a categoria. Vamos mapear tokens do vocabulario para categorias.
        # Truque: Vamos ver se a rede "pensa" em palavras de matemática ou de IO.
        
        probs = softmax(logits).flatten()
        top_indices = np.argsort(probs)[::-1][:5]
        
        score_math = 0
        score_io = 0
        score_logic = 0
        
        for idx in top_indices:
            word = self.tok.inverso.get(int(idx), "")
            if word in ["+", "-", "*", "/", "return", "val", "x", "y"]: score_math += 1
            if word in ["print", "open", "file", "db", "write"]: score_io += 1
            if word in ["if", "else", "for", "while", "true", "false"]: score_logic += 1
            
        if score_math > score_io and score_math > score_logic: return "MATEMATICA/CALCULO"
        if score_io > score_math and score_io > score_logic: return "IO/DADOS"
        if score_logic > score_math and score_logic > score_io: return "FLUXO/LOGICA"
        
        return "GENERICO"