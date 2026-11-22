# -*- coding: utf-8 -*-
"""Factory do ``code_hook`` do IMPLEMENT.

O runner chama ``code_hook(code, task) -> str``. Fechamos sobre
``bridge``/``validator`` porque ``apply_code_hook`` do projeto exige ambos.

Sempre com ``run_isolated=False``: a fase SANDBOX é a única porta de
execução. O hook só enriquece/valida estaticamente o código.
"""
from __future__ import annotations
from typing import Any, Callable
from engine.tasks.model import Task
from engine.tasks.runner import _extract_code_block

Applier = Callable[..., str]

def _real_applier(
    code: str,
    *,
    task,
    bridge,
    validator,
    max_retries: int,
    run_isolated: bool,
) -> str:
    from engine.thinking.code_hook import apply_code_hook
    return apply_code_hook(
        output=code,
        task=task,
        bridge=bridge,
        validator=validator,
        max_retries=max_retries,
        run_isolated=run_isolated,
    )

def make_code_hook(
    *,
    bridge: Any = None,
    validator: Any = None,
    applier: Applier | None = None,
    max_retries: int = 0,
) -> Callable[[str, Task], str]:
    apply_fn = applier or _real_applier
    def _hook(code: str, task: Task) -> str:
        # Se for C/C++, não aciona validação isolada prévia para evitar duplicidade com SANDBOX
        if task.spec.language in ("c", "cpp", "c++") and applier is None:
            return code
        try:
            out = apply_fn(
                code,
                task=task.spec.goal,
                bridge=bridge,
                validator=validator,
                max_retries=max_retries,
                run_isolated=False,
            )
        except Exception:
            return code
        if not isinstance(out, str) or not out.strip():
            return code
        clean_code, _ = _extract_code_block(out, task.spec.language)
        return clean_code or code
    return _hook


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------
def _run_tests() -> int:
    import sys

    from engine.tasks.model import Task, TaskSpec

    passed = 0
    failed = 0

    def _check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            print(f"  [OK] {name}")
            passed += 1
        else:
            print(f"  [X]  {name}" + (f" — {detail}" if detail else ""))
            failed += 1

    t = Task(spec=TaskSpec(goal="tarefa X"))

    # ---------- applier substitui código ----------
    captured: dict = {}

    def applier(code, *, task, bridge, validator, max_retries, run_isolated):
        captured["task"] = task
        captured["bridge"] = bridge
        captured["validator"] = validator
        captured["max_retries"] = max_retries
        captured["run_isolated"] = run_isolated
        return code.replace("x", "y")

    bridge = object()
    validator = object()
    hook = make_code_hook(bridge=bridge, validator=validator,
                          applier=applier, max_retries=3)
    out = hook("x=1", t)
    _check("applier: substitui", out == "y=1")
    _check("applier: run_isolated=False",
           captured["run_isolated"] is False)
    _check("applier: bridge repassado", captured["bridge"] is bridge)
    _check("applier: validator repassado", captured["validator"] is validator)
    _check("applier: max_retries=3", captured["max_retries"] == 3)
    _check("applier: task=goal", captured["task"] == "tarefa X")

    # ---------- applier retorna vazio → mantém original ----------
    def applier_empty(*args, **kw):
        return "   "

    hook = make_code_hook(applier=applier_empty)
    _check("applier vazio: mantém original", hook("original", t) == "original")

    # ---------- applier levanta → mantém original ----------
    def applier_boom(*args, **kw):
        raise RuntimeError("boom")

    hook = make_code_hook(applier=applier_boom)
    _check("applier boom: mantém original", hook("original", t) == "original")

    # ---------- applier retorna não-str → mantém original ----------
    def applier_none(*args, **kw):
        return None  # type: ignore[return-value]

    hook = make_code_hook(applier=applier_none)
    _check("applier None: mantém original", hook("original", t) == "original")

    # ---------- sem applier: usa real (mas não executa — só instancia) ----------
    hook = make_code_hook()
    _check("sem applier: callable", callable(hook))

    print()
    if failed == 0:
        print(f"  {passed} teste(s) OK")
        return 0
    print(f"  {passed}/{passed + failed} passaram — {failed} falha(s)")
    return 1


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_run_tests())
    print("Uso: python -m engine.tasks.hooks --test")
    raise SystemExit(1)
