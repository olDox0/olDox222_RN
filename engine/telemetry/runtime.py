# engine/telemetry/runtime.py

import json
import time
import platform
from pathlib import Path
import threading

try:
    import psutil
except Exception:
    print("psutil indisponivel")
    psutil = None

TELEMETRY_DIR = Path("telemetry")
TELEMETRY_DIR.mkdir(exist_ok=True)

FILE_DIRECT = TELEMETRY_DIR / "direct_runtime.jsonl"
FILE_SERVER = TELEMETRY_DIR / "server_runtime.jsonl"

_write_lock = threading.Lock()

_PROC = psutil.Process() if psutil else None

def _now_unix():
    return int(time.time())

def system_stats(sample_interval: float | None = None) -> dict:
    info = {
        "platform": platform.system(),
        "python": platform.python_version(),
    }

    if psutil is None:
        return info

    try:

        if sample_interval is not None:
            cpu = psutil.cpu_percent(interval=sample_interval)
        else:
            cpu = psutil.cpu_percent(interval=None)

        proc = _PROC

        mem_rss = int(proc.memory_info().rss / 1024 / 1024)

        info.update({
            "cpu_percent": round(cpu, 3),
            "ram_used_mb": mem_rss,
            "threads": proc.num_threads(),
            "cpu_count": psutil.cpu_count(logical=False) or psutil.cpu_count(),
        })

    except Exception:
        pass

    return info


def _atomic_append(path: Path, obj: dict) -> None:
    with _write_lock:
        with path.open("a", encoding="utf-8", buffering=1) as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def record_direct(data: dict) -> None:
    payload = dict(data)

    payload.setdefault("captured_at_unix", _now_unix())
    payload.setdefault("mode", "direct")

    payload.update(system_stats(sample_interval=0.01))

    _atomic_append(FILE_DIRECT, payload)


def record_server(data: dict) -> None:
    payload = dict(data)

    payload.setdefault("captured_at_unix", _now_unix())
    payload.setdefault("mode", "server")

    payload.update(system_stats(sample_interval=0.01))

    _atomic_append(FILE_SERVER, payload)


def record(data: dict) -> None:
    try:
        record_direct(data)
    except Exception:
        pass