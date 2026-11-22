# -*- coding: utf-8 -*-
"""Adapter ``Task -> (ok, feedback)`` para a fase SANDBOX.

Backend por linguagem:
    python/py     → engine.tools.sandbox_controller.SandboxController
    demais        → engine.tools.qemu_daemon.QemuDaemon (Alpine)

Timeout:
    ``task.spec.timeout_s`` se definido
    senão ``default_timeout_s`` (python) / ``c_timeout_s`` (outros)

Feedback = stdout + stderr concatenados e truncados a ~3000 chars.
Sem isso, um traceback grande estoura o prompt do DRAFT no retry.

God: Ares (execução) + Poseidon (I/O).
"""
from __future__ import annotations

from typing import Callable

from engine.tasks.model import Task

RunnerFn = Callable[[str, list[str], int], tuple[bool, str, str]]
"""``(code, args, timeout) -> (ok, stdout, stderr)``."""

_FEEDBACK_MAX = 3000


def _truncate(s: str) -> str:
    s = (s or "").strip()
    if len(s) <= _FEEDBACK_MAX:
        return s
    return s[:_FEEDBACK_MAX] + "\n[... truncado]"


def _real_python_runner(code: str, args: list[str], timeout: int) -> tuple[bool, str, str]:
    from engine.tools.sandbox_controller import SandboxController
    r = SandboxController().run(code, args=args, timeout=timeout, lang="python")
    return bool(r.success), r.stdout or "", r.stderr or ""


def _real_c_runner(code: str, args: list[str], timeout: int) -> tuple[bool, str, str]:
    from engine.tools.qemu_daemon import QemuDaemon
    d = QemuDaemon()
    if not d.is_running():
        started = d.start(timeout=max(60, timeout))
        if not started:
            return False, "", "QEMU daemon não subiu"
    r = d.run(code, args=args, lang="c", timeout=timeout)
    return bool(r.success), r.stdout or "", r.stderr or ""


def make_sandbox_step(
    *,
    python_runner:     RunnerFn | None = None,
    c_runner:          RunnerFn | None = None,
    default_timeout_s: int = 30,
    c_timeout_s:       int = 60,
    args:              list[str] | None = None,
) -> Callable[[Task], tuple[bool, str]]:
    """Retorna um ``sandbox_step(task) -> (ok, feedback)``."""

    py = python_runner or _real_python_runner
    c  = c_runner or _real_c_runner
    fixed_args = list(args or [])

    def _step(task: Task) -> tuple[bool, str]:
        art = task.artifact("implement") or task.artifact("draft")
        if art is None or not art.code.strip():
            return False, "sandbox: nenhum código para executar"

        lang = (art.lang or task.spec.language or "python").lower()
        is_python = lang in ("python", "py", "python3")
        timeout = task.spec.timeout_s or (
            default_timeout_s if is_python else c_timeout_s
        )
        runner = py if is_python else c

        try:
            ok, out, err = runner(art.code, fixed_args, timeout)
        except Exception as exc:
            return False, f"sandbox exceção: {type(exc).__name__}: {exc}"

        parts: list[str] = []
        if out.strip():
            parts.append("[STDOUT]\n" + out.strip())
        if err.strip():
            parts.append("[STDERR]\n" + err.strip())
        if not parts:
            parts = ["(sandbox sem output)"]

        return bool(ok), _truncate("\n".join(parts))

    return _step


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------
def _run_tests() -> int:
    import sys

    from engine.tasks.model import Task, TaskArtifact, TaskSpec, TaskStatus

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

    def _mk(lang="python", code="print('oi')", timeout_s=None) -> Task:
        t = Task(spec=TaskSpec(goal="g", language=lang, timeout_s=timeout_s))
        t.status = TaskStatus.RUNNING
        t.artifacts["implement"] = TaskArtifact(
            phase="implement", code=code, lang=lang,
        )
        return t

    # ---------- happy path python ----------
    calls: list[tuple] = []

    def py_ok(code, args, timeout):
        calls.append(("py", code, tuple(args), timeout))
        return True, "oi\n", ""

    step = make_sandbox_step(python_runner=py_ok)
    ok, fb = step(_mk())
    _check("python ok: True", ok is True)
    _check("python ok: feedback contém STDOUT", "[STDOUT]" in fb and "oi" in fb)
    _check("python ok: runner chamado 1x", len(calls) == 1)
    _check("python ok: timeout default 30", calls[0][3] == 30)

    # ---------- python falha ----------
    def py_fail(code, args, timeout):
        return False, "", "Traceback: NameError: 'x' is not defined"

    step = make_sandbox_step(python_runner=py_fail)
    ok, fb = step(_mk())
    _check("python fail: False", ok is False)
    _check("python fail: feedback tem STDERR + erro",
           "[STDERR]" in fb and "NameError" in fb)

    # ---------- lang c usa c_runner ----------
    c_calls: list[tuple] = []

    def c_ok(code, args, timeout):
        c_calls.append(("c", code, timeout))
        return True, "hello\n", ""

    def py_should_not(code, args, timeout):
        raise AssertionError("python_runner chamado para lang=c")

    step = make_sandbox_step(python_runner=py_should_not, c_runner=c_ok)
    ok, fb = step(_mk(lang="c", code="int main(){return 0;}"))
    _check("lang=c: ok", ok is True)
    _check("lang=c: c_runner chamado", len(c_calls) == 1)
    _check("lang=c: timeout default 60", c_calls[0][2] == 60)

    # ---------- c++ também cai em c_runner ----------
    c_calls.clear()
    step = make_sandbox_step(python_runner=py_should_not, c_runner=c_ok)
    ok, _ = step(_mk(lang="c++", code="int main(){return 0;}"))
    _check("lang=c++: usa c_runner", ok is True and len(c_calls) == 1)

    # ---------- override por task.spec.timeout_s ----------
    calls.clear()
    step = make_sandbox_step(python_runner=py_ok)
    step(_mk(timeout_s=5))
    _check("timeout override 5", calls[0][3] == 5)

    # ---------- sem código ----------
    t = Task(spec=TaskSpec(goal="g"))
    t.status = TaskStatus.RUNNING
    step = make_sandbox_step(python_runner=py_ok)
    ok, fb = step(t)
    _check("sem código: False", ok is False)
    _check("sem código: mensagem", "nenhum código" in fb)

    # ---------- exceção no runner ----------
    def py_boom(code, args, timeout):
        raise RuntimeError("kaboom")

    step = make_sandbox_step(python_runner=py_boom)
    ok, fb = step(_mk())
    _check("exceção runner: False", ok is False)
    _check("exceção runner: feedback menciona", "kaboom" in fb)

    # ---------- stdout vazio + stderr vazio ----------
    def py_silent(code, args, timeout):
        return True, "", ""

    step = make_sandbox_step(python_runner=py_silent)
    ok, fb = step(_mk())
    _check("silent: ok True", ok is True)
    _check("silent: mensagem placeholder", "sem output" in fb)

    # ---------- truncamento ----------
    def py_big(code, args, timeout):
        return False, "", "E" * 5000

    step = make_sandbox_step(python_runner=py_big)
    ok, fb = step(_mk())
    _check("truncamento: <= 3050 chars", len(fb) <= 3050)
    _check("truncamento: marcador", "[... truncado]" in fb)

    # ---------- args fixos ----------
    calls.clear()
    step = make_sandbox_step(python_runner=py_ok, args=["a", "b"])
    step(_mk())
    _check("args fixos repassados", calls[0][2] == ("a", "b"))

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
    print("Uso: python -m engine.tasks.sandbox_step --test")
    raise SystemExit(1)
