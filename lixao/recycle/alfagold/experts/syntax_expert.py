# alfagold/experts/syntax_expert.py
import numpy as np

class SyntaxExpert:
    """
    Syntax Expert v23.0 (Variable Boost).
    Incentiva identificadores em ARGS e bloqueia aspas explicitamente.
    """
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        self.vocab_size = len(tokenizer.vocab)
        self.memoria_variaveis = set()
        self.pilha_parenteses = 0 
        self.estado = "INICIO" 
        self.ultimo_token = ""
        self.assinatura_concluida = False
        
        self.ids = self._map_structural_tokens()
        self.keywords = ["def", "return", "if", "else", "with", "open", "as", "pass", "import"]

    def _map_structural_tokens(self):
        target_chars = {"(": "open", ")": "close", ":": "colon", ",": "comma", " ": "space"}
        mapped = {v: -1 for v in target_chars.values()}
        for char, name in target_chars.items():
            ids = self.tokenizer.encode(char)
            if ids: mapped[name] = ids[0]
        return mapped

    def reset(self):
        self.__init__(self.tokenizer)

    def observe(self, token_str):
        self.observar(token_str)

    def observar(self, token):
        token = token.strip()
        if not token: return
        self.ultimo_token = token
        
        if token == "def": 
            self.estado = "NOME"
            self.assinatura_concluida = False
            self.pilha_parenteses = 0
            return

        if self.estado == "NOME" and token.isidentifier() and token not in self.keywords:
            self.estado = "ARGS_PRE"
            
        for char in token:
            if char == "(": 
                self.pilha_parenteses += 1
                if self.estado in ["NOME", "ARGS_PRE"]: self.estado = "ARGS"
            elif char == ")": 
                if self.pilha_parenteses > 0: self.pilha_parenteses -= 1
                if self.pilha_parenteses == 0 and self.estado == "ARGS": 
                    self.estado = "TRANSICAO" 
            elif char == ":": 
                if self.estado == "TRANSICAO": 
                    self.estado = "CORPO"
                    self.assinatura_concluida = True
                    
        if self.estado == "ARGS" and token.isidentifier() and token not in self.keywords:
            self.memoria_variaveis.add(token)

    def get_inhibition_mask(self, current_logits_shape):
        mask = np.zeros(current_logits_shape, dtype=np.float32)
        i_open, i_colon, i_close = self.ids['open'], self.ids['colon'], self.ids['close']
        if i_open == -1: return mask

        # Assinatura
        if self.estado == "ARGS_PRE":
            mask[:] = -2000.0; mask[i_open] = 2000.0 
        elif self.estado == "TRANSICAO":
            mask[:] = -2000.0; mask[self.ids['colon']] = 2000.0
        elif self.estado == "NOME":
            mask[self.ids['colon']] = -1000.0; mask[i_open] = 100.0 

        # ARGS: Bloqueio + Incentivo
        elif self.estado == "ARGS":
            proibidos = [".", ":", ";", "{", "}", "[", "]", "=", "<", ">", "'", '"'] + self.keywords
            
            vocab = self.tokenizer.vocab
            for token_str, token_id in vocab.items():
                if token_id >= len(mask): continue
                
                clean = token_str.replace(' ', '').replace('Ġ', '').strip()
                
                # Bloqueio
                if any(p in clean for p in proibidos):
                    mask[token_id] = -2000.0
                
                # [NOVO] Boost em Variáveis
                # Se for identificador puro e não keyword, ajuda o modelo a escolher
                elif clean.isidentifier() and clean not in self.keywords:
                    mask[token_id] += 5.0

            # Se já temos variáveis, encoraja fechar
            if self.memoria_variaveis:
                mask[i_close] += 50.0

        return mask

    def validar(self, token):
        token = token.strip()
        if not token: return True, "Espaço"

        if not self.assinatura_concluida:
            if self.estado == "NOME":
                if not token.isidentifier(): return False, "Nome inválido"
                if token in self.keywords: return False, "Keyword como nome"
            if self.estado == "ARGS_PRE" and "(" not in token: return False, "Esperando '('"
            if self.estado == "TRANSICAO" and ":" not in token: return False, "Esperando ':'"

        if self.estado == "ARGS":
            if any(x in token for x in ["open", "with", "print", "'", '"']): return False, "Inválido em args"
            last_was_var = self.ultimo_token.isidentifier() and self.ultimo_token not in self.keywords
            if last_was_var and token.isidentifier(): return False, "Variáveis adjacentes"

        if self.estado == "CORPO":
            if self.ultimo_token.endswith(":") and token in [".", ",", ")", "]", "}"]: return False, "Início inválido"
            if self.ultimo_token == "with" and "open" not in token: return False, "Esperando 'open'"

        return True, "OK"

    def sugerir_correcao(self):
        if self.estado == "ARGS_PRE": return "("
        if self.estado == "TRANSICAO": return ":"
        if self.estado == "ARGS" and self.ultimo_token.isidentifier(): return ")" 
        if self.estado == "CORPO" and self.ultimo_token.endswith(":"): return "with"
        if self.estado == "CORPO" and self.ultimo_token == "with": return "open"
        return None