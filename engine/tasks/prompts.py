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
    "Você é o PLANEJADOR do ORN. Dado um objetivo, produza o plano "
    "de implementação APENAS em JSON válido, sem texto antes nem depois.\n"
    "NUNCA inclua marcadores como | stopgen |, [END], [CRIATORES], "
    "[COMANDA], [RESULTADO] na resposta."
)

_PLAN_JSON_SCHEMA = """{{
  "understanding": "explicação em 1-2 frases do que o programa deve fazer",
  "files": [
    {{"path": "main.{ext}", "action": "create", "purpose": "descrição curta"}}
  ],
  "risks": ["risco 1 (ex: loop infinito)", "risco 2 (ex: divisão por zero)"],
  "success_criteria": ["critério de sucesso mensurável"]
}}"""

DRAFT_SYSTEM = (
    "Você é o RASCUNHADOR do ORN. Seu papel é criar o RASCUNHO ALGORÍTMICO / PSEUDO-CÓDIGO.\n"
    "REGRAS:\n"
    "- Foque na lógica passo a passo e na sequência correta das variáveis.\n"
    "- Se houver loops (while/for), garanta que a variável de controle avance a cada iteração para evitar loop infinito.\n"
    "- NUNCA use funções interativas de teclado (como input, scanf, getchar).\n"
    "- Retorne o rascunho em um único bloco ```<lang> ... ``` ou ```text ... ``` e nada mais."
)

IMPLEMENT_SYSTEM = (
    "Você é o IMPLEMENTADOR do ORN. Transforme o rascunho/pseudo-código do DRAFT na "
    "versão final completa, compilável e executável na linguagem solicitada.\n"
    "REGRAS OBRIGATÓRIAS:\n"
    "- Retorne APENAS o código completo dentro de um único bloco ```<lang> ... ```.\n"
    "- Para C ou C++: inclua todas as bibliotecas necessárias (#include <stdio.h>) e a função int main(void) completa.\n"
    "- NUNCA use entrada interativa de teclado (input, scanf). Use dados fixos de teste.\n"
    "- Garanta que todas as variáveis de laço sejam atualizadas a cada iteração (sem loops infinitos).\n"
    "- Se houver [FEEDBACK], corrija pontualmente o erro relatado."
    "- Retorne SOMENTE o JSON, sem markdown ```json``` e sem texto extra.\n"
)

DIFF_SYSTEM = (
    "Você é o CORRETOR CIRÚRGICO do ORN. Dado um código que falhou no sandbox e o erro ocorrido, "
    "produza a correção MÍNIMA necessária.\n"
    "REGRAS:\n"
    "- Altere apenas as linhas com problema. Não refatore o código funcional.\n"
    "- Use o formato de patch de linhas @N:\n"
    "  @N\n"
    "  - linha_antiga\n"
    "  + linha_corrigida\n"
    "- Ou retorne o código completo corrigido em um único bloco ```<lang> ... ```.\n"
    "- Sem texto explicativo antes ou depois."
)

def build_diff_prompt(task: Task, feedback: str) -> tuple[str, str]:
    impl = task.artifact("implement") or task.artifact("draft")
    code = (impl.code if impl else "").strip()
    
    numbered_lines = []
    for i, line in enumerate(code.splitlines(), start=1):
        numbered_lines.append(f"{i:>3} | {line}")
    numbered_code = "\n".join(numbered_lines)
    
    clean_fb = feedback.strip()
    if len(clean_fb) > 1200:
        clean_fb = clean_fb[:1200] + "\n[... truncado]"
        
    user = f"""Objetivo: {task.spec.goal}
Linguagem: {task.spec.language}

[CÓDIGO ATUAL]
{numbered_code}
[/CÓDIGO ATUAL]

[ERRO DO SANDBOX]
{clean_fb}
[/ERRO DO SANDBOX]

Corrija o erro reportado gerando o patch @N ou o código corrigido:"""
    return DIFF_SYSTEM, user

def _feedback_block(feedback: str | None) -> str:
    if not feedback:
        return ""
    clean_fb = feedback.strip()
    if len(clean_fb) > 1200:
        clean_fb = clean_fb[:1200] + "\n[... truncado]"
    return (
        "\n\n[FEEDBACK DA TENTATIVA ANTERIOR]\n"
        f"{clean_fb}\n\n"
        "Corrija o erro acima. Se for timeout/loop infinito, certifique-se de atualizar a variável de controle do loop.\n"
        "Retorne a correção completa em um único bloco de código ```<lang> ... ``` e nada mais."
    )

def build_plan_prompt(task: Task) -> tuple[str, str]:
    ext = "c" if task.spec.language in ("c", "cpp") else "py"
    schema = _PLAN_JSON_SCHEMA.format(ext=ext)
    user = f"""Objetivo: {task.spec.goal}
Linguagem alvo: {task.spec.language}

Responda APENAS com um JSON válido seguindo este schema:

{schema}

Regras:
- Retorne SOMENTE o JSON, sem markdown ```json``` e sem texto extra.
- "risks" deve conter riscos REAIS (loops, overflow, divisão por zero, etc).
- Nunca inclua marcadores internos como | stopgen |, [END], [CRIATORES]."""
    return PLAN_SYSTEM, user

def build_plan_retry_prompt(task: Task, previous_raw: str, error: str) -> tuple[str, str]:
    """Prompt de retry quando JSON falhou — mostra erro e exige correção."""
    ext = "c" if task.spec.language in ("c", "cpp") else "py"
    schema = _PLAN_JSON_SCHEMA.format(ext=ext)
    previous_preview = previous_raw[:400]
    if len(previous_raw) > 400:
        previous_preview += "\n[...truncado]"
    user = f"""Objetivo: {task.spec.goal}
Linguagem: {task.spec.language}

Sua tentativa anterior FALHOU na validação.
ERRO: {error}

TENTATIVA ANTERIOR (inválida):
{previous_preview}

Corrija e retorne APENAS o JSON válido (schema abaixo), sem markdown, sem texto extra:

{schema}"""
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

Crie o rascunho algorítmico da solução em um único bloco de código:"""
    return DRAFT_SYSTEM, user

def build_implement_prompt(task: Task, feedback: str | None = None) -> tuple[str, str]:
    plan = task.artifact("plan")
    plan_txt = (plan.content if plan and plan.content else "(sem plano)").strip()
    draft = task.artifact("draft")
    draft_code = (draft.code if draft and draft.code else "").strip()
    if not draft_code:
        draft_code = "# sem rascunho prévio"
    c_note = "\nPara C/C++: inclua #include <stdio.h> e int main(void) completo com retorno 0." if task.spec.language in ("c", "cpp") else ""
    user = f"""Objetivo: {task.spec.goal}
Linguagem: {task.spec.language}
[PLANO]
{plan_txt}
[/PLANO]
[RASCUNHO ALGORÍTMICO]
```{task.spec.language}
{draft_code}
```
[/RASCUNHO ALGORÍTMICO]
{_feedback_block(feedback)}
{c_note}
Implemente a versão final completa e funcional em um único bloco ```{task.spec.language} ... ```:"""
    return IMPLEMENT_SYSTEM, user

def build_implement_prompt(task: Task, feedback: str | None = None) -> tuple[str, str]:
    plan = task.artifact("plan")
    plan_txt = (plan.content if plan and plan.content else "(sem plano)").strip()
    draft = task.artifact("draft")
    draft_code = (draft.code if draft and draft.code else "").strip()
    if not draft_code:
        draft_code = "# sem código prévio"
    c_hint = "\nPreserve ou garanta a função int main(void) executável." if task.spec.language in ("c", "cpp") else "\nGaranta testes sem input()."
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
{c_hint}
Produza a versão final. Formato: um único bloco ```{task.spec.language} ... ``` e nada mais."""
    return IMPLEMENT_SYSTEM, user
