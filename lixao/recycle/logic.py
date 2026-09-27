# -*- coding: utf-8 -*-
"""
Arquiteto Lógico v20.0 (Chief-Gold Edition).
Monitor Neuro-Simbólico para validação de sintaxe e rastreio de dependências.
Em conformidade com PASC-9 (Resgate de Poder) e MPoT-5.
"""

#import logging

class ArquitetoLogico:
    """
    Sistema 2 (Crítico): Valida a estrutura lógica gerada pela rede neural.
    Garante que a 'criatividade' estatística não viole regras sintáticas.
    """
    def __init__(self):
        self.memoria_variaveis = set()
        self.variaveis_usadas = set() # Resgatado do histórico (PASC-9)
        self.pilha_parenteses = 0 
        self.estado = "INICIO" # nosec
        self.ultimo_token = "" # nosec
        self.assinatura_concluida = False
        self.min_args = 0
        
        self.pontuacao = ["(", ")", ":", ",", "."]
        self.keywords = ["def", "return", "if", "else", "with", "open", "as", "pass", "import"]
        
    def reset(self):
        """Reinicializa o estado do autômato para uma nova análise."""
        self.__init__()

    def set_constraints(self, min_args: int = 0):
        """
        Define restrições dinâmicas para a função atual.
        Resgatado conforme PASC-9 para suportar validação de assinaturas.
        """
        if not isinstance(min_args, int):
            raise TypeError("min_args deve ser um inteiro.")
        self.min_args = min_args

    def observar(self, token: str):
        """
        Atualiza a máquina de estados baseada no fluxo de tokens recebido.
        Implementa a percepção estrutural do System 2.
        """
        if token is None:
            raise ValueError("observar: str 'token' não pode ser None.")
        if not token: return
        token = token.strip()
        
        # Atualiza estado baseado em keywords
        if token == "def": # nosec
            self.estado = "NOME"
            self.assinatura_concluida = False
        
        # Rastreio de variáveis no corpo
        if self.estado == "CORPO" and token.isidentifier() and token not in self.keywords:
            self.variaveis_usadas.add(token)
        
        # Processa caracteres estruturais
        for char in token:
            if char == "(": # nosec
                self.pilha_parenteses += 1
                if self.estado in ["NOME", "ARGS_PRE"]: self.estado = "ARGS"
            elif char == ")": # nosec
                if self.pilha_parenteses > 0: self.pilha_parenteses -= 1
                if self.pilha_parenteses == 0 and self.estado == "ARGS": 
                    self.estado = "TRANSICAO" 
            elif char == ":": # nosec
                if self.estado == "TRANSICAO": 
                    self.estado = "CORPO"
                    self.assinatura_concluida = True

        self.ultimo_token = token

    def validar(self, token: str):
        """
        Aplica as regras de inibição do MPoT e PEP8.
        Retorna: (bool, str) -> (Sucesso, Mensagem de Erro).
        """
        # MPoT-5: Contrato de Entrada
        if not isinstance(token, str):
            raise TypeError("O validador exige um token em formato string.")

        token = token.strip()
        if not token: return True, "Espaço"

        # 1. Proteção de NOME
        if self.estado == "NOME":
            if not token.isidentifier() and "(" not in token:
                return False, "Nome de função inválido para Python."
            if any(c in ":.," for c in token):
                return False, "Símbolos proibidos no identificador."

        # 2. Proteção de ARGS (Anti-Gagueira)
        if self.estado == "ARGS":
            if token in self.keywords: return False, "Uso proibido de keyword em argumento."
            
            # Rastreia variáveis definidas para o M2A2
            if token.isidentifier():
                self.memoria_variaveis.add(token)
            
            last_was_var = self.ultimo_token.isidentifier() and self.ultimo_token not in self.keywords
            if last_was_var:
                if token.isidentifier():
                    return False, "BLOQUEIO: Variável duplicada (Esperando ',' ou ')')"
                if token not in [",", ")"]:
                    return False, "Esperando separador de argumentos."

        # 3. Proteção de Transição
        if self.estado == "TRANSICAO":
            if ":" not in token: return False, "Esperando ':' para iniciar o bloco."

        # 4. Proteção de Corpo
        if self.estado == "CORPO":
            if self.ultimo_token == ":" or self.ultimo_token.endswith(":"):
                if token in [".", ",", ")", "]", "}"] or token == "(":
                     return False, "Início de bloco indentado inválido."

        return True, "OK"

    def variaveis_pendentes(self) -> set:
        """Retorna o conjunto de variáveis declaradas mas não utilizadas no corpo."""
        return self.memoria_variaveis - self.variaveis_usadas

    def sugerir_correcao(self):
        """Sugere o próximo token estrutural em caso de travamento do gerador."""
        if self.estado == "ARGS_PRE": return "("
        if self.estado == "TRANSICAO": return ":"
        
        if self.estado == "ARGS":
            if self.ultimo_token.isidentifier() and self.ultimo_token not in self.keywords:
                return ")" # Força o fechamento para salvar a sintaxe
            
        if self.estado == "CORPO" and (self.ultimo_token == ":" or self.ultimo_token.endswith(":")):
            return "pass" 
            
        return None