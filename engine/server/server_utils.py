# -*- coding: utf-8 -*-
"""Shared utility helpers for ORN server runtime."""

from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path
from typing import Any

from engine.telemetry import GLOBAL_TELEMETRY

try:
    import resource as _resource  # Unix only
    _HAS_RESOURCE = True
except ImportError:
    _HAS_RESOURCE = False


def observe_telemetry(name: str, elapsed_ms: float, *, category: str = "exec") -> None:
    try:
        GLOBAL_TELEMETRY.observe(
            name,
            float(elapsed_ms),
            category=category,
            critical=(category == "exec"),
            is_cold=False,
            failed=False,
        )
    except Exception:
        pass


def flush_telemetry_snapshot() -> None:
    try:
        GLOBAL_TELEMETRY.flush_json(Path("telemetry") / "server_runtime.json")
    except Exception:
        pass


def system_perf_snapshot() -> dict[str, Any]:
    rss_mb = 0.0
    try:
        if _HAS_RESOURCE:
            rss_kb = float(_resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss)
            if rss_kb > 10_000_000:
                rss_mb = round(rss_kb / (1024.0 * 1024.0), 3)
            else:
                rss_mb = round(rss_kb / 1024.0, 3)
    except Exception:
        pass

    load_1m = 0.0
    try:
        load_1m = round(float(os.getloadavg()[0]), 3)
    except Exception:
        pass

    import platform

    return {
        "pid": os.getpid(),
        "threads": threading.active_count(),
        "cpu_count": os.cpu_count() or 0,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "rss_mb": rss_mb,
        "load_1m": load_1m,
    }


def json_line(resp: dict[str, Any]) -> bytes:
    return (json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8")


def read_line_from_socket(conn: socket.socket, recv_sz: int, timeout: float = 10.0) -> str:
    conn.settimeout(timeout)
    data = bytearray()
    while True:
        chunk = conn.recv(recv_sz)
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in data:
            break
    return data.decode("utf-8", errors="replace").strip()
