# -*- coding: utf-8 -*-
"""
ORN — Code Assembler (Dédalo)
Montador de códigos complexos por meio de Cosmo Visão I/O.
OSL-18: Apenas Standard Library.
"""
import ast

class CodeAssembler:
    def __init__(self, bridge, validator):
        self._bridge = bridge
        self._validator = validator

    def assemble_system(self, intent_prompt: str) -> str:
        """Gera um sistema complexo dividindo-o em I/O e micro-geração."""
        
        # 1. Cosmo Visão: Pedir apenas o esqueleto e os contratos # -*- coding: utf-8 -*-
# engine/thinking/assembler.py
"""
ORN — Code Assembler (Dédalo)
Montador de códigos complexos por meio de Cosmo Visão I/O.

OSL-18: Standard Library (usa ast.unparse nativo do Python 3.9+).
God: Dédalo — o arquiteto do labirinto, constrói por partes.
"""

from __future__ import annotations
import ast
from typing import Any

class CodeAssembler:
    """Orquestra a geração de código em fases (Esqueleto -> Validação -> Implementação)."""

    def __init__(self, bridge: Any, validator: Any):
        self._bridge = bridge
        self._validator = validator

    def assemble(self, intent_prompt: str) -> dict[str, Any]:
        """Executa a Cosmo Visão I/O para gerar código estruturado."""
        
        # FASE 1: Cosmo Visão (Esqueleto e Contratos I/O)
        skeleton_prompt = (
            f"Atue como um Arquiteto de Software Sênior.\n"
            f"Crie APENAS as assinaturas de classes e funções em Python para resolver o seguinte problema: {intent_prompt}\n"
            f"REGRAS OBRIGATÓRIAS:\n"
            f"1. Use type hints rigorosos (Input/Output).\n"
            f"2. Use 'pass' no corpo de todas as funções.\n"
            f"3. Não escreva a lógica agora, apenas a estrutura."
        )
        
        # Pedimos ao Hefesto (LLM) o esqueleto. Usamos max_tokens baixo para ser rápido.
        raw_skeleton = self._bridge.ask(skeleton_prompt, max_tokens=256)
        clean_skeleton = self._extract_code_block(raw_skeleton)

        # FASE 2: Validação e Correção de Erro (O Crivo)
        tree, error = self._validate_and_parse(clean_skeleton)
        
        # Se o modelo alucinou na sintaxe, entramos no loop de correção rápida
        retries = 0
        while tree is None and retries < 2:
            rescue_prompt = (
                f"O código gerou um erro de sintaxe: {error}\n"
                f"Corrija APENAS a sintaxe do código abaixo:\n```python\n{clean_skeleton}\n```"
            )
            raw_skeleton = self._bridge.ask(rescue_prompt, max_tokens=256)
            clean_skeleton = self._extract_code_block(raw_skeleton)
            tree, error = self._validate_and_parse(clean_skeleton)
            retries += 1

        if tree is None:
            return {
                "success": False, 
                "output": clean_skeleton, 
                "error": f"Falha de sintaxe irreparável após {retries} tentativas: {error}"
            }

        # O Esqueleto é válido! Usamos ast.unparse para formatá-padrão (Python 3.9+)
        formatted_skeleton = ast.unparse(tree)

        # Retornamos o esqueleto validado (No futuro, a Fase 3 expande os 'pass' aqui)
        return {
            "success": True,
            "output": formatted_skeleton,
            "error": None
        }

    def _extract_code_block(self, text: str) -> str:
        """Limpa a resposta do LLM, extraindo apenas o bloco de código."""
        if "```python" in text:
            return text.split("```python")[1].split("```")[0].strip()
        elif "```" in text:
            return text.split("```")[1].split("```")[0].strip()
        return text.strip()

    def _validate_and_parse(self, code: str) -> tuple[ast.AST | None, str | None]:
        """Tenta compilar a árvore sintática (AST). Retorna erro se falhar."""
        try:
            tree = ast.parse(code)
            return tree, None
        except SyntaxError as e:
            return None, f"Linha {e.lineno}: {e.msg}"