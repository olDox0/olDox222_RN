# -*- coding: utf-8 -*-
"""
ORN — Code Assembler (Dédalo)
Montador de código por Cosmo Visão I/O com heurísticas de baixo custo.

Objetivo: reduzir inferência de modelos pequenos priorizando contratos de
entrada/saída (I/O), com prompts curtos e recuperação determinística.
"""

from __future__ import annotations

import ast
import re
from typing import Any

from engine.tools.code_sandbox import diagnose_python_file, stage_code

class CodeAssembler:
    """Orquestra geração estrutural em fases de baixo custo.

    Fluxo:
      1) Extrai pistas de I/O do intent (heurística local, sem inferência).
      2) Solicita ao LLM somente um esqueleto Python com type hints.
      3) Valida sintaxe e aplica até 2 reparos curtos.
      4) Se falhar, retorna fallback determinístico mínimo.
    """

    def __init__(self, bridge: Any, validator: Any):
        self._bridge = bridge
        self._validator = validator

    def assemble(self, intent_prompt: str) -> dict[str, Any]:
        """Executa a Cosmo Visão I/O para gerar código estruturado."""
        io_hint = self._extract_io_hint(intent_prompt)
        skeleton_prompt = self._build_skeleton_prompt(intent_prompt, io_hint)

        raw_skeleton = self._bridge.ask(skeleton_prompt, max_tokens=220)
        clean_skeleton = self._extract_code_block(raw_skeleton)

        tree, error = self._validate_and_parse(clean_skeleton)
        retries = 0
        while tree is None and retries < 2:
            rescue_prompt = (
                "Corrija APENAS a sintaxe Python do código abaixo. "
                "Não adicione explicações.\n"
                f"```python\n{clean_skeleton}\n```"
            )
            raw_skeleton = self._bridge.ask(rescue_prompt, max_tokens=180)
            clean_skeleton = self._extract_code_block(raw_skeleton)
            tree, error = self._validate_and_parse(clean_skeleton)
            retries += 1

        if tree is None:
            fallback = self._deterministic_fallback(io_hint)
            return {
                "success": False,
                "output": fallback,
                "error": f"Falha sintática após {retries} tentativas: {error}",
                "strategy": "fallback",
            }

        formatted = ast.unparse(tree)
        ok, reason = self._validator.validar_output(formatted, lang="python")
        if not ok:
            fallback = self._deterministic_fallback(io_hint)
            return {
                "success": False,
                "output": fallback,
                "error": f"Validação rejeitou saída: {reason}",
                "strategy": "fallback",
            }

        staged_path = stage_code(formatted, stem="assembler")
        diag_issues = diagnose_python_file(staged_path)
        if diag_issues:
            formatted = self._refine_with_diagnostics(formatted, diag_issues)
            staged_path = stage_code(formatted, stem="assembler_refined")

        return {
            "success": True,
            "output": formatted,
            "error": None,
            "strategy": "io_heuristic",
            "io_hint": io_hint,
            "staged_path": str(staged_path),
            "diagnostic_issues": diag_issues[:8],
        }

    def assemble_system(self, intent_prompt: str) -> str:
        """Compat: retorna apenas texto final para chamadas antigas."""
        result = self.assemble(intent_prompt)
        return result["output"]

    def _build_skeleton_prompt(self, intent_prompt: str, io_hint: str) -> str:
        return (
            "Você é um arquiteto de software focado em I/O.\n"
            "Gere SOMENTE código Python com contratos claros de entrada e saída.\n"
            "Regras: type hints obrigatórios, docstring curta, corpo com pass.\n"
            "Sem explicação, sem markdown fora de bloco de código.\n"
            f"Pistas de I/O detectadas: {io_hint}\n"
            f"Problema: {intent_prompt}"
        )

    def _extract_io_hint(self, intent_prompt: str) -> str:
        """Extrai pistas de I/O via heurística textual barata.

        Não tenta entender tudo; apenas reduz ambiguidade para o LLM.
        """
        text = intent_prompt.lower()
        in_hints: list[str] = []
        out_hints: list[str] = []

        if re.search(r"\b(json|yaml|csv|arquivo|file)\b", text):
            in_hints.append("input_document")
        if re.search(r"\b(api|http|request|endpoint)\b", text):
            in_hints.append("remote_payload")
        if re.search(r"\b(stream|fila|queue|evento)\b", text):
            in_hints.append("event_stream")

        if re.search(r"\b(relat[oó]rio|summary|resumo)\b", text):
            out_hints.append("report_text")
        if re.search(r"\b(c[oó]digo|code|script)\b", text):
            out_hints.append("code_artifact")
        if re.search(r"\b(log|telemetria|m[ée]trica)\b", text):
            out_hints.append("observability")

        if not in_hints:
            in_hints.append("generic_input")
        if not out_hints:
            out_hints.append("generic_output")

        return f"IN={','.join(in_hints)}; OUT={','.join(out_hints)}"

    def _extract_code_block(self, text: str) -> str:
        """Extrai bloco de código de resposta LLM."""
        if "```python" in text:
            return text.split("```python", 1)[1].split("```", 1)[0].strip()
        if "```" in text:
            return text.split("```", 1)[1].split("```", 1)[0].strip()
        return text.strip()

    def _validate_and_parse(self, code: str) -> tuple[ast.AST | None, str | None]:
        try:
            return ast.parse(code), None
        except SyntaxError as exc:
            return None, f"Linha {exc.lineno}: {exc.msg}"

    def _deterministic_fallback(self, io_hint: str) -> str:
        """Fallback estável para não bloquear o fluxo da CLI."""
        return (
            "from typing import Any\n\n"
            "def assemble_io_contract(payload: Any) -> dict[str, Any]:\n"
            f"    \"\"\"Fallback determinístico. {io_hint}\"\"\"\n"
            "    pass\n"
        )

    def _refine_with_diagnostics(self, code: str, issues: list[str]) -> str:
        """Envia código estagiado + diagnóstico para melhoria rápida pelo LLM."""
        fix_prompt = (
            "Corrija APENAS os problemas listados no código Python.\n"
            "Mantenha assinatura e intenção original. Responda só com código.\n"
            f"Problemas:\n- " + "\n- ".join(issues[:6]) + "\n"
            f"```python\n{code}\n```"
        )
        raw = self._bridge.ask(fix_prompt, max_tokens=220)
        candidate = self._extract_code_block(raw)
        tree, _ = self._validate_and_parse(candidate)
        if tree is None:
            return code
        fixed = ast.unparse(tree)
        ok, _ = self._validator.validar_output(fixed, lang="python")
        return fixed if ok else code
