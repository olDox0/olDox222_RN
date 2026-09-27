"""
DOXOLANG v3.0 (LSTM Engine)
Implementação de Long Short-Term Memory pura em NumPy.
Adiciona 'Portões Lógicos' para controle de fluxo de memória.
"""
import numpy as np
import re

# --- UTILITÁRIOS ---
def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -500, 500)))

def dsigmoid(y):
    return y * (1 - y)

def dtanh(y):
    return 1 - y * y

def softmax(x):
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum(axis=1, keepdims=True)

# --- TOKENIZER (Mantido igual) ---
class Tokenizer:
    def __init__(self):
        self.vocabulario = {} 
        self.inverso = {}     
        self.contador = 0
        self.adicionar_token("<PAD>")
        self.adicionar_token("<UNK>")
    
    def adicionar_token(self, token):
        if token not in self.vocabulario:
            self.vocabulario[token] = self.contador
            self.inverso[self.contador] = token
            self.contador += 1
            
    def treinar(self, textos):
        for texto in textos:
            for t in self._quebrar(texto):
                self.adicionar_token(t)

    def _quebrar(self, texto):
        padrao = r"[\w]+|[=+\-*/(){}:\[\]<>,.!]"
        return re.findall(padrao, texto)

    def converter_para_ids(self, texto):
        tokens = self._quebrar(texto)
        return np.array([self.vocabulario.get(t, 1) for t in tokens])

# --- EMBEDDING (Mantido igual) ---
class CamadaEmbedding:
    def __init__(self, tamanho_vocabulario, dimensao_embedding):
        self.V = tamanho_vocabulario
        self.D = dimensao_embedding
        self.E = np.random.randn(self.V, self.D) * 0.1
        self.ultimo_input = None

    def forward(self, ids):
        self.ultimo_input = ids
        return self.E[ids]

    def backward(self, dY, lr):
        np.add.at(self.E, self.ultimo_input, -lr * dY)

# --- A NOVA CÉLULA LSTM ---
class LSTM:
    def __init__(self, input_size, hidden_size, output_size):
        self.H = hidden_size
        self.I = input_size
        self.O = output_size
        
        # Inicialização Xavier
        std = 1.0 / np.sqrt(hidden_size)
        
        # Pesos (Concatenados para eficiência: Input + Hidden)
        # wf = Forget, wi = Input, wc = Cell Candidate, wo = Output
        self.Wf = np.random.uniform(-std, std, (self.I + self.H, self.H))
        self.Wi = np.random.uniform(-std, std, (self.I + self.H, self.H))
        self.Wc = np.random.uniform(-std, std, (self.I + self.H, self.H))
        self.Wo = np.random.uniform(-std, std, (self.I + self.H, self.H))
        self.Wy = np.random.uniform(-std, std, (self.H, self.O)) # Saída
        
        # Viéses
        self.bf = np.zeros((1, self.H))
        self.bi = np.zeros((1, self.H))
        self.bc = np.zeros((1, self.H))
        self.bo = np.zeros((1, self.H))
        self.by = np.zeros((1, self.O))

    def forward(self, inputs, h_prev=None, c_prev=None):
        if h_prev is None: h_prev = np.zeros((1, self.H))
        if c_prev is None: c_prev = np.zeros((1, self.H))
            
        self.cache = []
        outputs = []
        
        h, c = h_prev, c_prev
        
        for t in range(len(inputs)):
            x = inputs[t].reshape(1, -1)
            
            # Concatenar input e hidden anterior
            concat = np.hstack((x, h))
            
            # 1. Portão de Esquecimento (Lógica: O que apagar?)
            f = sigmoid(np.dot(concat, self.Wf) + self.bf)
            
            # 2. Portão de Entrada (Lógica: O que aprender?)
            i = sigmoid(np.dot(concat, self.Wi) + self.bi)
            
            # 3. Candidato a Memória (O que eu gostaria de guardar?)
            c_bar = np.tanh(np.dot(concat, self.Wc) + self.bc)
            
            # 4. Nova Memória Celular (Física: Mistura do passado e presente)
            c = f * c + i * c_bar
            
            # 5. Portão de Saída (Lógica: O que é relevante agora?)
            o = sigmoid(np.dot(concat, self.Wo) + self.bo)
            
            # 6. Estado Oculto (Memória filtrada para o próximo passo)
            h = o * np.tanh(c)
            
            # 7. Previsão
            y = np.dot(h, self.Wy) + self.by
            
            # Guardar tudo para o backprop
            self.cache.append((x, concat, f, i, c_bar, c, o, h, c_prev))
            outputs.append(y)
            c_prev = c # Atualiza para o próximo loop
            
        return np.array(outputs), h, c

    def backward(self, dY, lr=0.1):
        """
        O Pesadelo Matemático: BPTT na LSTM.
        """
        inputs_len = len(self.cache)
        dInputs = np.zeros((inputs_len, self.I))
        
        # Gradientes acumulados
        dWf, dWi, dWc, dWo, dWy = np.zeros_like(self.Wf), np.zeros_like(self.Wi), np.zeros_like(self.Wc), np.zeros_like(self.Wo), np.zeros_like(self.Wy)
        dbf, dbi, dbc, dbo, dby = np.zeros_like(self.bf), np.zeros_like(self.bi), np.zeros_like(self.bc), np.zeros_like(self.bo), np.zeros_like(self.by)
        
        dh_next = np.zeros((1, self.H))
        dc_next = np.zeros((1, self.H))
        
        for t in reversed(range(inputs_len)):
            dy = dY[t].reshape(1, -1)
            x, concat, f, i, c_bar, c, o, h, c_prev = self.cache[t]
            
            # Gradiente da saída final
            dWy += np.dot(h.T, dy)
            dby += dy
            
            # Gradiente voltando para o Hidden State
            dh = np.dot(dy, self.Wy.T) + dh_next
            
            # Gradiente através do Output Gate
            do = dh * np.tanh(c)
            do_raw = dsigmoid(o) * do
            
            # Gradiente voltando para a Célula de Memória
            dc = dc_next + (dh * o * dtanh(np.tanh(c)))
            
            # Gradiente através da Célula Candidata
            dc_bar = dc * i
            dc_bar_raw = dtanh(c_bar) * dc_bar
            
            # Gradiente através do Input Gate
            di = dc * c_bar
            di_raw = dsigmoid(i) * di
            
            # Gradiente através do Forget Gate
            df = dc * c_prev
            df_raw = dsigmoid(f) * df
            
            # Gradiente para o estado anterior (c_prev)
            dc_next = dc * f
            
            # Acumular gradientes dos pesos
            dWo += np.dot(concat.T, do_raw)
            dbo += do_raw
            dWc += np.dot(concat.T, dc_bar_raw)
            dbc += dc_bar_raw
            dWi += np.dot(concat.T, di_raw)
            dbi += di_raw
            dWf += np.dot(concat.T, df_raw)
            dbf += df_raw
            
            # Gradiente para a entrada (x) e hidden anterior (h_prev)
            d_concat = (np.dot(do_raw, self.Wo.T) + np.dot(dc_bar_raw, self.Wc.T) + 
                        np.dot(di_raw, self.Wi.T) + np.dot(df_raw, self.Wf.T))
            
            # Separa o gradiente do input (x) e do hidden (h)
            dInputs[t] = d_concat[0, :self.I]
            dh_next = d_concat[0, self.I:]
            
        # Clipping para evitar explosão
        for d in [dWf, dWi, dWc, dWo, dWy, dbf, dbi, dbc, dbo, dby, dInputs]:
            np.clip(d, -5, 5, out=d)
            
        # Atualização (Optimizer: Adagrad Simplificado - opcional, aqui usando SGD puro)
        self.Wf -= lr * dWf
        self.Wi -= lr * dWi
        self.Wc -= lr * dWc
        self.Wo -= lr * dWo
        self.Wy -= lr * dWy
        self.bf -= lr * dbf
        self.bi -= lr * dbi
        self.bc -= lr * dbc
        self.bo -= lr * dbo
        self.by -= lr * dby
        
        return dInputs