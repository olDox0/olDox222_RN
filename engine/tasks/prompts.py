# -*- coding: utf-8 -*-
"""Prompts por fase do sistema de tarefas.

Cada builder retorna ``(system_hint, user_prompt)``. O runner concatena
os dois com ``\\n\\n`` antes de chamar ``bridge.ask`` (o bridge atual
recebe prompt único).

God: Thoth (linguagem) + Atena (estratégia).
"""
from __future__ import annotations

from engine.tasks.model import Task


PLAN_SYSTEM = (
    "Você é o PLANEJADOR do ORN. Dado um objetivo, produza um plano "
    "estruturado em JSON. Sem código, sem prosa. Responda APENAS o JSON."
)

DRAFT_SYSTEM = (
    "Você é o RASCUNHADOR do ORN. Dado o plano, produza um rascunho "
    "executável. Formato: um único bloco ```<lang> ... ``` e nada mais. "
    "Priorize correção sobre elegância; o polimento vem depois."
)

IMPLEMENT_SYSTEM = (
    "Você é o IMPLEMENTADOR do ORN. A partir do rascunho, produza a versão "
    "final com type hints, docstring curta e tratamento de erro mínimo. "
    "Formato: um único bloco ```<lang> ... ``` e nada mais. "
    "Se houver [FEEDBACK], corrija APENAS o problema apontado."
)


def _feedback_block(feedback: str | None) -> str:
    if not feedback:
        return ""
    return (
        "\n\n[FEEDBACK DA TENTATIVA ANTERIOR]\n"
        f"{feedback.strip()}\n\n"
        "Corrija APENAS o problema apontado. Não refatore o resto.\n"
        "Retorne o código completo corrigido em **um único bloco** "
        "```<lang> ... ``` e nada mais."
    )

def build_plan_prompt(task: Task) -> tuple[str, str]:
    constraints = "\n".join(f"- {c}" for c in task.spec.constraints) or "- (nenhuma)"
    user = f"""Objetivo: {task.spec.goal}
Linguagem alvo: {task.spec.language}
Restrições:
{constraints}

Responda APENAS com um objeto JSON válido no formato exato:
{{
  "understanding": "string",
  "files": [{{"path": "string", "action": "create|modify", "purpose": "string"}}],
  "io_contracts": [{{"symbol": "string", "kind": "function", "inputs": [{{"name": "string", "type": "string"}}], "outputs": [{{"type": "string"}}], "errors": ["string"]}}],
  "risks": ["string"],
  "success_criteria": ["string"]
}}
Sem texto fora do JSON. Sem comentários."""
    return PLAN_SYSTEM, user


def build_draft_prompt(task: Task, feedback: str | None = None) -> tuple[str, str]:
    plan = task.artifact("plan")
    plan_txt = (plan.content if plan and plan.content else "(sem plano disponível)").strip()
    user = f"""Objetivo: {task.spec.goal}
Linguagem: {task.spec.language}

[PLANO]
{plan_txt}
[/PLANO]
{_feedback_block(feedback)}

Produza um rascunho executável. Formato: um único bloco ```{task.spec.language} ... ``` e nada mais."""
    return DRAFT_SYSTEM, user


def build_implement_prompt(task: Task, feedback: str | None = None) -> tuple[str, str]:
    plan = task.artifact("plan")
    plan_txt = (plan.content if plan and plan.content else "(sem plano)").strip()
    draft = task.artifact("draft")
    draft_code = (draft.code if draft and draft.code else "").strip()
    if not draft_code:
        draft_code = "# (rascunho vazio)"
    user = f"""Objetivo: {task.spec.goal}
Linguagem: {task.spec.language}

[PLANO]
{plan_txt}
[/PLANO]

[RASCUNHO]
```{task.spec.language}
{draft_code}
```
[/RASCUNHO]
{_feedback_block(feedback)}

Produza a versão final. Formato: um único bloco ```{task.spec.language} ... ``` e nada mais."""
    return IMPLEMENT_SYSTEM, user
