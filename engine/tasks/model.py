# -*- coding: utf-8 -*-
"""Modelos de dados do sistema de tarefas.

Estado puro e serializável. Sem I/O de disco, sem inferência, sem sandbox.
Grafo de transições (status e fase) mora aqui — o runner só chama
``set_status`` / ``set_phase``.

God: Atena (estrutura) + Hades (persistência via ``engine.tasks.store``).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Fases
# ---------------------------------------------------------------------------
Phase = Literal["plan", "draft", "implement", "sandbox", "present"]

PHASES: tuple[Phase, ...] = ("plan", "draft", "implement", "sandbox", "present")

# Grafo de fases. Retry do sandbox volta para DRAFT (decisão de produto).
# Falha de validação no IMPLEMENT também volta para DRAFT.
PHASE_TRANSITIONS: dict[Phase, frozenset[Phase]] = {
    "plan":      frozenset({"draft"}),
    "draft":     frozenset({"implement"}),
    "implement": frozenset({"sandbox", "draft"}),
    "sandbox":   frozenset({"present", "draft", "sandbox"}),
    "present":   frozenset(),  
}

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED  = "paused"
    DONE    = "done"
    BLOCKED = "blocked"
    ABORTED = "aborted"
    FAILED  = "failed"   # confirmar se store.py já usa


STATUS_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.RUNNING, TaskStatus.ABORTED}),
    TaskStatus.RUNNING: frozenset({
        TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.BLOCKED,
        TaskStatus.PAUSED,          # NOVO
        TaskStatus.ABORTED,
    }),
    TaskStatus.PAUSED: frozenset({  # NOVO
        TaskStatus.RUNNING,
        TaskStatus.ABORTED,
    }),
    TaskStatus.BLOCKED: frozenset({TaskStatus.RUNNING, TaskStatus.ABORTED}),
    TaskStatus.DONE:    frozenset(),
    TaskStatus.FAILED:  frozenset(),
    TaskStatus.ABORTED: frozenset(),
}

TERMINAL_STATUSES = frozenset({
    TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.ABORTED,
})


def can_transition_status(cur: TaskStatus, new: TaskStatus) -> bool:
    return new in STATUS_TRANSITIONS.get(cur, frozenset())


def can_transition_phase(cur: Phase, new: Phase) -> bool:
    return new in PHASE_TRANSITIONS.get(cur, frozenset())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now() -> float:
    return time.time()


def new_task_id(ts: float | None = None) -> str:
    """ID ordenável por tempo: ``YYYYMMDD-HHMMSS-<hex6>``."""
    t = time.localtime(ts if ts is not None else time.time())
    return time.strftime("%Y%m%d-%H%M%S", t) + "-" + uuid.uuid4().hex[:6]


def _jsonable(obj: Any) -> Any:
    """Sanitiza ``meta`` para serialização JSON segura."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in obj]
    return str(obj)


# ---------------------------------------------------------------------------
# TaskArtifact
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class TaskArtifact:
    """Artefato produzido por uma fase. ``content`` = texto bruto do modelo,
    ``code`` = código extraído (se houver), ``meta`` = dados estruturados
    (ex.: plano JSON parseado, resultado do sandbox)."""

    phase:   Phase
    content: str = ""
    code:    str = ""
    lang:    str = "python"
    path:    str | None = None
    meta:    dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "phase":   self.phase,
            "content": self.content,
            "code":    self.code,
            "lang":    self.lang,
            "path":    self.path,
            "meta":    _jsonable(self.meta),
        }

    @classmethod
    def from_dict(cls, raw: dict | None) -> "TaskArtifact | None":
        if not isinstance(raw, dict):
            return None
        phase = raw.get("phase")
        if phase not in PHASES:
            return None
        return cls(
            phase=phase,
            content=str(raw.get("content", "")),
            code=str(raw.get("code", "")),
            lang=str(raw.get("lang", "python")),
            path=raw.get("path"),
            meta=dict(raw.get("meta") or {}),
        )


# ---------------------------------------------------------------------------
# TaskSpec
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class TaskSpec:
    """Entrada imutável (na prática) de uma tarefa."""
    goal:        str
    id:          str = ""
    language:    str = "python"
    max_retries: int = 2
    max_tokens:  int | None = None
    timeout_s:   int | None = None          # <-- NOVO (None = default por lang)
    constraints: list[str] = field(default_factory=list)
    created_at:  float = field(default_factory=now)

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "goal":        self.goal,
            "language":    self.language,
            "max_retries": self.max_retries,
            "max_tokens":  self.max_tokens,
            "timeout_s":   self.timeout_s,
            "constraints": list(self.constraints),
            "created_at":  self.created_at,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "TaskSpec":
        if not isinstance(raw, dict):
            raise ValueError("TaskSpec.from_dict: raw não é dict")
        goal = raw.get("goal")
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("TaskSpec.from_dict: goal vazio ou inválido")
        max_tokens_raw = raw.get("max_tokens")
        return cls(
            goal=goal,
            id=str(raw.get("id", "")),
            language=str(raw.get("language", "python")),
            max_retries=int(raw.get("max_retries", 2) or 0),
            max_tokens=(int(max_tokens_raw) if max_tokens_raw is not None else None),
            timeout_s=(int(raw["timeout_s"]) if raw.get("timeout_s") is not None else None),
            constraints=[str(c) for c in (raw.get("constraints") or [])],
            created_at=float(raw.get("created_at", now()) or now()),
        )


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Task:
    """Estado mutável de uma tarefa. ``artifacts`` é chaveado por fase."""

    spec:          TaskSpec
    status:        TaskStatus = TaskStatus.PENDING
    current_phase: Phase = "plan"
    artifacts:     dict[str, TaskArtifact] = field(default_factory=dict)
    attempts:      int = 0
    errors:        list[str] = field(default_factory=list)
    feedback:      str = ""            # <-- NOVO: dica entre retries de DRAFT
    created_at:    float = field(default_factory=now)
    updated_at:    float = field(default_factory=now)



    # ---- conveniência ----
    @property
    def id(self) -> str:
        return self.spec.id

    def artifact(self, phase: str) -> TaskArtifact | None:
        return self.artifacts.get(phase)

    # ---- transições validadas ----
    def set_status(self, new: TaskStatus) -> None:
        if not can_transition_status(self.status, new):
            raise ValueError(
                f"transição de status inválida: {self.status.value} -> {new.value}"
            )
        self.status = new
        self.updated_at = now()

    def set_phase(self, new: Phase) -> None:
        if not can_transition_phase(self.current_phase, new):
            raise ValueError(
                f"transição de fase inválida: {self.current_phase} -> {new}"
            )
        self.current_phase = new
        self.updated_at = now()

    # ---- serialização ----
    def to_dict(self) -> dict:
        return {
            "schema":        SCHEMA_VERSION,
            "spec":          self.spec.to_dict(),
            "status":        self.status.value,
            "current_phase": self.current_phase,
            "artifacts":     {k: v.to_dict() for k, v in self.artifacts.items()},
            "attempts":      self.attempts,
            "errors":        list(self.errors),
            "created_at":    self.created_at,
            "updated_at":    self.updated_at,
            "feedback":   self.feedback,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Task":
        if not isinstance(raw, dict):
            raise ValueError("Task.from_dict: raw não é dict")
        spec_raw = raw.get("spec")
        if not isinstance(spec_raw, dict):
            raise ValueError("Task.from_dict: spec ausente ou inválido")
        spec = TaskSpec.from_dict(spec_raw)

        status_raw = raw.get("status", "pending")
        try:
            status = TaskStatus(status_raw)
        except ValueError:
            raise ValueError(f"Task.from_dict: status inválido: {status_raw!r}")

        phase = raw.get("current_phase", "plan")
        if phase not in PHASES:
            raise ValueError(f"Task.from_dict: phase inválida: {phase!r}")

        artifacts: dict[str, TaskArtifact] = {}
        artifacts_raw = raw.get("artifacts") or {}
        if not isinstance(artifacts_raw, dict):
            raise ValueError("Task.from_dict: artifacts inválido")
        for _k, v in artifacts_raw.items():
            art = TaskArtifact.from_dict(v)
            if art is not None:
                artifacts[art.phase] = art

        return cls(
            spec=spec,
            status=status,
            current_phase=phase,  # type: ignore[arg-type]
            artifacts=artifacts,
            attempts=int(raw.get("attempts", 0) or 0),
            errors=[str(e) for e in (raw.get("errors") or [])],
            created_at=float(raw.get("created_at", now()) or now()),
            updated_at=float(raw.get("updated_at", now()) or now()),
            feedback=str(raw.get("feedback", "")),
        )
