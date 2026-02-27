# ia_core/logic_filter.py
import re

class SiCDoxValidator:
    """System 2: O Censor Lógico do SiCDox (MPoT-8)."""
    
    def validar_output(self, output: str) -> bool:
        """Verifica se o plano proposto é compatível com o Doxoade."""
        # Regra 1: Deve ser .dox ou Python válido (não Java/C#)
        proibidos = ["String ", "public class", "private int", "void "]
        if any(term in output for term in proibidos):
            return False, "Erro: IA gerou sintaxe fora do padrão Python/Maestro."

        # Regra 2: Se for .dox, deve conter comandos conhecidos
        if "```dox" in output or "RUN " in output:
            if "doxoade" not in output:
                return False, "Aviso: Script .dox não invoca o núcleo 'doxoade'."

        return True, "OK"