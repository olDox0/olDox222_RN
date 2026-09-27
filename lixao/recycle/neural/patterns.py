# doxoade/neural/patterns.py

"""
Banco de Padrões Estruturais (Syntax Mirror).
Define esqueletos de código válido para guiar a geração.
Tokens genéricos:
- <ID>: Qualquer identificador (variável/função)
- <ARGS>: Argumentos
- <STR>: String
- <EXPR>: Expressão
"""

PATTERNS = [
    # Definição de Função Padrão
    ["def", "<ID>", "(", "<ARGS>", ")", ":"],
    
    # Context Manager (I/O)
    ["with", "open", "(", "<STR>", ",", "<STR>", ")", "as", "<ID>", ":"],
    
    # Bloco Simples
    ["if", "<EXPR>", ":", "return", "<EXPR>"],
]

def match_pattern(current_tokens):
    """
    Tenta alinhar os tokens atuais com um padrão conhecido.
    Retorna o próximo token esperado se houver um match forte.
    """
# [DOX-UNUSED]     best_match = None
# [DOX-UNUSED]     max_score = 0
    
    # Normaliza tokens atuais para o formato genérico
    normalized = []
    for t in current_tokens:
        if t in ["def", "return", "if", "else", "with", "open", "as", ":", "(", ")", ","]:
            normalized.append(t)
        elif t.startswith("'") or t.startswith('"'):
            normalized.append("<STR>")
        elif t.isidentifier():
            normalized.append("<ID>")
        else:
            normalized.append("<EXPR>")

    # Compara com o banco
    for pattern in PATTERNS:
        # Verifica se o padrão 'encaixa' no final da sequência atual
        # Ex: current=[def, <ID>], pattern=[def, <ID>, (, ...] -> Match!
        
        # Olha apenas os últimos N tokens para ver se encaixam no início de um padrão
# [DOX-UNUSED]         n = len(normalized)
        for i in range(len(pattern)):
            # Tenta alinhar o final do normalized com o começo do pattern
            # normalized: ... [def, <ID>]
            # pattern:        [def, <ID>, (, ...]
            sub_norm = normalized[- (i + 1):]
            sub_pat = pattern[:i + 1]
            
            if sub_norm == sub_pat:
                if i + 1 < len(pattern):
                    return pattern[i + 1] # Retorna o próximo esperado (ex: '(')

    return None