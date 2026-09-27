"""
DOXOLOGIC v3.0 - The Architect (Hierarchical Constraint System).
Implementa Autômatos de Pilha para garantir sintaxe perfeita.
"""
import pickle
import numpy as np
import time
import os
from doxovis import cabecalho, info, sucesso, erro, alerta

ARQUIVO_MODELO = "cerebro_codex.pkl"

class ArquitetoLogico:
    def __init__(self):
        self.memoria_variaveis = set()
        self.pilha_parenteses = 0 # 0 = Balanceado, >0 = Devendo fechamento
        self.estado = "DEF" # Estados: DEF, NOME, ARGS, CORPO, RETORNO, FIM
        self.ultimo_token = ""
        
    def observar(self, token):
        """Atualiza o estado da máquina baseado no que foi escrito."""
        self.ultimo_token = token
        
        # Gestão de Variáveis
        if self.estado == "ARGS" and token.isalnum() and token != "def":
            self.memoria_variaveis.add(token)
            
        # Gestão de Estados Macro
        if token == "def": self.estado = "NOME"
        elif self.estado == "NOME" and token not in ["(", "def"]: self.estado = "ARGS_PRE"
        elif token == "(": 
            self.estado = "ARGS"
            self.pilha_parenteses += 1
        elif token == ")": 
            self.pilha_parenteses -= 1
            if self.pilha_parenteses == 0 and self.estado == "ARGS":
                self.estado = "TRANSICAO" # Esperando os dois pontos :
        elif token == ":": self.estado = "CORPO"
        elif token == "return": self.estado = "RETORNO"
        
    def validar(self, token, fim_provavel=False):
        """
        O Juiz Supremo. Retorna (True/False, Motivo).
        """
        is_op = token in ["+", "-", "*", "/", "%"]
        is_var = token in self.memoria_variaveis
        is_num = token.isalnum() and not is_var and token not in ["def", "return"]
        
        # 1. Regra da Pilha (Parenteses)
        if token == "(":
            # Não pode abrir parenteses logo depois de fechar ou de variavel (em python simples)
            if self.ultimo_token == ")": return False, "Sintaxe inválida: )("
            if self.ultimo_token.isalnum() and self.ultimo_token not in ["if", "while", "return", "def"]: return False, "Chamada de função não suportada ainda"
        
        if token == ")":
            if self.pilha_parenteses <= 0: return False, "Não há o que fechar"
            if self.ultimo_token in ["(", ",", "+", "-", "*", "/"]: return False, "Fechamento prematuro"

        # 2. Regra da Transição (:)
        if token == ":":
            if self.pilha_parenteses > 0: return False, "Parenteses abertos"
            if self.estado != "TRANSICAO": return False, "Lugar errado para :"

        # 3. Regra do Retorno
        if token == "return":
            if self.estado != "CORPO": return False, "Return fora do corpo"
        
        # 4. Regra de Operadores (Não pode terminar com + ou começar expressão com *)
        if is_op:
            if self.ultimo_token in ["(", "return", ",", "def", ":"]: return False, "Operador sem operando esquerdo"
            if self.ultimo_token in ["+", "-", "*", "/", "%"]: return False, "Operador duplicado"

        # 5. Regra de Variáveis (A mais importante!)
        if self.estado in ["CORPO", "RETORNO"] and token.isalnum():
            if token not in ["return", "def"]:
                # Se não é keyword, TEM que ser variável conhecida
                if not is_var: return False, f"Alucinação: {token} desconhecido"

        # 6. Regra de Fim de Ciclo (Anti-Loop)
        # Se a rede tentar continuar escrevendo depois de uma expressão válida no return
        if self.estado == "RETORNO" and fim_provavel:
            # Se já temos "return a + b", e a rede quer mandar um "/", permitimos.
            # Mas se ela quer mandar "return", bloqueia.
            pass

        return True, "OK"

def raciocinar():
    if not os.path.exists(ARQUIVO_MODELO):
        erro("Cérebro não encontrado.")
        return

    with open(ARQUIVO_MODELO, 'rb') as f:
        modelo = pickle.load(f)
    
    embed, lstm, tok = modelo["embed"], modelo["lstm"], modelo["tokenizer"]
    arquiteto = ArquitetoLogico()
    
    cabecalho("RACIOCÍNIO ESTRUTURADO (STACK MACHINE)")
    print("   O Arquiteto impõe regras gramaticais estritas.\n")
    
    prompt = input("   Defina (ex: 'def soma'): ")
    if not prompt: prompt = "def"
    
    try:
        input_ids = tok.converter_para_ids(prompt)
    except:
        erro("Erro de tokenização.")
        return

    curr_id = input_ids[0]
    h, c = None, None
    texto_final = []
    
    # --- FASE 1: ABSORÇÃO ---
    for id_val in input_ids:
        palavra = tok.inverso.get(id_val)
        texto_final.append(palavra)
        arquiteto.observar(palavra)
        
        x = embed.forward(np.array([curr_id]))
        _, h, c = lstm.forward(x, h_prev=h, c_prev=c)
        curr_id = id_val

    print(f"\n   Pensando: {' '.join(texto_final)}", end=" ", flush=True)

    # --- FASE 2: CONSTRUÇÃO ---
    for _ in range(30): # Limite máximo de tokens
        time.sleep(0.05)
        
        # A. Intuição
        x = embed.forward(np.array([curr_id]))
        out, h_next, c_next = lstm.forward(x, h_prev=h, c_prev=c)
        probs = out[0].flatten()
        
        # B. Raciocínio (Top 10 para ter mais opções válidas)
        top_indices = np.argsort(probs)[::-1][:10]
        decisao_final = None
        
        for idx in top_indices:
            idx = int(idx)
            candidato = tok.inverso.get(idx, "?")
            
            # Pergunta ao Arquiteto
            aprovado, motivo = arquiteto.validar(candidato)
            
            if aprovado:
                decisao_final = idx
                break
        
        # C. Intervenção de Crise (Se a rede travou)
        if decisao_final is None:
            # O Arquiteto assume o controle
            if arquiteto.estado == "ARGS":
                sugestao = "," 
            elif arquiteto.estado == "TRANSICAO":
                sugestao = ":"
            elif arquiteto.estado == "CORPO":
                sugestao = "return"
            elif arquiteto.estado == "RETORNO":
                 # Se travou no retorno, tenta fechar a conta
                 if list(arquiteto.memoria_variaveis):
                     sugestao = list(arquiteto.memoria_variaveis)[0]
                 else:
                     break # Abortar
            else:
                break
            
            decisao_final = tok.vocabulario.get(sugestao)
            # print(f"[{sugestao}]", end="") # Debug da intervenção
            
        # D. Execução
        palavra_escolhida = tok.inverso.get(decisao_final, "?")
        
        # CRITÉRIO DE PARADA INTELIGENTE
        # Se estamos no retorno, temos uma variavel/numero, e a rede quer parar ou a pilha ta vazia
        # Simplesmente paramos de gerar se a estrutura parece completa.
        if arquiteto.estado == "RETORNO" and palavra_escolhida.isalnum():
            # Verifica probabilidade de fim
            # Se a rede quer gerar <PAD> ou <UNK> ou algo invalido a seguir, paramos.
            pass

        arquiteto.observar(palavra_escolhida)
        
        h, c = h_next, c_next
        curr_id = decisao_final
        texto_final.append(palavra_escolhida)
        
        print(f"{palavra_escolhida}", end=" ", flush=True)
        
        # Parada forçada se a expressão ficou longa demais e válida
        if arquiteto.estado == "RETORNO" and len(texto_final) > 15:
             # Heurística: se o ultimo foi variavel, pode parar
             if palavra_escolhida.isalnum(): break

    print("\n")
    if arquiteto.memoria_variaveis:
        info(f"Variáveis Detectadas: {arquiteto.memoria_variaveis}")
    if arquiteto.pilha_parenteses == 0:
        sucesso("Sintaxe Balanceada.")
    else:
        alerta("Aviso: Parenteses não fechados.")

if __name__ == "__main__":
    raciocinar()