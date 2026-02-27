# alfagold/experts/reward_expert.py
import numpy as np
import re

class RewardExpert:
    """
    Expert de Valor (Córtex Orbitofrontal).
    Avalia a qualidade e aderência do código gerado ao objetivo (Prompt).
    """
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        
    def evaluate(self, prompt, generated_code):
        """
        Retorna um score de 0.0 a 1.0.
        """
        score = 0.5 # Começa neutro
        
        # 1. Coerência Estrutural (Sintaxe Básica)
        if self._check_balance(generated_code):
            score += 0.2
        else:
            score -= 0.3
            
        # 2. Aderência ao Prompt (Semântica Simples)
        keywords = self._extract_keywords(prompt)
        hits = 0
        for kw in keywords:
            # I/O Check
            if kw in ["salvar", "escrever"] and ("write" in generated_code or "open" in generated_code):
                hits += 1
            # Logic Check
            if kw in ["calcular", "soma"] and ("return" in generated_code or "+" in generated_code):
                hits += 1
                
        if hits > 0: score += 0.2
        
        # 3. Penalidade de Alucinação (Repetição/Gagueira)
        if self._detect_loops(generated_code):
            score -= 0.4
            
        # 4. Penalidade de Formatação Bizarra
        if "::" in generated_code or ".." in generated_code:
            score -= 0.2
            
        return np.clip(score, 0.0, 1.0)

    def _check_balance(self, code):
        """Verifica parênteses e aspas básicos."""
        try:
            if code.count('(') != code.count(')'): return False
            if code.count("'") % 2 != 0: return False
            if code.count('"') % 2 != 0: return False
            # Se tem 'def', tem que ter ':'
            if "def " in code and ":" not in code: return False
            return True
        except Exception as e:
            import sys, os
            _, exc_obj, exc_tb = sys.exc_info()
            f_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            line_n = exc_tb.tb_lineno
            print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: _check_balance\033[0m")
            print(f"\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033[0m")
            return False

    def _detect_loops(self, code):
        """Detecta gagueira grave (ex: caminho caminho)."""
        # Limpa pontuação para ver palavras puras
        clean = re.sub(r'[^\w\s]', '', code)
        tokens = clean.split()
        if len(tokens) < 3: return False
        
        # Janela deslizante de 2 tokens iguais
        for i in range(len(tokens) - 1):
            if tokens[i] == tokens[i+1]: # Repetição direta
                return True
        return False

    def _extract_keywords(self, text):
        return [w.lower() for w in text.split() if len(w) > 3]