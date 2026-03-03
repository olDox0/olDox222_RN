# -*- coding: utf-8 -*-
"""Telemetria leve para decisões de performance do ORN.

OSL-75: telemetria nunca pode alterar comportamento funcional.
Design: coleta local-first, overhead baixo e falha silenciosa.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from functools import wraps
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable


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
