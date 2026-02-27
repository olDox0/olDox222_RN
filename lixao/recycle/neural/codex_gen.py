# doxoade/neural/codex_gen.py
import random

FUNCOES = ["salvar", "carregar", "logar", "processar", "ler", "escrever"]
VARIAVEIS = ["nome", "dados", "texto", "conteudo", "caminho"]
MODOS = ["'w'", "'r'", "'a'"]

def gerar_sintaxe_basica():
    f = random.choice(FUNCOES)
    v = random.choice(VARIAVEIS)
    return f"def {f} ( {v} ) : pass"

def gerar_funcao_simples():
    f = random.choice(FUNCOES)
    return f"def {f} ( a , b ) : return a + b"

def gerar_funcao_condicional():
    v = random.choice(VARIAVEIS)
    return f"def checar ( {v} ) : if {v} : return True"

# [NOVO] O Dataset de Ouro (Python Fluente)
def gerar_funcao_io():
    """Gera código I/O Pythonicamente perfeito."""
    f_name = random.choice(["salvar_arquivo", "gravar_texto", "escrever_log"])
    arg = random.choice(["nome", "caminho"])
    conteudo = random.choice(["texto", "dados", "msg"])
    modo = "'w'"
    
    # Variações válidas
    templates = [
        f"def {f_name}({arg}): with open({arg}, {modo}) as f: f.write({conteudo})",
        f"def {f_name}({arg}): with open('file.txt', {modo}) as f: f.write({conteudo})",
        f"def {f_name}({arg}, {conteudo}): with open({arg}, {modo}) as arquivo: arquivo.write({conteudo})"
    ]
    return random.choice(templates)

def obter_vocabulario_completo():
    # Garante que todos os símbolos do Python estejam aqui
    return list(set(FUNCOES + VARIAVEIS + MODOS + 
        ["def", "return", "if", "else", "with", "open", "as", "write", "read", 
         "(", ")", ":", ".", ",", "pass", "True", "False", "None"]))