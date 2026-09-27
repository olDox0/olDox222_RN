# Arquivo Cobaia - Risco de Segurança
def processar_entrada_perigosa(dado):
    # O SiCDox deve identificar este 'eval' como proibido
    return eval(dado)