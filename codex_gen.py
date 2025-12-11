"""
CODEX GENERATOR
Gera código Python sintético válido para treinamento massivo.
"""
import random

# Vocabulário Controlado (Para manter a rede leve)
FUNCOES = ["soma", "sub", "mult", "div", "calc", "f1", "f2", "operacao"]
VARIAVEIS = ["a", "b", "x", "y", "i", "j", "num", "val"]
OPS = ["+", "-", "*", "/", "%"]

def gerar_funcao_simples():
    """
    Gera uma string de código Python válida e aleatória.
    Ex: 'def calc ( x , y ) : return x * y'
    """
    nome_func = random.choice(FUNCOES)
    v1 = random.choice(VARIAVEIS)
    v2 = random.choice(VARIAVEIS)
    
    # Garante que v2 seja diferente de v1 para ficar bonito
    while v2 == v1:
        v2 = random.choice(VARIAVEIS)
        
    op = random.choice(OPS)
    
    # Montagem da estrutura sintática
    codigo = f"def {nome_func} ( {v1} , {v2} ) : return {v1} {op} {v2}"
    
    return codigo

def obter_vocabulario_completo():
    """Retorna todas as palavras possíveis para inicializar o Tokenizer."""
    # AQUI: Adicionei a "," na lista
    tokens = ["def", "(", ")", ":", "return", ",", "<PAD>", "<UNK>"] 
    tokens += FUNCOES + VARIAVEIS + OPS
    return list(set(tokens))

# Teste rápido se rodado direto
if __name__ == "__main__":
    print("--- Exemplos de Código Gerado ---")
    for _ in range(5):
        print(gerar_funcao_simples())