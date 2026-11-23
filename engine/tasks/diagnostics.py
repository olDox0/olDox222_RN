# -*- coding: utf-8 -*-
# doxoade/engine/tasks/diagnostics.py
"""
Sondas de saúde do sistema de tarefas (ProDeNov 3.1.6 / 3.1.8 / 3.1.9).

check_health()  → {cli, server, store_writable, events_contract, tasks_module, all_ok}
probe_task(id)  → estado, fase, última transição
probe_server()  → is_server_online + latência + status()

--test          → testes in-file. Nenhuma escrita destrutiva.
"""

from __future__ import annotations
import time
from typing import Any

def probe_corrupt() -> list[dict[str, Any]]:
    """Varre DEFAULT_ROOT/*/state.json e retorna os ilegíveis (TASK_E04)."""
    import json as _json
    out: list[dict[str, Any]] = []
    try:
        from engine.tasks.store import DEFAULT_ROOT
    except Exception:
        return out
    if not DEFAULT_ROOT.exists():
        return out
    for d in sorted(DEFAULT_ROOT.iterdir()):
        if not d.is_dir():
            continue
        sp = d / "state.json"
        if not sp.exists():
            out.append({"task_id": d.name, "error": "state.json ausente"})
            continue
        try:
            _json.loads(sp.read_text(encoding="utf-8"))
        except Exception as exc:
            out.append({
                "task_id": d.name,
                "error": f"{type(exc).__name__}: {exc}",
            })
    return out

def check_health() -> dict[str, Any]:
    out: dict[str, Any] = {
        "cli": _check_cli(),
        "server": _check_server(),
        "store_writable": _check_store(),
        "events_contract": _check_events_contract(),
        "tasks_module": _check_tasks_module(),
        "store_clean": not bool(probe_corrupt()),
    }
    out["all_ok"] = all(bool(v) for v in out.values() if isinstance(v, bool))
    return out


def _check_cli() -> bool:
    try:
        from engine.tasks.cli import task_group  # noqa: F401
        return True
    except Exception:
        return False


def _check_server() -> bool:
    try:
        from engine.tools.server_client import is_server_online
        return bool(is_server_online())
    except Exception:
        return False


def _check_store() -> bool:
    try:
        from pathlib import Path
        from engine.tasks.store import TaskStore, DEFAULT_ROOT
        root = Path(DEFAULT_ROOT)
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".diag_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        TaskStore(root=root)  # noqa: F841
        return True
    except Exception:
        return False


def _check_events_contract() -> bool:
    """Sonda TASK_E06 — round-trip de kinds de tarefa."""
    try:
        from engine.api.events import StreamEvent, to_ndjson, parse_ndjson_line
    except Exception:
        return False
    for k in ("task_start", "phase_start", "phase_done", "phase_error",
              "sandbox_start", "sandbox_done", "task_done"):
        ev = StreamEvent(kind=k, task_id="probe", phase="p")  # type: ignore[arg-type]
        back = parse_ndjson_line(to_ndjson(ev))
        if back is None or back.kind != k:
            return False
    return True


def _check_tasks_module() -> bool:
    try:
        import engine.tasks  # noqa: F401
        return True
    except Exception:
        return False


def probe_task(task_id: str) -> dict[str, Any]:
    try:
        from engine.tasks.store import TaskStore, DEFAULT_ROOT
        t = TaskStore(root=DEFAULT_ROOT).load(task_id)
        return {
            "id": t.id, "status": t.status.value,
            "phase": t.current_phase, "attempts": t.attempts,
            "created_at": t.created_at, "errors": list(t.errors),
        }
    except FileNotFoundError:
        return {"error": f"task não encontrada: {task_id}"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def probe_server() -> dict[str, Any]:
    try:
        from engine.tools.server_client import is_server_online, status
        if not is_server_online():
            return {"online": False}
        t0 = time.monotonic()
        st = status()
        return {"online": True,
                "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                "status": st}
    except Exception as exc:
        return {"online": False, "error": f"{type(exc).__name__}: {exc}"}


def render_health(h: dict[str, Any]) -> str:
    lines = ["HEALTH:"]
    for k in ("cli", "server", "store_writable",
              "events_contract", "tasks_module", "store_clean"):
        lines.append(f"  {k:<18} {'OK' if h.get(k) else 'FALHA'}")
    lines.append(f"  {'all_ok':<18} {h.get('all_ok')}")
    return "\n".join(lines)


def _run_tests() -> int:
    passed = failed = 0
    def _chk(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            print(f"  [OK] {name}"); passed += 1
        else:
            print(f"  [X]  {name}" + (f" — {detail}" if detail else "")); failed += 1
    h = check_health()
    _chk("check_health tem 5 + all_ok",
         {"cli", "server", "store_writable", "events_contract",
          "tasks_module", "all_ok"} <= set(h))
    _chk("cli importa", h["cli"])
    _chk("tasks_module importa", h["tasks_module"])
    _chk("store gravável", h["store_writable"])
    _chk("events_contract (pós Cap 1)", h["events_contract"])
    _chk("store_clean (sem corrupção)", h["store_clean"])
    _chk("probe_corrupt é lista", isinstance(probe_corrupt(), list))
    _chk("probe_server dict", isinstance(probe_server(), dict))
    _chk("probe_task(missing) → error",
         "error" in probe_task("__nao_existe__"))
    print()
    if failed == 0:
        print(f"  {passed} teste(s) OK"); return 0
    print(f"  {passed}/{passed + failed} — {failed} falha(s)"); return 1


if __name__ == "__main__":
    import sys, json
    if "--test" in sys.argv:
        raise SystemExit(_run_tests())
    if "--probe-server" in sys.argv:
        print(json.dumps(probe_server(), indent=2, ensure_ascii=False))
        raise SystemExit(0)
    if "--probe-task" in sys.argv:
        i = sys.argv.index("--probe-task")
        if i + 1 < len(sys.argv):
            print(json.dumps(probe_task(sys.argv[i + 1]),
                             indent=2, ensure_ascii=False))
            raise SystemExit(0)
        print("uso: --probe-task <id>"); raise SystemExit(1)
    print(render_health(check_health()))
