# -*- coding: utf-8 -*-
"""Auto-benchmark para descobrir configuração de menor latência."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from engine.core.llm_bridge import BridgeConfig, SiCDoxBridge


@dataclass(frozen=True)
class Candidate:
    n_ctx: int
    min_p: float
    repeat_penalty: float


def default_candidates() -> list[Candidate]:
    return [
        Candidate(256, 0.05, 1.05),
        Candidate(512, 0.10, 1.10),
        Candidate(1024, 0.10, 1.10),
        Candidate(1024, 0.20, 1.10),
        Candidate(2048, 0.20, 1.15),
    ]


def _default_runner(cfg: BridgeConfig, prompt: str, max_tokens: int, runs: int) -> float:
    bridge = SiCDoxBridge(cfg)
    try:
        bridge.ask(prompt, max_tokens=max_tokens)  # warm-up
        times: list[float] = []
        for _ in range(runs):
            t0 = time.perf_counter()
            bridge.ask(prompt, max_tokens=max_tokens)
            times.append(time.perf_counter() - t0)
        return sum(times) / max(1, len(times))
    finally:
        bridge.shutdown()


def autotune(
    prompt: str,
    max_tokens: int = 96,
    runs: int = 2,
    candidates: list[Candidate] | None = None,
    runner: Callable[[BridgeConfig, str, int, int], float] | None = None,
) -> dict:
    pool = candidates or default_candidates()
    use_runner = runner or _default_runner
    rows: list[dict] = []
    for c in pool:
        cfg = BridgeConfig(n_ctx=c.n_ctx, active_window=min(c.n_ctx, 512), min_p=c.min_p, repeat_penalty=c.repeat_penalty)
        avg_s = use_runner(cfg, prompt, max_tokens, runs)
        rows.append({
            "n_ctx": c.n_ctx,
            "min_p": c.min_p,
            "repeat_penalty": c.repeat_penalty,
            "avg_s": round(avg_s, 4),
        })
    rows.sort(key=lambda r: r["avg_s"])
    return {"best": rows[0] if rows else None, "candidates": rows, "prompt": prompt, "runs": runs, "max_tokens": max_tokens}
