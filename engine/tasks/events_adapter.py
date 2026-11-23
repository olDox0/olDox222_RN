# -*- coding: utf-8 -*-
# doxoade/engine/tasks/events_adapter.py
"""
Adapter runner-emit(dict) → StreamEvent (Cap 1.6).

Compatível com _create_event_emitter de engine/tasks/cli.py: o runner
emite dicts crus; este adapter traduz para StreamEvent canônico do
engine.api.events. Stateful — aprende task_id do primeiro evento que
o carrega (só o task_start do runner carrega task_id).

TASK_E02: kind desconhecido → retorna None (log + ignora).
"""
from __future__ import annotations

from engine.api.events import StreamEvent


class TaskEventAdapter:
    """Traduz dict do runner → StreamEvent. Aprende task_id do primeiro emit."""

    def __init__(self, task_id: str = "") -> None:
        self._task_id = task_id

    def __call__(self, ev: dict) -> StreamEvent | None:
        if not isinstance(ev, dict):
            return None
        kind = ev.get("event")
        tid = str(ev.get("task_id") or self._task_id)
        if tid:
            self._task_id = tid

        meta: dict = {}
        if "attempt"  in ev: meta["attempt"]  = ev["attempt"]
        if "code_len" in ev: meta["code_len"] = ev["code_len"]
        if "attempts" in ev: meta["attempts"] = ev["attempts"]
        if "status"   in ev: meta["status"]   = ev["status"]
        if "hunks"    in ev: meta["hunks"]    = ev["hunks"]
        if "mode"     in ev: meta["mode"]     = ev["mode"]

        if kind == "task_start":
            return StreamEvent(kind="task_start", task_id=tid,
                               phase=str(ev.get("phase", "")), meta=meta)
        if kind == "task_done":
            return StreamEvent(kind="task_done", task_id=tid,
                               output=str(ev.get("output", "")),
                               elapsed_s=float(ev.get("elapsed_s", 0.0) or 0.0),
                               meta=meta)
        if kind == "phase_start":
            return StreamEvent(kind="phase_start", task_id=tid,
                               phase=str(ev.get("phase", "")), meta=meta)
        if kind == "phase_done":
            return StreamEvent(kind="phase_done", task_id=tid,
                               phase=str(ev.get("phase", "")),
                               output=str(ev.get("output", "")),
                               elapsed_s=float(ev.get("elapsed_s", 0.0) or 0.0),
                               progress=float(ev.get("progress", 0.0) or 0.0),
                               meta=meta)
        if kind == "phase_error":
            return StreamEvent(kind="phase_error", task_id=tid,
                               phase=str(ev.get("phase", "")),
                               error=str(ev.get("reason", "")), meta=meta)
        if kind == "sandbox_start":
            return StreamEvent(kind="sandbox_start", task_id=tid,
                               phase=str(ev.get("phase", "")), meta=meta)
        if kind == "sandbox_done":
            return StreamEvent(kind="sandbox_done", task_id=tid,
                               phase=str(ev.get("phase", "")),
                               output=str(ev.get("output", "")),
                               elapsed_s=float(ev.get("elapsed_s", 0.0) or 0.0),
                               meta=meta)
        return None  # TASK_E02


def _run_tests() -> int:
    passed = failed = 0

    def _chk(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            print(f"  [OK] {name}"); passed += 1
        else:
            print(f"  [X]  {name}" + (f" — {detail}" if detail else "")); failed += 1

    a = TaskEventAdapter()
    ev = a({"event": "task_start", "task_id": "t1", "phase": "plan"})
    _chk("task_start vira StreamEvent", ev is not None and ev.task_id == "t1")

    ev = a({"event": "phase_start", "phase": "draft"})
    _chk("task_id aprendido de task_start anterior",
         ev is not None and ev.task_id == "t1" and ev.phase == "draft")

    ev = a({"event": "phase_done", "phase": "draft", "code_len": 100})
    _chk("meta.code_len preservado",
         ev is not None and ev.meta.get("code_len") == 100)

    ev = a({"event": "phase_error", "phase": "draft", "reason": "boom"})
    _chk("phase_error vira error", ev is not None and ev.error == "boom")

    ev = a({"event": "task_done", "status": "done", "attempts": 2})
    _chk("task_done com meta", ev is not None and ev.meta.get("attempts") == 2)

    ev = a({"event": "kind_inventado"})
    _chk("TASK_E02: kind desconhecido → None", ev is None)

    ev = a("não é dict")
    _chk("não-dict → None", ev is None)

    # ndjson round-trip do adapter
    from engine.api.events import to_ndjson, parse_ndjson_line
    a2 = TaskEventAdapter()
    a2({"event": "task_start", "task_id": "t9"})
    e = a2({"event": "phase_start", "phase": "draft"})
    back = parse_ndjson_line(to_ndjson(e))
    _chk("adapter → ndjson → StreamEvent",
         back is not None and back.task_id == "t9" and back.phase == "draft")

    print()
    if failed == 0:
        print(f"  {passed} teste(s) OK"); return 0
    print(f"  {passed}/{passed + failed} — {failed} falha(s)"); return 1


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_run_tests())
    print("Uso: python -m engine.tasks.events_adapter --test")
    raise SystemExit(1)
