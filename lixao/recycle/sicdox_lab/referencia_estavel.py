# Exemplo de "Como o Arquiteto resolve"
import ast
def processar_entrada_segura(dado):
    return ast.literal_eval(dado)