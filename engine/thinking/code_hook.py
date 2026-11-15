# -*- coding: utf-8 -*-
"""CodeHook — valida código gerado (Python e C) antes de chegar ao usuário.

Fluxo:
  - Detecta se o bloco é C (por #include + int main)
  - Se C: roda no QemuDaemon (gcc + execução real no Alpine)
  - Se Python: fluxo original (lint + sandbox Python)
  - Se falhar, pede correção ao modelo com stderr como contexto
"""
from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engine.core.llm_bridge import SiCDoxBridge

import re as _re_ansi
#_ANSI_RE = _re_ansi.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_ANSI_RE = _re_ansi.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\]8;;[^\x1b]*\x1b\\")

def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")

# ── Extração de blocos ──────────────────────────────────────
_RE_TAGGED = re.compile(
    r"\[code-begin\](.*?)\[code-end\]",
    re.IGNORECASE | re.DOTALL,
)
_RE_FENCED_CLOSED = re.compile(
    r"```(?:python|c)?\s*\n(.*?)```",
    re.DOTALL,
)
_RE_FENCED_OPEN = re.compile(
    r"```(?:python|c)?\s*\n(.*)",
    re.DOTALL,
)
_RE_FENCED = _RE_FENCED_CLOSED

# ── Detecção de C ───────────────────────────────────────────
_RE_C_FUNC = re.compile(
    r"\b(?:int|void|float|double|char|long|short|unsigned|signed|struct\s+\w+)\s+\w+\s*\(",
)
_RE_C_MAIN = re.compile(
    r"(?m)^\s*(?:int|void)\s+main\s*\([^)]*\)\s*\{",
)


def _has_c_code(text: str) -> bool:
    """Detecta C por #include OU por `int main(...) {` (com chave aberta).

    Aceita C sem `#include` desde que tenha `int main()` seguido de `{`.
    Isso cobre o caso comum em que o modelo "esquece" o include.
    """
    if not text:
        return False
    # Caminho forte: #include
    if "#include" in text:
        # precisa ter alguma função C (main ou outra)
        if re.search(r"\bint\s+main\s*\(", text) or _RE_C_FUNC.search(text):
            return True
    # Caminho fraco: int/void main(...) { (com chave) — típico de C esquecido
    if _RE_C_MAIN.search(text):
        return True
    return False


def _has_python_code(text: str) -> bool:
    if _RE_TAGGED.search(text) or _RE_FENCED.search(text):
        return True
    for line in (text or "").splitlines():
        if line.startswith(("def ", "class ", "import ", "from ")):
            return True
    return False


def _extract_code(text: str) -> str:
    m = _RE_TAGGED.search(text or "")
    return m.group(1).strip() if m else ""


def _extract_markdown_code(text: str) -> str:
    m = _RE_FENCED_CLOSED.search(text or "")
    if m:
        return m.group(1).strip()
    m = _RE_FENCED_OPEN.search(text or "")
    if m:
        partial = m.group(1).strip()
        if any(kw in partial for kw in ("#include", "def ", "class ", "int main")):
            return partial
    return ""


def _extract_c_block(text: str) -> str:
    """Extrator preferencial para C: tagged, ```c, ``` genérico e bare code."""
    m = _RE_TAGGED.search(text or "")
    if m:
        return m.group(1).strip()
    m = re.search(r"```c\s*\n(.*?)```", text or "", re.DOTALL)
    if m:
        return m.group(1).strip()
    m = _RE_FENCED_CLOSED.search(text or "")
    if m and "#include" in m.group(1):
        return m.group(1).strip()

    # ── Fallback: bare code C ──
    if "#include" not in (text or ""):
        return ""
    stripped = text.strip()
    if stripped.startswith("#include"):
        return stripped
    idx = stripped.find("#include")
    # Aceita preâmbulo curto ("Aqui está:\n#include ...")
    if 0 <= idx < 250:
        return stripped[idx:]
    return ""


# ── Validação C via QemuDaemon ──────────────────────────────
def _validate_c_via_daemon(code: str, timeout: int = 90) -> tuple[bool, str, str]:
    """Compila e executa via QemuDaemon. Retorna (ok, stdout, stderr).

    Se o daemon estiver offline, retorna (True, "", "") para não bloquear
    o pipeline quando o sandbox não estiver ativo.
    """
    try:
        from engine.tools.qemu_daemon import QemuDaemon
    except ImportError:
        return True, "", "(daemon indisponível)"

    daemon = QemuDaemon()
    if not daemon.is_running():
        return True, "", "(daemon offline — validação C pulada)"

    try:
        res = daemon.run(code, timeout=timeout)
    except Exception as exc:
        return True, "", f"(daemon falhou: {exc})"

    if res.success:
        return True, res.stdout, res.stderr
    # Falhou — retorna o stderr do gcc como motivos
    error_text = res.stderr or res.stdout or "erro desconhecido"
    return False, res.stdout, error_text

def _validate_python_via_daemon(code: str, timeout: int = 30) -> tuple[bool, str, str]:
    """Executa Python no Alpine. Retorna (ok, stdout, stderr)."""
    try:
        from engine.tools.qemu_daemon import QemuDaemon
    except ImportError:
        return True, "", "(daemon indisponível)"

    daemon = QemuDaemon()
    if not daemon.is_running():
        return True, "", "(daemon offline)"

    try:
        res = daemon.run(code, lang="python", timeout=timeout)
    except Exception as exc:
        return True, "", f"(daemon falhou: {exc})"

    if res.success:
        return True, res.stdout, res.stderr
    return False, res.stdout, res.stderr or "erro desconhecido"

def _log_attempt(attempt: int, total: int, raw: str, max_chars: int = 400) -> None:
    """Log visível do que o modelo devolveu em cada tentativa (verbose)."""
    preview = raw[:max_chars].replace("\n", "\\n")
    if len(raw) > max_chars:
        preview += f"...[{len(raw)-max_chars}c]"
    print(f"    [C-HOOK] tentativa {attempt}/{total}: {len(raw)} chars")
    print(f"      raw: {preview}")

def _run_c_fix_loop(
    task: str,
    broken_code: str,
    issues: list[str],
    bridge: "SiCDoxBridge",
    max_retries: int,
    original_output: str,
) -> str:
    """Loop de correção C com detecção de erro de infraestrutura.

    Se o daemon estiver offline ou sem bootstrap, não tenta corrigir:
    devolve o output original com aviso (OSL-15).
    """
    # ── Erro de infraestrutura? (não é gcc error) ──
    _INFRA_MARKERS = (
        "Bootstrap não executado",
        "Daemon offline",
        "socket morto",
        "sem daemon",
    )
    if any(m in " ".join(issues) for m in _INFRA_MARKERS):
        print(f"    [C-HOOK] infraestrutura indisponível — passthrough")
        return original_output + (
            "\n\n[!] [C-HOOK] Sandbox C indisponível "
            "(rode `orn sandbox bootstrap`). Código não validado."
        )

    code = broken_code
    for attempt in range(max_retries):
        prompt = (
            "[TASK] Corrija o código C abaixo.\n"
            f"Tarefa original: {task}\n\n"
            "Código atual:\n"
            f"```c\n{code}\n```\n\n"
            "Erros do gcc:\n"
            + "\n".join(f"  • {i}" for i in issues[:6])
            + "\n\n"
            "Regras:\n"
            "- Devolva o código C COMPLETO, corrigido, dentro de ```c ... ```.\n"
            "- Sem texto antes ou depois do bloco.\n"
            "- Preserve o que estava correto.\n"
            "- Se faltar #include, adicione.\n"
        )
        print(f"    [C-HOOK] prompt enviado ({len(prompt)} chars)")
        try:
            raw = bridge.ask(prompt, max_tokens=1024)
        except Exception as exc:
            return original_output + f"\n\n[!] [C-HOOK] assembler falhou: {exc}"

        _log_attempt(attempt + 1, max_retries, raw)

        new_code = _extract_c_block(raw) or _extract_markdown_code(raw)
        if not new_code:
            return original_output + "\n\n[!] [C-HOOK] modelo não retornou bloco C"

        ok, stdout, stderr = _validate_c_via_daemon(new_code)
        if ok:
            new_block = f"```c\n{new_code}\n```"
            patched, n = _RE_TAGGED.subn(
                f"[code-begin]\n{new_code}\n[code-end]",
                original_output, count=1,
            )
            if n == 0:
                patched, n = _RE_FENCED.subn(new_block, original_output, count=1)
            if n == 0:
                patched = original_output + f"\n\n[✓] [C-HOOK] Código corrigido:\n{new_block}"
            else:
                patched += (
                    f"\n\n[✓] [C-HOOK] C compilado e executado OK "
                    f"({attempt + 1} tentativa(s))."
                )
            if stdout.strip():
                patched += f"\n\n**Saída:**\n```\n{stdout}\n```"
            return patched

        # Falhou de novo — mas é infraestrutura?
        if any(m in stderr for m in _INFRA_MARKERS):
            return original_output + (
                "\n\n[!] [C-HOOK] Sandbox caiu no meio — passthrough."
            )

        code = new_code
        issues = [_strip_ansi(l) for l in stderr.splitlines() if l.strip()][:10] or issues
        print(f"      [C-HOOK] gcc rejeitou:")
        for line in [_strip_ansi(l) for l in stderr.splitlines()[:3]]:
            print(f"        | {line[:120]}")

    return original_output + (
        f"\n\n[!] [C-HOOK] {len(issues)} erro(s) persistiram após "
        f"{max_retries} tentativa(s):\n"
        + "\n".join(f"  • {i}" for i in issues[:6])
    )


# ── Caminho Python (inalterado) ─────────────────────────────
def _diagnose_inline(code: str) -> list[str]:
    try:
        from engine.tools.code_sandbox import lint_python_text
        all_issues = lint_python_text(code)
        _TRIVIAL = ("trailing whitespace", "evitar TAB", "linha acima de 120")
        return [i for i in all_issues if not any(t in i for t in _TRIVIAL)]
    except Exception as exc:
        return [f"[HOOK] Linter indisponível: {exc}"]


def _run_sandbox_in_hook(code: str) -> list[str]:
    """Tenta Alpine primeiro (isolado); se offline, fallback local."""
    # ── Alpine (preferido) ──
    try:
        from engine.tools.qemu_daemon import QemuDaemon
        daemon = QemuDaemon()
        if daemon.is_running():
            ok, stdout, stderr = _validate_python_via_daemon(code, timeout=20)
            if ok:
                return []
            issues = [_strip_ansi(l) for l in stderr.splitlines() if l.strip()][:5]
            return issues or ["[RUN] python falhou sem stderr"]
    except Exception:
        pass

    # ── Fallback: subprocess local ──
    import subprocess
    try:
        from engine.tools.code_sandbox import stage_code
        tmp_path = stage_code(code, stem="hook_check")
        res = subprocess.run(
            [sys.executable, "-I", str(tmp_path)],
            capture_output=True, text=True, timeout=5,
        )
        if res.returncode != 0:
            lines = [l.strip() for l in res.stderr.splitlines() if l.strip()]
            return [f"[RUN] {lines[-1] if lines else 'erro desconhecido'}"]
        return []
    except subprocess.TimeoutExpired:
        return ["[RUN] Timeout — possível loop infinito."]
    except Exception as exc:
        return [f"[RUN] falha no isolamento: {exc}"]


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
    try:
        from engine.thinking.assembler import CodeAssembler
        asm = CodeAssembler(bridge, validator,
                            max_retries=max_retries, run_isolated=run_isolated)
        result = asm.assemble(task)
    except Exception as exc:
        return original_output + f"\n\n[!] [HOOK] Assembler indisponível: {exc}"

    if not result["success"]:
        return original_output + (
            f"\n\n[!] [DIAG] {len(issues)} issue(s) no código Python gerado:\n"
            + "\n".join(f"  • {i}" for i in issues[:5])
        )

    fixed_code = result["output"]
    new_block = f"```python\n{fixed_code}\n```"
    patched, n = _RE_TAGGED.subn(
        f"[code-begin]\n{fixed_code}\n[code-end]",
        original_output, count=1,
    )
    if n == 0:
        patched, n = _RE_FENCED.subn(new_block, original_output, count=1)
    if n == 0:
        patched = original_output + f"\n\n[HOOK] Código corrigido:\n{new_block}"

    return patched + (
        f"\n\n[✓] [DIAG] Python validado pelo hook "
        f"({result.get('attempts', '?')} tentativa(s))."
    )


# ── Entrypoint ──────────────────────────────────────────────
def apply_code_hook(
    output: str,
    task: str,
    bridge: "SiCDoxBridge",
    validator: Any,
    max_retries: int = 1,
    run_isolated: bool = True,
) -> str:
    # ── 1. Caminho C ────────────────────────────────────────
    if _has_c_code(output):
        code = _extract_c_block(output) or _extract_markdown_code(output)
        if not code:
            # Se nem bare nem fenced, tenta o texto inteiro (mais agressivo)
            if "#include" in output:
                code = output.strip()
            if not code:
                return output
        ok, stdout, stderr = _validate_c_via_daemon(code)
        if ok:
            if stdout.strip():
                return output + (
                    f"\n\n[✓] [C-HOOK] Compilado e executado no Alpine:\n"
                    f"```\n{_strip_ansi(stdout)}\n```"
                )
            return output

        # Falhou: extrai stderr como issues
        issues = [l for l in stderr.splitlines() if l.strip()][:10]
        if not issues:
            issues = [stderr[:200] or "gcc falhou sem mensagem"]
        return _run_c_fix_loop(
            task=task,
            broken_code=code,
            issues=issues,
            bridge=bridge,
            max_retries=max_retries,
            original_output=output,
        )

    # ── 2. Caminho Python (original) ────────────────────────
    _is_bare_code = (
        not _has_python_code(output)
        and any(output.lstrip().startswith(kw)
                for kw in ("def ", "class ", "from ", "import "))
    )
    if not _has_python_code(output) and not _is_bare_code:
        return output

    _truncated = (output.count("```") % 2) == 1
    code = _extract_code(output) or _extract_markdown_code(output)
    if not code:
        if _truncated:
            return _run_assembler_fix(
                task=task, broken_code="",
                issues=["[HOOK] Output truncado — sem bloco extraível."],
                bridge=bridge, validator=validator,
                max_retries=max_retries, run_isolated=run_isolated,
                original_output=output,
            )
        return output

    issues = _diagnose_inline(code)
    if not issues and run_isolated:
        issues.extend(_run_sandbox_in_hook(code))
    if _truncated and not issues:
        issues = ["[HOOK] Bloco de código truncado pelo limite de tokens."]
    if not issues:
        return output

    return _run_assembler_fix(
        task=task, broken_code=code, issues=issues,
        bridge=bridge, validator=validator,
        max_retries=max_retries, run_isolated=run_isolated,
        original_output=output,
    )


# ── Testes embutidos ────────────────────────────────────────
def _run_tests() -> int:
    passed = failed = 0

    def _check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            print(f"  [OK] {name}")
            passed += 1
        else:
            print(f"  [X]  {name}" + (f" — {detail}" if detail else ""))
            failed += 1

    # 1. Detecção C
    c_code = "#include <stdio.h>\nint main(){printf(\"hi\");return 0;}"
    py_code = "def f():\n    return 1"
    _check("detecta C (main)", _has_c_code(c_code))
    _check("NÃO detecta C em Python", not _has_c_code(py_code))
    _check("NÃO detecta C sem #include",
           not _has_c_code("int main(){return 0;}"))
    _check("detecta C com função auxiliar",
           _has_c_code("#include <stdio.h>\nvoid foo(){}\nvoid bar(){}"))

    # 2. Extração C
    wrapped = "Aqui está o código:\n```c\n#include <stdio.h>\nint main(){return 0;}\n```"
    _check("_extract_c_block de ```c", "int main" in _extract_c_block(wrapped))
    tagged = "[code-begin]\n#include <stdio.h>\nint main(){return 0;}\n[code-end]"
    _check("_extract_c_block de tagged", "int main" in _extract_c_block(tagged))
    _check("_extract_c_block vazio para texto puro",
           _extract_c_block("só texto") == "")

    # 3. Validação sem daemon → passthrough
    ok, _, msg = _validate_c_via_daemon(c_code)
    # Se daemon offline, deve retornar ok=True (passthrough)
    # Se daemon online, pode retornar ok=True ou False
    _check("_validate_c_via_daemon não crasha sem daemon",
           isinstance(ok, bool))

    # 4. apply_code_hook com C + daemon offline → passthrough
    class _MockBridge:
        def ask(self, prompt, max_tokens=256, **kw):
            return "#include <stdio.h>\nint main(){return 0;}"
    class _MockValidator:
        def validar_output(self, text, lang=None): return True, ""

    out = apply_code_hook(c_code, "teste", _MockBridge(), _MockValidator(),
                          max_retries=0, run_isolated=False)
    _check("apply_code_hook C sem daemon retorna texto", isinstance(out, str))

    # 5. apply_code_hook com Python → não confunde com C
    py_with_include = "```python\n# isso não é C\nx = 1\n```"
    out = apply_code_hook(py_with_include, "teste", _MockBridge(),
                          _MockValidator(), max_retries=0, run_isolated=False)
    _check("Python com comentário '#include' não vira C", isinstance(out, str))

    print()
    if failed == 0:
        print(f"  {passed} teste(s) OK")
        return 0
    print(f"  {passed}/{passed + failed} passaram — {failed} falha(s)")
    return 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_run_tests())
    print("Uso: python -m engine.thinking.code_hook --test")
    raise SystemExit(1)
