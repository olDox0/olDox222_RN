"""
CRITIC v1.0 - The Judge.
Analisa logs de execução para determinar a verdadeira causa da falha.
"""
import re

class Critic:
    def julgar_execucao(self, stdout, stderr, codigo_gerado):
        """
        Retorna: (Veredito, Culpado, TipoDeErro)
        Veredito: 'CULPADO' (Rede errou), 'INOCENTE' (Teste errou), 'INCERTO'
        """
        log_completo = stdout + "\n" + stderr
        
        # Caso 1: Sucesso
        if "SUCESSO_TESTES" in log_completo:
            return "SUCESSO", None, None

        # Caso 2: Falha de Lógica (A conta deu errado)
        if "FALHA_ASSERT" in log_completo or "AssertionError" in log_completo:
            # A rede gerou código válido, mas a matemática está errada.
            # Culpado: Os operadores usados.
            return "CULPADO", "LOGICA", "AssertionError"

        # Caso 3: Erro de Sintaxe (Rede gerou lixo)
        if "SyntaxError" in log_completo:
            return "CULPADO", "SINTAXE", "SyntaxError"

        # Caso 4: Erro de Nome (Pode ser alucinação OU erro do teste)
        if "NameError" in log_completo:
            # Se o erro diz "name 'soma' is not defined", e a rede definiu 'def soma',
            # então o erro é do AMBIENTE (o python não leu o arquivo direito).
            # Se diz "name 'z' is not defined" e 'z' não foi definido, culpa da REDE.
            match = re.search(r"name '(.+?)' is not defined", log_completo)
            if match:
                var = match.group(1)
                if f"def {var}" in codigo_gerado:
                    return "INOCENTE", "AMBIENTE", "NameError (Definido mas não achado)"
                else:
                    return "CULPADO", var, "NameError (Alucinação)"
        
        # Caso 5: Indentação (Geralmente culpa do gerador de arquivo)
        if "IndentationError" in log_completo:
            return "INOCENTE", "FORMATACAO", "IndentationError"

        return "INCERTO", None, "Erro Desconhecido"