# -*- coding: utf-8 -*-
"""Persistência de tarefas.

Layout::

    .orn/tasks/<task_id>/
        state.json          # snapshot atômico (fonte da verdade)
        events.ndjson       # log append-only
        artifacts/
            plan.txt | plan.json
            draft.txt | draft.py
            implement.txt | implement.py
            sandbox.txt
            present.txt

Gravações de ``state.json`` são atômicas (tmp + fsync + ``os.replace``).
Nada aqui executa código nem chama modelo.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from engine.tasks.model import (
    SCHEMA_VERSION,
    Task,
    TaskArtifact,
    TaskSpec,
    TaskStatus,
    new_task_id,
    now,
)

DEFAULT_ROOT: Path = Path(".orn") / "tasks"

_EXT_BY_LANG: dict[str, str] = {
    "python": ".py", "py": ".py",
    "c": ".c", "h": ".h",
    "c++": ".cpp", "cpp": ".cpp",
    "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts",
    "rust": ".rs", "go": ".go",
    "text": ".txt", "": ".txt",
}


def _ext_for_lang(lang: str) -> str:
    return _EXT_BY_LANG.get((lang or "").lower(), ".txt")


class TaskStore:
    """Store de tarefas em disco. Idempotente e seguro para uso concorrente
    *entre processos* (graças ao write atômico), mas não trata locks entre
    threads — um ``TaskRunner`` por processo (decisão de MVP)."""

    def __init__(self, root: str | Path = DEFAULT_ROOT) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # paths
    # ------------------------------------------------------------------
    def _task_dir(self, task_id: str) -> Path:
        if not task_id or task_id in (".", "..") or "/" in task_id or "\\" in task_id:
            raise ValueError(f"task_id inválido: {task_id!r}")
        return self.root / task_id

    def _state_path(self, task_id: str) -> Path:
        return self._task_dir(task_id) / "state.json"

    def _events_path(self, task_id: str) -> Path:
        return self._task_dir(task_id) / "events.ndjson"

    def _artifacts_dir(self, task_id: str) -> Path:
        return self._task_dir(task_id) / "artifacts"

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def new(self, spec: TaskSpec) -> Task:
        if not spec.id:
            spec.id = new_task_id()
        d = self._task_dir(spec.id)
        if d.exists():
            raise FileExistsError(f"já existe tarefa: {spec.id}")
        d.mkdir(parents=True)
        self._artifacts_dir(spec.id).mkdir()
        self._events_path(spec.id).touch()

        task = Task(spec=spec)
        self.save(task)
        self.append_event(task, {"event": "task_created", "ts": now(),
                                 "goal": spec.goal})
        return task

    def load(self, task_id: str) -> Task:
        p = self._state_path(task_id)
        if not p.exists():
            raise FileNotFoundError(f"tarefa não encontrada: {task_id}")
        raw = json.loads(p.read_text(encoding="utf-8"))
        schema = raw.get("schema")
        if schema != SCHEMA_VERSION:
            raise ValueError(
                f"schema incompatível em {p}: {schema!r} != {SCHEMA_VERSION}"
            )
        return Task.from_dict(raw)

    def save(self, task: Task) -> None:
        task.updated_at = now()
        self._atomic_write_json(self._state_path(task.id), task.to_dict())

    def append_event(self, task: Task, ev: dict) -> None:
        p = self._events_path(task.id)
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(ev, ensure_ascii=False) + "\n"
        with p.open("a", encoding="utf-8") as f:
            f.write(line)

    def save_artifact(self, task: Task, art: TaskArtifact) -> list[Path]:
        d = self._artifacts_dir(task.id)
        d.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []

        if art.content:
            p = d / f"{art.phase}.txt"
            p.write_text(art.content, encoding="utf-8")
            written.append(p)

        if art.code:
            p = d / f"{art.phase}{_ext_for_lang(art.lang)}"
            p.write_text(art.code, encoding="utf-8")
            written.append(p)

        plan_obj = art.meta.get("plan")
        if art.phase == "plan" and isinstance(plan_obj, dict):
            p = d / "plan.json"
            p.write_text(
                json.dumps(plan_obj, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            written.append(p)

        return written

    def list(self, status: TaskStatus | None = None) -> list[Task]:
        out: list[Task] = []
        if not self.root.exists():
            return out
        for child in sorted(self.root.iterdir()):
            if not child.is_dir():
                continue
            sp = child / "state.json"
            if not sp.exists():
                continue
            try:
                raw = json.loads(sp.read_text(encoding="utf-8"))
                task = Task.from_dict(raw)
            except Exception:
                continue
            if status is not None and task.status != status:
                continue
            out.append(task)
        return out

    def exists(self, task_id: str) -> bool:
        try:
            return self._state_path(task_id).exists()
        except ValueError:
            return False

    def delete(self, task_id: str) -> bool:
        """Remove o diretório inteiro da tarefa. Usado por ``orn task abort``."""
        d = self._task_dir(task_id)
        if not d.exists():
            return False
        for f in sorted(d.rglob("*"), reverse=True):
            try:
                if f.is_dir():
                    f.rmdir()
                else:
                    f.unlink()
            except OSError:
                pass
        try:
            d.rmdir()
        except OSError:
            return False
        return True

    # ------------------------------------------------------------------
    # atomic write
    # ------------------------------------------------------------------
    def _atomic_write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------
def _run_tests() -> int:
    import shutil

    from engine.tasks.model import (
        can_transition_phase,
        can_transition_status,
        new_task_id,
    )

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

    tmp = Path(tempfile.mkdtemp(prefix="orn_tasks_test_"))
    try:
        store = TaskStore(tmp)

        # --- criação ---
        spec = TaskSpec(goal="soma dois números", language="python")
        task = store.new(spec)
        _check("id gerado", bool(task.id) and len(task.id) >= 20, task.id)
        _check("id contém '-'", "-" in task.id)
        _check("state.json existe", store._state_path(task.id).exists())
        _check("events.ndjson existe", store._events_path(task.id).exists())
        _check("artifacts/ existe", store._artifacts_dir(task.id).is_dir())
        _check("status inicial=PENDING", task.status == TaskStatus.PENDING)
        _check("phase inicial=plan", task.current_phase == "plan")
        _check("exists true", store.exists(task.id))
        _check("exists false (id inexistente)",
               not store.exists("nao-existe-000000"))

        # --- load round-trip ---
        t2 = store.load(task.id)
        _check("load preserva id", t2.id == task.id)
        _check("load preserva goal", t2.spec.goal == "soma dois números")
        _check("load status", t2.status == TaskStatus.PENDING)

        # --- mutate + save + load ---
        t2.set_status(TaskStatus.RUNNING)
        t2.set_phase("draft")
        t2.attempts = 1
        t2.errors.append("erro teste")
        store.save(t2)
        t3 = store.load(task.id)
        _check("save status=RUNNING", t3.status == TaskStatus.RUNNING)
        _check("save phase=draft", t3.current_phase == "draft")
        _check("save attempts=1", t3.attempts == 1)
        _check("save errors", t3.errors == ["erro teste"])

        # --- eventos ---
        n_before = store._events_path(task.id).read_text().count("\n")
        store.append_event(task, {"event": "phase_start", "phase": "draft"})
        store.append_event(task, {"event": "phase_done",  "phase": "draft"})
        n_after = store._events_path(task.id).read_text().count("\n")
        _check("append_event +2", n_after == n_before + 2)

        # --- artefatos ---
        art = TaskArtifact(
            phase="draft",
            content="rascunho",
            code="print('oi')",
            lang="python",
        )
        store.save_artifact(task, art)
        adir = store._artifacts_dir(task.id)
        _check("draft.txt escrito", (adir / "draft.txt").exists())
        _check("draft.py escrito",  (adir / "draft.py").exists())

        art_plan = TaskArtifact(
            phase="plan",
            content="{}",
            meta={"plan": {"understanding": "x", "files": []}},
        )
        store.save_artifact(task, art_plan)
        _check("plan.json escrito", (adir / "plan.json").exists())
        plan_loaded = json.loads((adir / "plan.json").read_text(encoding="utf-8"))
        _check("plan.json preserva chaves",
               plan_loaded.get("understanding") == "x")

        # --- list ---
        _check("list all == 1", len(store.list()) == 1)
        _check("list PENDING == 0", len(store.list(TaskStatus.PENDING)) == 0)
        _check("list RUNNING == 1", len(store.list(TaskStatus.RUNNING)) == 1)

        # --- path traversal ---
        try:
            store.load("../etc/passwd")
            _check("path traversal bloqueado", False, "não levantou")
        except ValueError:
            _check("path traversal bloqueado", True)
        except FileNotFoundError:
            _check("path traversal bloqueado", False, "levantou FNF, não ValueError")

        # --- transições (delegação de responsabilidade ao model) ---
        _check("status PENDING→RUNNING",
               can_transition_status(TaskStatus.PENDING, TaskStatus.RUNNING))
        _check("status DONE→RUNNING NEG",
               not can_transition_status(TaskStatus.DONE, TaskStatus.RUNNING))
        _check("status BLOCKED→RUNNING",
               can_transition_status(TaskStatus.BLOCKED, TaskStatus.RUNNING))
        _check("phase sandbox→draft",
               can_transition_phase("sandbox", "draft"))
        _check("phase implement→draft",
               can_transition_phase("implement", "draft"))
        _check("phase plan→present NEG",
               not can_transition_phase("plan", "present"))
        _check("phase present sem saída",
               can_transition_phase("present", "draft") is False)

        # --- set_status/set_phase rejeitam transição inválida ---
        task_done = store.load(task.id)
        task_done.status = TaskStatus.DONE
        try:
            task_done.set_status(TaskStatus.RUNNING)
            _check("set_status rejeita DONE→RUNNING", False)
        except ValueError:
            _check("set_status rejeita DONE→RUNNING", True)
        try:
            task_done.set_phase("present")
            _check("set_phase rejeita draft→present", False)
        except ValueError:
            _check("set_phase rejeita draft→present", True)

        # --- unicidade de new_task_id ---
        ids = {new_task_id() for _ in range(50)}
        _check("new_task_id único (50)", len(ids) == 50)

        # --- schema mismatch ---
        sp = store._state_path(task.id)
        raw = json.loads(sp.read_text(encoding="utf-8"))
        raw["schema"] = 999
        sp.write_text(json.dumps(raw), encoding="utf-8")
        try:
            store.load(task.id)
            _check("schema mismatch rejeita", False)
        except ValueError:
            _check("schema mismatch rejeita", True)

        # --- from_dict sem spec ---
        try:
            Task.from_dict({"status": "pending"})
            _check("from_dict sem spec falha", False)
        except ValueError:
            _check("from_dict sem spec falha", True)

        # --- delete ---
        _check("delete existente", store.delete(task.id) is True)
        _check("delete some state.json",
               not store._state_path(task.id).exists())
        _check("delete idempotente", store.delete(task.id) is False)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failed == 0:
        print(f"  {passed} teste(s) OK")
        return 0
    print(f"  {passed}/{passed + failed} passaram — {failed} falha(s)")
    return 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_run_tests())
    print("Uso: python -m engine.tasks.store --test")
    raise SystemExit(1)
