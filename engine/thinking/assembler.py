# -*- coding: utf-8 -*-
"""
ORN — CodeAssembler (Dédalo / Cosmo Visão)
Gera código, diagnostica no sandbox e itera até passar ou esgotar tentativas.

OSL-3:  CodeDrawer e sandbox importados lazy.
OSL-4:  Cada método faz uma coisa; loop em _refine_loop().
OSL-7:  assemble() sempre retorna dict com 'success', 'output', 'error'.
OSL-15: Erros de execução não derrubam o pipeline — viram feedback.
OSL-18: stdlib only (subprocess, ast, hashlib, time — tudo stdlib).
God: Dédalo — constrói o labirinto do código até ele funcionar.

Fluxo:
    assemble(task)
        ├─ bridge.ask(PROMPT_GERAR)      # 1ª geração
        ├─ _extract_code(output)         # extrai bloco python
        ├─ stage_code(code)              # .orn/sandbox_codegen/candidate_*.py
        ├─ _diagnose(path)               # lint + execução isolada
        ├─ se issues → bridge.ask(PROMPT_FIX + erros + esqueleto)
        └─ repete max_retries vezes
        └─ sucesso → CodeDrawer.upsert_snippet()
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engine.core.llm_bridge import SiCDoxBridge


# ---------------------------------------------------------------------------
# Prompts de geração e correção
# ---------------------------------------------------------------------------

_PROMPT_GERAR = """\
[TASK] Escreva código Python correto e funcional para: {task}
Regras:
- Apenas código Python válido, sem texto explicativo antes do bloco.
- Envolva o código em [code-begin] ... [code-end].
- Sem imports desnecessários. Sem eval/exec. Sem bare except.
- Type hints obrigatórios em funções públicas.
"""

_PROMPT_FIX = """\
[TASK] Corrija o código Python abaixo.

Tarefa original: {task}

Esqueleto atual (resumo):
{skeleton}

Erros encontrados:
{errors}

Regras:
- Corrija TODOS os erros listados.
- Envolva o código corrigido em [code-begin] ... [code-end].
- Sem texto explicativo — apenas o código.
"""

# ---------------------------------------------------------------------------
# Limite de execução isolada
# ---------------------------------------------------------------------------
_RUN_TIMEOUT: int = 8   # segundos — conservador para N2808


# ---------------------------------------------------------------------------
# CodeAssembler
# ---------------------------------------------------------------------------

class CodeAssembler:
    """Gera e refina código via loop diagnose→feedback.

    Args:
        bridge:     SiCDoxBridge já instanciada (injeção de dependência).
        validator:  SiCDoxValidator (usado para validar output bruto do LLM).
        max_retries: Tentativas máximas de correção (1 = gera + 1 fix).
        run_isolated: Se True, executa o candidato com `python -I` (sandbox real).
    """

    def __init__(
        self,
        bridge: "SiCDoxBridge",
        validator: Any,
        max_retries: int = 2,
        run_isolated: bool = True,
    ) -> None:
        self._bridge = bridge
        self._validator = validator
        self._max_retries = max(1, int(max_retries))
        self._run_isolated = run_isolated

    # ------------------------------------------------------------------
    # API pública — chamada pelo Executive._run_gen()
    # ------------------------------------------------------------------

    def assemble(self, task: str) -> dict[str, Any]:
        """Gera, testa e refina código para a tarefa dada.

        Returns:
            {
              "success": bool,
              "output":  str,   # código final (ou melhor tentativa)
              "error":   str,   # mensagem de falha (vazio se success)
              "attempts": int,  # quantas gerações foram feitas
            }
        """
        if not task or not task.strip():
            return {"success": False, "output": "", "error": "task vazio.", "attempts": 0}

        return self._refine_loop(task.strip())

    # ------------------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------------------

    def _refine_loop(self, task: str) -> dict[str, Any]:
        """Gera → diagnostica → corrige, até max_retries ou sucesso."""
        from engine.tools.code_sandbox import (   # lazy (OSL-3)
            diagnose_python_file,
            stage_code,
        )
        from engine.core.blackboard import CognitiveReducer  # lazy

        code      = ""
        issues: list[str] = []
        attempts  = 0
        last_path: Path | None = None

        for attempt in range(self._max_retries + 1):
            attempts = attempt + 1

            # ── 1. Gerar / corrigir via LLM ───────────────────────────
            if attempt == 0:
                prompt = _PROMPT_GERAR.format(task=task)
            else:
                skeleton = CognitiveReducer.reduce_file(
                    "candidate.py", code, max_chars=400
                )
                errors_text = "\n".join(f"  • {i}" for i in issues[:10])
                prompt = _PROMPT_FIX.format(
                    task=task,
                    skeleton=skeleton,
                    errors=errors_text,
                )

            raw_output = self._bridge.ask(prompt, max_tokens=256)

            # ── 2. Extrair bloco de código ─────────────────────────────
            extracted = _extract_code(raw_output)
            if not extracted:
                # LLM não usou as tags — tenta pegar bloco ```python
                extracted = _extract_markdown_code(raw_output)
            if not extracted:
                # Sem bloco detectável — usa o output bruto se parece código
                extracted = raw_output.strip() if raw_output.strip().startswith(("def ", "class ", "import ")) else ""

            if not extracted:
                issues = ["LLM não gerou um bloco de código reconhecível."]
                code   = raw_output  # guarda para diagnóstico textual
                continue

            code = extracted

            # ── 3. Staging ────────────────────────────────────────────
            try:
                last_path = stage_code(code, stem="candidate")
            except OSError as exc:
                return {
                    "success": False,
                    "output":  code,
                    "error":   f"[SANDBOX] Falha ao escrever arquivo: {exc}",
                    "attempts": attempts,
                }

            # ── 4. Diagnóstico (lint + execução) ─────────────────────
            issues = diagnose_python_file(last_path)

            if self._run_isolated and not issues:
                # Só executa se o lint passou — economiza tempo no N2808
                run_issues = _run_isolated_script(last_path, timeout=_RUN_TIMEOUT)
                issues.extend(run_issues)

            if not issues:
                # ── 5. Sucesso — salva no CodeDrawer ──────────────────
                _save_to_drawer(task=task, code=code)
                return {
                    "success":  True,
                    "output":   code,
                    "error":    "",
                    "attempts": attempts,
                }

        # Esgotou tentativas — retorna melhor código com lista de issues
        error_summary = f"Não resolvido após {attempts} tentativa(s): " + "; ".join(issues[:3])
        return {
            "success":  False,
            "output":   code,
            "error":    error_summary,
            "attempts": attempts,
        }


# ---------------------------------------------------------------------------
# Extratores de código (OSL-4)
# ---------------------------------------------------------------------------

_RE_TAGGED = re.compile(
    r"\[code-begin\](.*?)\[code-end\]",
    re.IGNORECASE | re.DOTALL,
)
_RE_MARKDOWN = re.compile(
    r"```(?:python)?\s*\n(.*?)```",
    re.DOTALL,
)


def _extract_code(text: str) -> str:
    """Extrai primeiro bloco [code-begin]...[code-end]."""
    m = _RE_TAGGED.search(text or "")
    return m.group(1).strip() if m else ""


def _extract_markdown_code(text: str) -> str:
    """Fallback: extrai primeiro bloco ```python ... ```."""
    m = _RE_MARKDOWN.search(text or "")
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# Execução isolada (OSL-15: falha não derruba pipeline)
# ---------------------------------------------------------------------------

def _run_isolated_script(path: Path, timeout: int = _RUN_TIMEOUT) -> list[str]:
    """Executa `python -I <path>` e retorna lista de erros (vazia = OK).

    -I (isolated): ignora PYTHONPATH, site-packages e variáveis de ambiente.
    Equivalente ao `orn diagnose --run` interno.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-I", str(path)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return [f"[RUN] Timeout ({timeout}s) — possível loop infinito."]
    except OSError as exc:
        return [f"[RUN] Falha ao executar: {exc}"]

    if result.returncode != 0:
        # Pega as últimas 3 linhas do stderr (normalmente contém o erro)
        lines = [l.strip() for l in result.stderr.splitlines() if l.strip()]
        tail  = lines[-3:] if lines else ["[RUN] Erro desconhecido."]
        return [f"[RUN] retorno={result.returncode}"] + tail

    return []


# ---------------------------------------------------------------------------
# Persistência no CodeDrawer (OSL-3: lazy)
# ---------------------------------------------------------------------------

def _save_to_drawer(task: str, code: str) -> None:
    """Salva snippet aprovado no CodeDrawer. Falha silenciosa (OSL-15)."""
    try:
        from engine.tools.code_drawer import CodeDrawer  # lazy
        drawer = CodeDrawer()
        # Nome derivado da task (slug simples)
        name = re.sub(r"[^\w]+", "_", task.strip().lower())[:40].strip("_")
        drawer.upsert_snippet(
            name=name or "generated",
            lang="python",
            inputs=[],
            outputs=[],
            code=code,
            tags=["assembler", "auto"],
        )
    except Exception:
        pass   # OSL-15: drawer não é crítico para o pipeline