# -*- coding: utf-8 -*-
"""StreamEvent — schema canônico de eventos de inferência.

Consumido por:
  - engine/web/        (HTTP NDJSON)
  - engine/server/     (TCP stream mode — já fala este formato)
  - engine/api/facade  (direct mode)
  - future Doxly plugin (process.start + NDJSON)

Nenhuma dependência de transporte. Só schema + codec.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Iterator, Literal

EventKind = Literal[
    "start", "sources", "chunk", "llm_done", "validated", "done", "error",
    # task-level:
    "task_start", "phase_start", "phase_done", "phase_error",
    "sandbox_start", "sandbox_done", "task_done",
]
@dataclass(slots=True)
class SourceRef:
    category:    str       = ""
    kind:        EventKind = "sources"
    path:        str       = ""
    rank:        float     = 0.0
    request_id:  str       = ""
    snippet:     str       = ""
    title:       str       = ""
    def to_dict(self) -> dict:
        return {
            "path":     self.path,
            "title":    self.title,
            "snippet":  self.snippet,
            "category": self.category,
            "rank":     self.rank,
        }

@dataclass(slots=True)
class StreamEvent:
    kind:       EventKind
    delta:      str     = ""
    output:     str     = ""
    elapsed_s:  float   = 0.0
    error:      str     = ""
    request_id: str     = ""
    chunk_idx:  int     = -1
    model:      str     = ""
    max_tokens: int     = 0
    changed:    bool    = False
    sources:    list    = field(default_factory=list)   # ← novo
    task_id:    str     = ""
    phase:      str     = ""
    progress:   float   = 0.0
    meta:       dict    = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        d = {"event": self.kind}
        if self.kind == "start":
            if self.request_id:  d["request_id"] = self.request_id
            if self.model:       d["model"]      = self.model
            if self.max_tokens:  d["max_tokens"] = self.max_tokens
        elif self.kind == "chunk":
            d["delta"] = self.delta
            if self.chunk_idx >= 0: d["chunk_idx"]  = self.chunk_idx
            if self.request_id:     d["request_id"] = self.request_id
        elif self.kind == "llm_done":
            d["output"]    = self.output
            d["elapsed_s"] = round(float(self.elapsed_s), 3)
            if self.request_id: d["request_id"] = self.request_id
        elif self.kind == "validated":
            d["output"]  = self.output
            d["changed"] = bool(self.changed)
            if self.request_id: d["request_id"] = self.request_id
        elif self.kind == "done":
            d["output"]    = self.output
            d["elapsed_s"] = round(float(self.elapsed_s), 3)
            if self.request_id: d["request_id"] = self.request_id
        elif self.kind == "error":
            d["error"] = self.error
            if self.request_id: d["request_id"] = self.request_id
        elif self.kind == "task_start":
            d["task_id"] = self.task_id
            if self.phase: d["phase"] = self.phase
        elif self.kind == "task_done":
            d["task_id"]   = self.task_id
            d["output"]    = self.output
            d["elapsed_s"] = round(float(self.elapsed_s), 3)
        elif self.kind == "phase_start":
            d["task_id"] = self.task_id
            d["phase"]   = self.phase
        elif self.kind == "phase_done":
            d["task_id"]   = self.task_id
            d["phase"]     = self.phase
            d["output"]    = self.output
            d["elapsed_s"] = round(float(self.elapsed_s), 3)
            if self.progress:
                d["progress"] = round(float(self.progress), 3)
        elif self.kind == "phase_error":
            d["task_id"] = self.task_id
            d["phase"]   = self.phase
            d["error"]   = self.error
        elif self.kind == "sandbox_start":
            d["task_id"] = self.task_id
            d["phase"]   = self.phase
        elif self.kind == "sandbox_done":
            d["task_id"]   = self.task_id
            d["phase"]     = self.phase
            d["output"]    = self.output
            d["elapsed_s"] = round(float(self.elapsed_s), 3)
        if self.meta:
            d["meta"] = self.meta
        if self.sources:
            d["sources"] = [
                {
                    "path":     s.path,
                    "title":    s.title,
                    "snippet":  s.snippet,
                    "category": s.category,
                    "rank":     s.rank,
                }
                for s in self.sources
            ]
        return d

    @classmethod
    def from_raw(cls, raw: dict | None) -> "StreamEvent | None":
        if not isinstance(raw, dict):
            return None
        if "event" in raw:
            kind = raw["event"]
            if kind == "start":
                return cls(
                    kind="start",
                    request_id=str(raw.get("request_id", "")),
                    model=str(raw.get("model", "")),
                    max_tokens=int(raw.get("max_tokens", 0) or 0),
                )
            if kind == "chunk":
                cidx = raw.get("chunk_idx", -1)
                try:
                    cidx = int(cidx)
                except (TypeError, ValueError):
                    cidx = -1
                return cls(
                    kind="chunk",
                    delta=str(raw.get("delta", "")),
                    chunk_idx=cidx,
                    request_id=str(raw.get("request_id", "")),
                )
            if kind == "llm_done":
                return cls(
                    kind="llm_done",
                    output=str(raw.get("output", "")),
                    elapsed_s=float(raw.get("elapsed_s", 0.0) or 0.0),
                    request_id=str(raw.get("request_id", "")),
                )
            if kind == "validated":
                return cls(
                    kind="validated",
                    output=str(raw.get("output", "")),
                    changed=bool(raw.get("changed", False)),
                    request_id=str(raw.get("request_id", "")),
                )
            if kind == "done":
                return cls(
                    kind="done",
                    output=str(raw.get("output", "")),
                    elapsed_s=float(raw.get("elapsed_s", 0.0) or 0.0),
                    request_id=str(raw.get("request_id", "")),
                )
            if kind == "error":
                return cls(
                    kind="error",
                    error=str(raw.get("error", "")),
                    request_id=str(raw.get("request_id", "")),
                )
            if kind == "task_start":
                return cls(kind="task_start",
                           task_id=str(raw.get("task_id", "")),
                           phase=str(raw.get("phase", "")),
                           meta=dict(raw.get("meta") or {}))
            if kind == "task_done":
                return cls(kind="task_done",
                           task_id=str(raw.get("task_id", "")),
                           output=str(raw.get("output", "")),
                           elapsed_s=float(raw.get("elapsed_s", 0.0) or 0.0),
                           meta=dict(raw.get("meta") or {}))
            if kind == "phase_start":
                return cls(kind="phase_start",
                           task_id=str(raw.get("task_id", "")),
                           phase=str(raw.get("phase", "")),
                           meta=dict(raw.get("meta") or {}))
            if kind == "phase_done":
                return cls(kind="phase_done",
                           task_id=str(raw.get("task_id", "")),
                           phase=str(raw.get("phase", "")),
                           output=str(raw.get("output", "")),
                           elapsed_s=float(raw.get("elapsed_s", 0.0) or 0.0),
                           progress=float(raw.get("progress", 0.0) or 0.0),
                           meta=dict(raw.get("meta") or {}))
            if kind == "phase_error":
                return cls(kind="phase_error",
                           task_id=str(raw.get("task_id", "")),
                           phase=str(raw.get("phase", "")),
                           error=str(raw.get("error", "")),
                           meta=dict(raw.get("meta") or {}))
            if kind == "sandbox_start":
                return cls(kind="sandbox_start",
                           task_id=str(raw.get("task_id", "")),
                           phase=str(raw.get("phase", "")),
                           meta=dict(raw.get("meta") or {}))
            if kind == "sandbox_done":
                return cls(kind="sandbox_done",
                           task_id=str(raw.get("task_id", "")),
                           phase=str(raw.get("phase", "")),
                           output=str(raw.get("output", "")),
                           elapsed_s=float(raw.get("elapsed_s", 0.0) or 0.0),
                           meta=dict(raw.get("meta") or {}))
            return None
        # caminho legado: server responde sem "event"
        if "output" in raw and "elapsed_s" in raw:
            return cls(
                kind="done",
                output=str(raw.get("output", "")),
                elapsed_s=float(raw.get("elapsed_s", 0.0) or 0.0),
                error=str(raw.get("error", "") or ""),
            )
        if raw.get("error"):
            return cls(kind="error", error=str(raw.get("error", "")))
        return None


def to_ndjson(event: StreamEvent) -> str:
    return json.dumps(event.to_dict(), ensure_ascii=False) + "\n"


def parse_ndjson_line(line: str) -> StreamEvent | None:
    line = (line or "").strip()
    if not line:
        return None
    try:
        raw = json.loads(line)
    except json.JSONDecodeError:
        return None
    return StreamEvent.from_raw(raw)


def iter_events_from_lines(lines: Iterator[str]) -> Iterator[StreamEvent]:
    for line in lines:
        ev = parse_ndjson_line(line)
        if ev is not None:
            yield ev


# ── testes embutidos ─────────────────────────────────────────
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

    e = StreamEvent(kind="start", request_id="r1", model="qwen", max_tokens=128)
    _check("start to_dict", e.to_dict()["event"] == "start")
    _check("start request_id", e.to_dict()["request_id"] == "r1")
    e2 = StreamEvent.from_raw(e.to_dict())
    _check("start round-trip", e2 is not None and e2.kind == "start")

    e = StreamEvent(kind="chunk", delta="def ", chunk_idx=0, request_id="r1")
    e2 = StreamEvent.from_raw(e.to_dict())
    _check("chunk round-trip", e2 is not None and e2.delta == "def " and e2.chunk_idx == 0)

    e = StreamEvent(kind="done", output="ok", elapsed_s=1.234, request_id="r1")
    e2 = StreamEvent.from_raw(e.to_dict())
    _check("done round-trip", e2 is not None and e2.output == "ok")
    _check("done elapsed_s", e2.elapsed_s == 1.234)

    e = StreamEvent(kind="error", error="boom")
    e2 = StreamEvent.from_raw(e.to_dict())
    _check("error round-trip", e2 is not None and e2.error == "boom")

    legacy = {"output": "hello", "elapsed_s": 2.5, "error": None}
    ev = StreamEvent.from_raw(legacy)
    _check("legacy done", ev is not None and ev.kind == "done" and ev.output == "hello")
    _check("legacy elapsed", ev.elapsed_s == 2.5)

    ev = StreamEvent.from_raw({"error": "offline"})
    _check("legacy error", ev is not None and ev.kind == "error" and ev.error == "offline")

    _check("None → None", StreamEvent.from_raw(None) is None)
    _check("{} → None", StreamEvent.from_raw({}) is None)
    _check("evento desconhecido → None", StreamEvent.from_raw({"event": "??"}) is None)

    line = to_ndjson(StreamEvent(kind="chunk", delta="x"))
    _check("ndjson termina com \\n", line.endswith("\n"))
    ev = parse_ndjson_line(line)
    _check("ndjson parse", ev is not None and ev.delta == "x")
    _check("ndjson vazio → None", parse_ndjson_line("") is None)
    _check("ndjson inválido → None", parse_ndjson_line("not json") is None)

    # chunk_idx=0 não vira -1
    e = StreamEvent(kind="chunk", delta="x", chunk_idx=0)
    e2 = StreamEvent.from_raw(e.to_dict())
    _check("chunk_idx=0 preservado", e2 is not None and e2.chunk_idx == 0)

    # chunk_idx ausente → -1
    e2 = StreamEvent.from_raw({"event": "chunk", "delta": "y"})
    _check("chunk_idx ausente → -1", e2 is not None and e2.chunk_idx == -1)

    # --- task events (TASK_E06 fix) ---
    # task_start
    e = StreamEvent(kind="task_start", task_id="t1", phase="plan")
    d = e.to_dict()
    _check("task_start to_dict", d["event"] == "task_start" and d["task_id"] == "t1")
    e2 = StreamEvent.from_raw(d)
    _check("task_start round-trip", e2 is not None and e2.task_id == "t1" and e2.phase == "plan")
    e2 = parse_ndjson_line(to_ndjson(e))
    _check("task_start ndjson", e2 is not None and e2.kind == "task_start" and e2.task_id == "t1")

    # task_done
    e = StreamEvent(kind="task_done", task_id="t1", output="ok", elapsed_s=1.5)
    d = e.to_dict()
    _check("task_done to_dict", d["task_id"] == "t1" and d["output"] == "ok")
    e2 = StreamEvent.from_raw(d)
    _check("task_done round-trip", e2 is not None and e2.task_id == "t1" and e2.elapsed_s == 1.5)
    e2 = parse_ndjson_line(to_ndjson(e))
    _check("task_done ndjson", e2 is not None and e2.kind == "task_done")

    # phase_start
    e = StreamEvent(kind="phase_start", task_id="t1", phase="draft")
    d = e.to_dict()
    _check("phase_start to_dict", d["phase"] == "draft" and d["task_id"] == "t1")
    e2 = StreamEvent.from_raw(d)
    _check("phase_start round-trip", e2 is not None and e2.phase == "draft")
    e2 = parse_ndjson_line(to_ndjson(e))
    _check("phase_start ndjson", e2 is not None and e2.kind == "phase_start")

    # phase_done
    e = StreamEvent(kind="phase_done", task_id="t1", phase="draft",
                    output="x", elapsed_s=2.0, progress=0.4)
    d = e.to_dict()
    _check("phase_done to_dict", d["phase"] == "draft" and d["progress"] == 0.4)
    e2 = StreamEvent.from_raw(d)
    _check("phase_done round-trip", e2 is not None and e2.progress == 0.4)
    e2 = parse_ndjson_line(to_ndjson(e))
    _check("phase_done ndjson", e2 is not None and e2.kind == "phase_done")

    # phase_error
    e = StreamEvent(kind="phase_error", task_id="t1", phase="draft", error="boom")
    d = e.to_dict()
    _check("phase_error to_dict", d["error"] == "boom" and d["phase"] == "draft")
    e2 = StreamEvent.from_raw(d)
    _check("phase_error round-trip", e2 is not None and e2.error == "boom")
    e2 = parse_ndjson_line(to_ndjson(e))
    _check("phase_error ndjson", e2 is not None and e2.kind == "phase_error")

    # sandbox_start
    e = StreamEvent(kind="sandbox_start", task_id="t1", phase="sandbox")
    d = e.to_dict()
    _check("sandbox_start to_dict", d["phase"] == "sandbox")
    e2 = StreamEvent.from_raw(d)
    _check("sandbox_start round-trip", e2 is not None and e2.phase == "sandbox")
    e2 = parse_ndjson_line(to_ndjson(e))
    _check("sandbox_start ndjson", e2 is not None and e2.kind == "sandbox_start")

    # sandbox_done
    e = StreamEvent(kind="sandbox_done", task_id="t1", phase="sandbox",
                    output="OK", elapsed_s=0.5)
    d = e.to_dict()
    _check("sandbox_done to_dict", d["output"] == "OK")
    e2 = StreamEvent.from_raw(d)
    _check("sandbox_done round-trip", e2 is not None and e2.output == "OK")
    e2 = parse_ndjson_line(to_ndjson(e))
    _check("sandbox_done ndjson", e2 is not None and e2.kind == "sandbox_done")

    # meta aditivo
    e = StreamEvent(kind="phase_done", task_id="t1", phase="draft",
                    meta={"attempts": 2, "code_len": 128})
    d = e.to_dict()
    _check("meta preservado", d.get("meta", {}).get("attempts") == 2)
    e2 = StreamEvent.from_raw(d)
    _check("meta round-trip", e2 is not None and e2.meta.get("attempts") == 2)


    print()
    if failed == 0:
        print(f"  {passed} teste(s) OK")
        return 0
    print(f"  {passed}/{passed + failed} passaram — {failed} falha(s)")
    return 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_run_tests())
    print("Uso: python -m engine.api.events --test")
    raise SystemExit(1)
