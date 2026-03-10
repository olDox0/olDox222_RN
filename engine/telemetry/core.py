# -*- coding: utf-8 -*-
# engine/telemetry/core.py
"""Telemetria leve para decisões de performance do ORN.

OSL-75: telemetria nunca pode alterar comportamento funcional.
Design: coleta local-first, overhead baixo e falha silenciosa.
"""

from __future__ import annotations

import time
import threading
import os
import json

from typing import Any, Callable
from pathlib import Path
from functools import wraps
from dataclasses import dataclass, field
from collections import deque


@dataclass(slots=True)
class ProbeStats:
    """Estatísticas compactas para uma função instrumentada."""

    category: str
    critical: bool
    calls: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    failures: int = 0
    cold_calls: int = 0
    warm_calls: int = 0
    _tail_ms: deque[float] = field(default_factory=lambda: deque(maxlen=2048), repr=False)

    def register(self, elapsed_ms: float, *, is_cold: bool, failed: bool) -> None:
        self.calls += 1
        self.total_ms += elapsed_ms
        self.max_ms = max(self.max_ms, elapsed_ms)
        self._tail_ms.append(elapsed_ms)
        if is_cold:
            self.cold_calls += 1
        else:
            self.warm_calls += 1
        if failed:
            self.failures += 1

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.calls if self.calls else 0.0

    @property
    def p95_ms(self) -> float:
        if not self._tail_ms:
            return 0.0
        ordered = sorted(self._tail_ms)
        idx = int(0.95 * (len(ordered) - 1))
        return ordered[idx]


class TelemetryAggregator:
    """Agregador em memória com API simples para snapshot e reset."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stats: dict[str, ProbeStats] = {}

    def observe(
        self,
        name: str,
        elapsed_ms: float,
        *,
        category: str,
        critical: bool,
        is_cold: bool,
        failed: bool,
    ) -> None:
        with self._lock:
            stats = self._stats.get(name)
            if stats is None:
                stats = ProbeStats(category=category, critical=critical)
                self._stats[name] = stats
            stats.register(elapsed_ms, is_cold=is_cold, failed=failed)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                name: {
                    "category": s.category,
                    "critical": s.critical,
                    "calls": s.calls,
                    "avg_ms": round(s.avg_ms, 4),
                    "p95_ms": round(s.p95_ms, 4),
                    "max_ms": round(s.max_ms, 4),
                    "cold_calls": s.cold_calls,
                    "warm_calls": s.warm_calls,
                    "failures": s.failures,
                }
                for name, s in self._stats.items()
            }

    def flush_json(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "captured_at_unix": int(time.time()),
            "probes": self.snapshot(),
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return out


GLOBAL_TELEMETRY = TelemetryAggregator()


def orn_probe(
    *,
    category: str = "exec",
    critical: bool = False,
    probe_name: str | None = None,
    aggregator: TelemetryAggregator | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorador de instrumentação leve.

    - Silencioso por design: erros de telemetria não podem quebrar execução.
    - Mede latência wall-clock em ms.
    - Distingue cold/warm call no escopo da função decorada.
    """

    sink = aggregator or GLOBAL_TELEMETRY

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        name = probe_name or f"{func.__module__}.{func.__qualname__}"
        warmed_up = False

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal warmed_up
            t0 = time.perf_counter()
            failed = False
            try:
                return func(*args, **kwargs)
            except Exception:
                failed = True
                raise
            finally:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                is_cold = not warmed_up
                warmed_up = True
                try:
                    sink.observe(
                        name,
                        elapsed_ms,
                        category=category,
                        critical=critical,
                        is_cold=is_cold,
                        failed=failed,
                    )
                except Exception:
                    # Telemetria nunca pode interromper o fluxo principal.
                    pass

        return wrapper

    return decorator

def get_runtime_status(limit: int = 5) -> dict:
    """
    Gera payload compatível com STATUS a partir do GLOBAL_TELEMETRY.
    Uso leve, fail-safe — não deve criar dependências fortes.
    """
    import os
    import platform
    import threading
    import time

    # snapshot das probes
    try:
        snap = GLOBAL_TELEMETRY.snapshot()
    except Exception:
        snap = {}

    rows: list[dict] = []
    total_ms = 0.0
    total_calls = 0
    for name, s in snap.items():
        calls = int(s.get("calls", 0) or 0)
        avg_ms = float(s.get("avg_ms", 0) or 0.0)
        p95 = float(s.get("p95_ms", 0) or 0.0)
        total_ms += avg_ms * calls
        total_calls += calls
        rows.append(
            {
                "name": name,
                "calls": calls,
                "avg_ms": avg_ms,
                "p95_ms": p95,
                "total_ms": round(calls * avg_ms, 4),
            }
        )

    rows.sort(key=lambda x: x["total_ms"], reverse=True)
    hotspots = rows[: max(1, limit)] if rows else []

    # simples snapshot de sistema (best-effort)
    rss_mb = 0.0
    try:
        # try unix resource first
        import resource as _resource  # type: ignore
        rss_kb = float(_resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss)
        if rss_kb > 10_000_000:
            rss_mb = round(rss_kb / (1024.0 * 1024.0), 3)
        else:
            rss_mb = round(rss_kb / 1024.0, 3)
    except Exception:
        try:
            # fallback to psutil if available
            import psutil  # type: ignore
            rss_mb = round(psutil.Process(os.getpid()).memory_info().rss / 1024.0 / 1024.0, 3)
        except Exception:
            rss_mb = 0.0

    load_1m = 0.0
    try:
        load_1m = round(float(os.getloadavg()[0]), 3)
    except Exception:
        load_1m = 0.0

    total_elapsed_s = round(total_ms / 1000.0, 3) if total_calls else 0.0
    avg_elapsed_s = round((total_elapsed_s / total_calls) if total_calls else 0.0, 3)

    # ai_perf best-effort
    infer_calls = 0
    for name, s in snap.items():
        if "infer" in name:
            infer_calls += int(s.get("calls", 0) or 0)

    ai_perf = {
        "infer_calls": infer_calls,
        "last_infer_s": 0.0,
        "last_max_tokens": 0,
        "last_prompt_chars": 0,
        "last_output_chars": 0,
        "avg_prompt_chars": 0,
        "avg_output_chars": 0,
        "last_tokens_per_s": 0.0,
        "total_tokens_per_s": 0.0,
        "last_output_chars_per_s": 0.0,
        "last_lock_wait_ms": 0.0,
        "last_llm_call_ms": 0.0,
        "avg_lock_wait_ms": 0.0,
        "avg_llm_call_ms": 0.0,
        "last_non_llm_ms": 0.0,
        "last_llm_share_pct": 0.0,
    }

    payload = {
        "status": "local",
        "uptime_s": 0,
        "requests": total_calls,
        "errors": 0,
        "total_tokens": 0,
        "avg_elapsed_s": avg_elapsed_s,
        "port": None,
        "vulcan": False,
        "vulcan_detail": "",
        "boot_perf": {"vulcan_boot_ms": 0.0, "model_load_ms": 0.0},
        "system_perf": {
            "pid": os.getpid(),
            "threads": threading.active_count(),
            "cpu_count": os.cpu_count() or 0,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "rss_mb": rss_mb,
            "load_1m": load_1m,
        },
        "ai_perf": ai_perf,
        "telemetry_hotspots": hotspots,
    }
    return payload
    
def record_direct_telemetry(payload: dict) -> None:
    """
    Grava telemetria do modo direto (append JSONL) e registra observações
    em GLOBAL_TELEMETRY para aparecer em hotspots locais.
    Fail-safe: nunca propaga excecao.
    """
    try:
        # file JSONL
        out_dir = Path("telemetry")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "direct_runtime.jsonl"
        # enriquecendo payload com timestamp/host info
        payload_enriched = dict(payload)
        payload_enriched.setdefault("captured_at_unix", int(time.time()))
        try:
            with out_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload_enriched, ensure_ascii=False) + "\n")
        except Exception:
            # último esforço: escrever sem bloquear
            pass

        # registra no GLOBAL_TELEMETRY para sumarização de hotspots
        try:
            # unidades em ms para GLOBAL_TELEMETRY.observe
            ml_ms = float((payload_enriched.get("model_load_s") or 0.0) * 1000.0)
            inf_ms = float((payload_enriched.get("infer_s") or 0.0) * 1000.0)
            total_ms = float((payload_enriched.get("total_s") or 0.0) * 1000.0)

            if ml_ms > 0:
                GLOBAL_TELEMETRY.observe(
                    "direct.model_load",
                    ml_ms,
                    category="direct",
                    critical=False,
                    is_cold=False,
                    failed=False,
                )
            if inf_ms > 0:
                GLOBAL_TELEMETRY.observe(
                    "direct.infer",
                    inf_ms,
                    category="direct",
                    critical=True,
                    is_cold=False,
                    failed=False,
                )
            if total_ms > 0:
                GLOBAL_TELEMETRY.observe(
                    "direct.total",
                    total_ms,
                    category="direct",
                    critical=False,
                    is_cold=False,
                    failed=False,
                )
        except Exception:
            pass

    except Exception:
        # absolutamente silencioso — telemetria nao deve quebrar fluxo
        pass