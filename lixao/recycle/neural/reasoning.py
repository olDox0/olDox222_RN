"""
SHERLOCK v5.1 (Semantic Update).
Adiciona compreensão do conceito de 'total' e 'result'.
"""
# [DOX-UNUSED] import numpy as np
import os
import json
import re

MEMORY_FILE = ".doxoade_bayes.json"

class Sherlock:
    def __init__(self):
        self.beliefs = {
            # Soma / Adição
            "soma": {"+": 0.9, "*": 0.05, "-": 0.05},
            "add":  {"+": 0.9, "*": 0.05, "-": 0.05},
            "adição": {"+": 0.95, "*": 0.02, "-": 0.02},
            "adicionar": {"+": 0.95, "*": 0.02, "-": 0.02},
            "total": {"+": 0.95}, # NOVO: Total geralmente é soma
            
            # Subtração
            "sub":  {"-": 0.9, "+": 0.05, "/": 0.05},
            "menos": {"-": 0.95, "+": 0.02},
            "subtração": {"-": 0.95, "+": 0.02},
            "diferença": {"-": 0.95},
            
            # Multiplicação
            "mult": {"*": 0.9, "+": 0.1},
            "vezes": {"*": 0.95},
            "multiplicação": {"*": 0.95},
            "produto": {"*": 0.95},
            
            # Divisão
            "div":  {"/": 0.9, "%": 0.1},
            "divisão": {"/": 0.95},
            
            # Lógica
            "maior": {">": 0.8, ">=": 0.2},
            "menor": {"<": 0.8, "<=": 0.2},
            "igual": {"==": 0.9},
            
            "generic": {"+": 0.25, "-": 0.25, "*": 0.25, "/": 0.25}
        }
        self.load_memory()

    def load_memory(self):
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                    saved_beliefs = json.load(f)
                    self.beliefs.update(saved_beliefs)
            except Exception: pass

    def save_memory(self):
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.beliefs, f, indent=2)

    def get_priors(self, prompt):
        prompt = prompt.lower()
        intent = "generic"
        matches = [k for k in self.beliefs if k != "generic" and k in prompt]
        if matches:
            intent = max(matches, key=len)
        return self.beliefs[intent], intent

    def atualizar_crenca(self, intent, operador_usado, sucesso):
        if intent not in self.beliefs: return
        if operador_usado not in self.beliefs[intent]: return
        current_p = self.beliefs[intent][operador_usado]
        alpha = 0.2 
        new_p = current_p + alpha * (1.0 - current_p) if sucesso else current_p * (1.0 - alpha)
        self.beliefs[intent][operador_usado] = new_p
        total = sum(self.beliefs[intent].values())
        if total > 0:
            for k in self.beliefs[intent]: self.beliefs[intent][k] /= total
        self.save_memory()

    def analisar_falha(self, codigo, erro_stdout, erro_stderr):
        if "SyntaxError" in erro_stderr: return "Erro de Sintaxe."
        if "NameError" in erro_stderr:
            m = re.search(r"name '(.+?)' is not defined", erro_stderr)
            if m: return f"Alucinação de variável: '{m.group(1)}'."
            return "Erro de Nome."
        if "FALHA_ASSERT" in erro_stdout: return "Lógica incorreta."
        if "IndentationError" in erro_stderr: return "Erro de Formatação."
        if "TypeError" in erro_stderr: return "Erro de Tipagem/Argumentos."
        return "Erro desconhecido."

    def verificar_analogia(self, codigo_gerado, requisitos_ignorados=None):
        if "return" in codigo_gerado:
            if "+ +" in codigo_gerado or "- -" in codigo_gerado: return False, "Operadores duplicados"
            if codigo_gerado.strip().endswith("return"): return False, "Return vazio"
        return True, "Estrutura plausível"

    def verificar_coerencia(self, codigo, priors):
        return True, "OK"