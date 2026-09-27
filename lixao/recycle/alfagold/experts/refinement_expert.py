# alfagold/experts/refinement_expert.py
import re

class RefinementExpert:
    """
    Expert de Refinamento v3.1 (Nuclear Dedup).
    Adiciona detecção de repetições aglutinadas (passpasspass).
    """
    def process(self, raw_code):
        # 1. Deduplicação (Ruído Neural)
        code = self._deduplicate(raw_code)
        
        # 2. Espaçamento Sintático (Gramática)
        code = self._fix_spacing(code)
        
        # 3. Indentação e Newlines (Estrutura)
        code = self._apply_indentation(code)
        
        # 4. Limpeza Final
        code = code.replace(" .", ".").replace(" :", ":").replace("( ", "(")
        return code.strip()

    def _deduplicate(self, text):
        """Remove repetições de palavras e padrões comuns."""
        # 1. Palavras com espaço: 'caminho caminho' -> 'caminho'
        text = re.sub(r'\b(\w+)(?:\s+\1\b)+', r'\1', text)
        
        # 2. Pontuação repetida: '::' -> ':'
        text = re.sub(r'([:,;=])\1+', r'\1', text)
        
        # 3. Aspas malucas: "'w''w'" -> "'w'"
        text = re.sub(r"('[\w\.]+')\1+", r"\1", text)
        
        # 4. [NOVO] Repetição Aglutinada (Nuclear)
        # Detecta qualquer sequência de 3+ letras que se repete 2+ vezes colada
        # Ex: "passpass" -> "pass"
        # Grupo 1: ([a-zA-Z_]{3,}) -> Palavra de pelo menos 3 letras
        # \1+ -> A mesma palavra repetida 1 ou mais vezes
        text = re.sub(r'([a-zA-Z_]{3,})\1+', r'\1', text)
        
        return text

    def _fix_spacing(self, text):
        keywords = ["def", "with", "as", "import", "return", "if", "else", "for", "while", "in"]
        for kw in keywords:
            # Espaço após keyword
            text = re.sub(rf'(?<=\b{kw})([a-zA-Z0-9_\'\"])', r' \1', text)
            # Espaço antes de keyword se colado em pontuação
            text = re.sub(rf'([):])({kw}\b)', r'\1 \2', text)

        text = re.sub(r',(\S)', r', \1', text)
        return text

    def _apply_indentation(self, text):
        """Transforma one-liners em blocos indentados."""
        # Padrão: : seguido de comando
        pattern = r':\s*(with|if|for|return|print|open|pass)'
        
        def replacer(match):
            return f":\n    {match.group(1)}"
            
        text = re.sub(pattern, replacer, text)
        text = text.replace("withopen", "with open")
        
        return text