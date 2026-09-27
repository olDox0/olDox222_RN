# -*- coding: utf-8 -*-
"""
ORN — Logic Filter / Validator (Anúbis)
Valida todo output do LLM antes de chegar ao usuário.

OSL-5.2: Valida integridade de qualquer saída recebida de módulos externos.
OSL-7:   Contrato explícito — retorna (bool, motivo: str).
God: Anúbis — decide o que passa ou morre.

TODO Fase 1: implementar regras de validação básicas.
TODO Fase 2: adicionar validação sintática de código (ast.parse).
"""

from __future__ import annotations


class SiCDoxValidator:
    """Validador de output do LLM.

    Regras atuais (a expandir):
      - Output não pode ser vazio.
      - Output não pode ser apenas whitespace.
      - [Fase 2] Se lang == 'python', deve passar ast.parse().
    """

    def validar_output(self, output: str,
                       lang: str | None = None) -> tuple[bool, str]:
        """Valida o *output* gerado pelo modelo.

        OSL-5.1: Pré-condição — output deve ser str.
        OSL-7: Retorna tupla (válido, motivo) — chamador deve verificar.

        Args:
            output: Texto gerado pelo LLM.
            lang:   Linguagem do código, se aplicável ('python', 'c', etc).

        Returns:
            (True, "") se válido.
            (False, motivo) se inválido.
        """
        if not isinstance(output, str):
            return False, "Output não é uma string."

        if not output.strip():
            return False, "Output vazio ou apenas whitespace."

        if lang == "python":
            return self._validar_python(output)

        return True, ""

    # ------------------------------------------------------------------
    # Validações por linguagem
    # ------------------------------------------------------------------

    def _validar_python(self, codigo: str) -> tuple[bool, str]:
        """Tenta fazer parse do código Python gerado.

        OSL-18: usa ast da stdlib — sem deps externas.
        """
        import ast  # noqa: PLC0415 (stdlib, import local aceitável aqui)
        try:
            ast.parse(codigo)
            return True, ""
        except SyntaxError as exc:
            return False, f"SyntaxError no código gerado: {exc}"