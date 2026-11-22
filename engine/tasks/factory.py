# -*- coding: utf-8 -*-
"""Monta um ``TaskRunner`` pronto para uso real.

Uso no CLI (passo 6):

    from engine.tasks.factory import build_default_runner
    from engine.tasks.store   import TaskStore
    runner = build_default_runner(TaskStore())
    runner.run(task_id)

O ``bridge`` e o ``validator`` são lazy-instanciados só se não forem
passados — permite testes sem carregar modelo.
"""
from __future__ import annotations

from typing import Any, Callable

from engine.tasks.hooks        import make_code_hook
from engine.tasks.runner       import TaskRunner
from engine.tasks.sandbox_step import make_sandbox_step
from engine.tasks.store        import TaskStore


def build_default_runner(
    store: TaskStore,
    *,
    bridge:        Any = None,
    validator:     Any = None,
    emit:          Callable[[dict], None] | None = None,
    sandbox_step:  Callable | None = None,
    code_hook:     Callable | None = None,
    lazy_bridge:   bool = True,
    default_max_tokens: int = 512,   # <-- NOVO
) -> TaskRunner:
    if bridge is None:
        if not lazy_bridge:
            raise ValueError("bridge obrigatório quando lazy_bridge=False")
        from engine.core.llm_bridge import SiCDoxBridge
        bridge = SiCDoxBridge()

    if validator is None:
        from engine.core.logic_filter import SiCDoxValidator
        validator = SiCDoxValidator()

    if sandbox_step is None:
        sandbox_step = make_sandbox_step()

    if code_hook is None:
        code_hook = make_code_hook(bridge=bridge, validator=validator)

    return TaskRunner(
        store=store,
        bridge=bridge,
        validator=validator,
        emit=emit,
        code_hook=code_hook,
        sandbox_step=sandbox_step,
        default_max_tokens=default_max_tokens,
    )


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------
def _run_tests() -> int:
    import sys
    import tempfile
    import shutil
    from pathlib import Path

    from engine.tasks.model import TaskSpec

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

    tmp = Path(tempfile.mkdtemp(prefix="orn_factory_test_"))
    try:
        store = TaskStore(tmp / "tasks")
        spec = TaskSpec(goal="g")
        store.new(spec)

        # ---------- com bridge e validator dummies ----------
        bridge_d = object()
        validator_d = object()
        sb_d = lambda t: (True, "")
        runner = build_default_runner(
            store,
            bridge=bridge_d,
            validator=validator_d,
            sandbox_step=sb_d,
        )
        _check("factory: bridge preservado", runner.bridge is bridge_d)
        _check("factory: validator preservado", runner.validator is validator_d)
        _check("factory: sandbox_step preservado",
               runner._sandbox_step is sb_d)
        _check("factory: code_hook construído",
               callable(runner._code_hook))

        # ---------- sem sandbox_step → constrói default ----------
        runner = build_default_runner(
            store, bridge=bridge_d, validator=validator_d,
        )
        _check("factory: sandbox_step default é callable",
               callable(runner._sandbox_step))

        # ---------- sem code_hook → constrói default ----------
        runner = build_default_runner(
            store, bridge=bridge_d, validator=validator_d,
            sandbox_step=sb_d,
        )
        _check("factory: code_hook default é callable",
               callable(runner._code_hook))

        # ---------- lazy_bridge=False sem bridge → erro ----------
        try:
            build_default_runner(store, lazy_bridge=False)
            _check("factory: lazy_bridge=False exige bridge", False)
        except ValueError:
            _check("factory: lazy_bridge=False exige bridge", True)

        # ---------- lazy_bridge=False sem bridge → erro ----------
        try:
            build_default_runner(store, lazy_bridge=False)
            _check("factory: lazy_bridge=False exige bridge", False)
        except ValueError:
            _check("factory: lazy_bridge=False exige bridge", True)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

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
    print("Uso: python -m engine.tasks.factory --test")
    raise SystemExit(1)
