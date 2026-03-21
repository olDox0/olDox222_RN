# -*- coding: utf-8 -*-
"""
ORN — CodeHook (Argos)
Hook pós-inferência: detecta código no output do think, diagnostica
e aciona o CodeAssembler para corrigir se necessário.

OSL-4:  Três funções, cada uma com uma responsabilidade.
OSL-7:  apply() sempre retorna str — nunca None nem exceção não tratada.
OSL-15: Falha no sandbox não derruba o think — output original é preservado.
OSL-18: stdlib only neste módulo; sandbox/assembler importados lazy (OSL-3).
God: Argos — observa tudo; só age quando vê um problema real.

Integração em executive._run_think():
    # após _looks_degenerate_think_output / antes de build board_snapshot
    output = apply_code_hook(output, prompt, bridge=_bridge, validator=validator)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engine.core.llm_bridge import SiCDoxBridge

# ---------------------------------------------------------------------------
# Regex — detecta bloco de código Python no output do LLM
# ---------------------------------------------------------------------------

_RE_TAGGED = re.compile(
    r"\[code-begin\](.*?)\[code-end\]",
    re.IGNORECASE | re.DOTALL,
)
_RE_FENCED_CLOSED = re.compile(
    r"```(?:python)?\s*\n(.*?)```",
    re.DOTALL,
)
_RE_FENCED_OPEN = re.compile(
    r"```(?:python)?\s*\n(.*)",   # sem ``` de fechamento — output cortado
    re.DOTALL,
)

_RE_FENCED = _RE_FENCED_CLOSED

def _extract_code(text: str) -> str:
    """Extrai primeiro bloco [code-begin]...[code-end]."""
    m = _RE_TAGGED.search(text or "")
    return m.group(1).strip() if m else ""


def _extract_markdown_code(text: str) -> str:
    """Extrai bloco ```python ... ```.
    Fallback: aceita bloco aberto (output truncado pelo limite de tokens).
    """
    # Tenta bloco fechado primeiro
    m = _RE_FENCED_CLOSED.search(text or "")
    if m:
        return m.group(1).strip()

    # Bloco aberto — output foi cortado antes do fechamento
    m = _RE_FENCED_OPEN.search(text or "")
    if m:
        partial = m.group(1).strip()
        # Só aceita se parecer código real (tem pelo menos def/class/import)
        if any(kw in partial for kw in ("def ", "class ", "import ", "return ")):
            return partial

    return ""


def _has_python_code(text: str) -> bool:
    """True se o output parece conter código Python relevante."""
    if _RE_TAGGED.search(text) or _RE_FENCED.search(text):
        return True
    # Fallback: linhas com def/class na raiz (sem markdown)
    for line in (text or "").splitlines():
        if line.startswith(("def ", "class ", "import ", "from ")):
            return True
    return False


# ---------------------------------------------------------------------------
# Hook principal — chamado pelo Executive._run_think()
# ---------------------------------------------------------------------------

def apply_code_hook(
    output: str,
    task: str,
    bridge: "SiCDoxBridge",
    validator: Any,
    max_retries: int = 1,
    run_isolated: bool = True,
) -> str:
    """Diagnostica e corrige código presente no output do think.

    Se o output não contiver código Python, retorna output inalterado.
    Se o diagnóstico passar limpo, retorna output inalterado.
    Se houver issues, aciona o CodeAssembler e substitui o bloco de código.

    Args:
        output:       Texto gerado pelo bridge.ask() no _run_think().
        task:         Prompt original do usuário (usado como task no assembler).
        bridge:       Bridge já ativa (não recarrega o modelo).
        validator:    SiCDoxValidator para validar o output corrigido.
        max_retries:  Tentativas de correção repassadas ao CodeAssembler.
        run_isolated: Executa o candidato com `python -I` antes de aprovar.

    Returns:
        Output original ou output com bloco de código substituído pelo fix.
    """
    _is_bare_code = (
        not _has_python_code(output)
        and any(output.lstrip().startswith(kw)
                for kw in ("def ", "class ", "from ", "import "))
    )
    if not _has_python_code(output) and not _is_bare_code:
        return output

    _truncated = (output.count("```") % 2) == 1
    code = _extract_code(output) or _extract_markdown_code(output)

    # Se não extraiu código mas o bloco está aberto, usa a task diretamente
    if not code:
        if _truncated:
            issues = ["[HOOK] Output truncado — sem bloco extraível."]
            return _run_assembler_fix(
                task=task,
                broken_code="",
                issues=issues,
                bridge=bridge,
                validator=validator,
                max_retries=max_retries,
                run_isolated=run_isolated,
                original_output=output,
            )
        return output  # sem código, sem truncamento — preserva output

    issues = _diagnose_inline(code)

    # NOVO: Se o linter aprovou a sintaxe, obriga a rodar o código para ver se funciona!
    if not issues and run_isolated:
        issues.extend(_run_sandbox_in_hook(code))

    if _truncated and not issues:
        issues = ["[HOOK] Bloco de código truncado pelo limite de tokens."]

    if not issues:
        return output

    # ── Há issues → aciona o assembler ────────────────────────────────
    fixed_output = _run_assembler_fix(
        task=task,
        broken_code=code,
        issues=issues,
        bridge=bridge,
        validator=validator,
        max_retries=max_retries,
        run_isolated=run_isolated,
        original_output=output,
    )
    return fixed_output


# ---------------------------------------------------------------------------
# Diagnose inline (OSL-4)
# ---------------------------------------------------------------------------

# Issues que não justificam chamar o assembler — custo > benefício no N2808
_TRIVIAL_ISSUES: tuple[str, ...] = (
    "trailing whitespace",
    "evitar TAB",
    "linha acima de 120",
)

def _diagnose_inline(code: str) -> list[str]:
    try:
        from engine.tools.code_sandbox import lint_python_text
        all_issues = lint_python_text(code)
        # Filtra issues que não quebram execução
        return [i for i in all_issues
                if not any(t in i for t in _TRIVIAL_ISSUES)]
    except Exception as exc:
        return [f"[HOOK] Linter indisponível: {exc}"]

def _run_sandbox_in_hook(code: str) -> list[str]:
    """Executa o código isolado para pegar erros de runtime (OSL-18)."""
    import subprocess
    import sys
    try:
        from engine.tools.code_sandbox import stage_code
        tmp_path = stage_code(code, stem="hook_check")
        res = subprocess.run([sys.executable, "-I", str(tmp_path)],
            capture_output=True, text=True, timeout=5
        )
        if res.returncode != 0:
            lines =[l.strip() for l in res.stderr.splitlines() if l.strip()]
            return [f"[RUN] Erro de runtime: {lines[-1] if lines else 'desconhecido'}"]
        return[]
    except subprocess.TimeoutExpired:
        return ["[RUN] Timeout — possível loop infinito."]
    except Exception as e:
        return [f"[RUN] Falha no isolamento: {e}"]


# ---------------------------------------------------------------------------
# Acionar assembler e substituir o bloco no output (OSL-4)
# ---------------------------------------------------------------------------

def _run_assembler_fix(
    task: str,
    broken_code: str,
    issues: list[str],
    bridge: "SiCDoxBridge",
    validator: Any,
    max_retries: int,
    run_isolated: bool,
    original_output: str,
) -> str:
    """Chama CodeAssembler e substitui o bloco de código no output.

    Se o assembler não conseguir corrigir, retorna o output original
    com um aviso inline — nunca falha silenciosamente para o usuário.
    """
    try:
        from engine.thinking.assembler import CodeAssembler  # lazy (OSL-3)

        asm    = CodeAssembler(bridge, validator, max_retries=max_retries, run_isolated=run_isolated)
        result = asm.assemble(task)

    except Exception as exc:
        # OSL-15: assembler indisponível → preserva output + aviso
        warning = f"\n\n[!] [HOOK] Assembler indisponível: {exc}"
        return original_output + warning

    if not result["success"]:
        # Assembler tentou mas não resolveu → output original + issues
        issues_text = "\n".join(f"  • {i}" for i in issues[:5])
        warning = (
            f"\n\n[!] [DIAG] {len(issues)} issue(s) detectada(s) no código gerado:\n"
            f"{issues_text}"
        )
        return original_output + warning

    fixed_code = result["output"]

    # ── Substitui o bloco de código no output original ─────────────
    # Tenta manter o texto explicativo que veio antes/depois do bloco.
    new_block = f"```python\n{fixed_code}\n```"

    # 1ª tentativa: substituir bloco [code-begin]...[code-end]
    patched, n = _RE_TAGGED.subn(
        f"[code-begin]\n{fixed_code}\n[code-end]",
        original_output,
        count=1,
    )
    if n == 0:
        # 2ª tentativa: substituir bloco ```python ... ```
        patched, n = _RE_FENCED.subn(new_block, original_output, count=1)

    if n == 0:
        # Sem bloco reconhecível para substituir — anexa o fix
        patched = original_output + f"\n\n[HOOK] Código corrigido:\n{new_block}"

    attempts = result.get("attempts", "?")
    # Se o bloco original estava truncado, descarta o texto introdutório
    # e entrega só o código corrigido — mais limpo para o usuário
    if n == 0 or (original_output.count("```") % 2) == 1:
        return f"```python\n{fixed_code}\n```\n\n[✓] [DIAG] Código validado pelo hook ({attempts} tentativa(s))."
    patched += f"\n\n[✓] [DIAG] Código validado pelo hook ({attempts} tentativa(s))."
    return patched
    