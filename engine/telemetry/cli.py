# -*- coding: utf-8 -*-
# engine/telemetry/cli.py
"""CLI utilitário para telemetria do ORN."""

from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path
from typing import Optional

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8371


def _fmt_ms(value: float) -> str:
    value = float(value or 0)
    if value >= 1000:
        return f"{value / 1000.0:.3f}s"
    return f"{value:.3f}ms"


def query_server_status(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 5.0) -> dict | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            s.sendall(b"STATUS\n")
            data = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
                if data.endswith(b"\n"):
                    break
        return json.loads(data.decode("utf-8").strip())
    except Exception:
        return None


def _hotspot_by_name(payload: dict, name: str) -> dict | None:
    for row in payload.get("telemetry_hotspots", []) or []:
        if row.get("name") == name:
            return row
    return None


def normalize_status_payload(payload: dict) -> tuple[dict, bool]:
    """Normaliza STATUS para exibição humana, com fallback para schemas antigos."""
    norm = dict(payload)
    ai = dict(norm.get("ai_perf") or {})
    inferred = False

    if "total_tokens_per_s" not in ai:
        total_tokens = float(norm.get("total_tokens", 0) or 0)
        avg_elapsed_s = float(norm.get("avg_elapsed_s", 0) or 0)
        requests = float(norm.get("requests", 0) or 0)
        total_elapsed_s = avg_elapsed_s * requests
        ai["total_tokens_per_s"] = round((total_tokens / total_elapsed_s) if total_elapsed_s else 0, 3)
        inferred = True

    infer_row = _hotspot_by_name(norm, "server.infer")
    llm_row = _hotspot_by_name(norm, "server.infer.llm_call")
    lock_row = _hotspot_by_name(norm, "server.infer.lock_wait")

    if "last_llm_call_ms" not in ai and llm_row:
        ai["last_llm_call_ms"] = float(llm_row.get("avg_ms", 0) or 0)
        inferred = True
    if "last_lock_wait_ms" not in ai and lock_row:
        ai["last_lock_wait_ms"] = float(lock_row.get("avg_ms", 0) or 0)
        inferred = True

    if "last_non_llm_ms" not in ai:
        infer_ms = float(ai.get("last_infer_s", 0) or 0) * 1000.0
        llm_ms = float(ai.get("last_llm_call_ms", 0) or 0)
        ai["last_non_llm_ms"] = round(max(infer_ms - llm_ms, 0.0), 4)
        inferred = True

    if "last_llm_share_pct" not in ai:
        infer_ms = float(ai.get("last_infer_s", 0) or 0) * 1000.0
        llm_ms = float(ai.get("last_llm_call_ms", 0) or 0)
        ai["last_llm_share_pct"] = round((llm_ms / infer_ms * 100.0) if infer_ms else 0, 2)
        inferred = True

    norm["ai_perf"] = ai
    return norm, inferred


def _print_human_status(payload: dict, *, limit: int = 5) -> None:
    payload, inferred = normalize_status_payload(payload)
    print(f"status: {payload.get('status', 'unknown')}")
    print(f"requests: {payload.get('requests', 0)}")
    print(f"errors: {payload.get('errors', 0)}")
    print(f"avg_elapsed_s: {payload.get('avg_elapsed_s', 0)}")
    boot = payload.get("boot_perf", {})
    if boot:
        print("boot_perf:")
        print(f"  - vulcan_boot: {_fmt_ms(boot.get('vulcan_boot_ms', 0))}")
        print(f"  - model_load : {_fmt_ms(boot.get('model_load_ms', 0))}")

    system = payload.get("system_perf", {})
    if system:
        print("system_perf:")
        print(f"  - pid/threads : {system.get('pid', 0)} / {system.get('threads', 0)}")
        print(f"  - cpu/load1m  : {system.get('cpu_count', 0)} / {system.get('load_1m', 0)}")
        print(f"  - rss_mb      : {system.get('rss_mb', 0)}")

    ai = payload.get("ai_perf", {})
    if ai:
        title = "ai_perf (compat)" if inferred else "ai_perf"
        print(f"{title}:")
        print(f"  - infer_calls   : {ai.get('infer_calls', 0)}")
        print(f"  - last_infer    : {ai.get('last_infer_s', 0)}s")
        print(f"  - last_tps      : {ai.get('last_tokens_per_s', 0)} tok/s")
        print(f"  - total_tps     : {ai.get('total_tokens_per_s', 0)} tok/s")
        print(f"  - avg_prompt    : {ai.get('avg_prompt_chars', 0)} chars")
        print(f"  - avg_output    : {ai.get('avg_output_chars', 0)} chars")
        print(f"  - lock_wait     : {_fmt_ms(ai.get('last_lock_wait_ms', 0))}")
        print(f"  - llm_call      : {_fmt_ms(ai.get('last_llm_call_ms', 0))}")
        print(f"  - non_llm       : {_fmt_ms(ai.get('last_non_llm_ms', 0))}")
        print(f"  - llm_share     : {ai.get('last_llm_share_pct', 0)}%")

    hotspots = payload.get("telemetry_hotspots", [])
    if hotspots:
        total = sum(float(r.get("total_ms", 0) or 0) for r in hotspots) or 1.0
        print("hotspots:")
        for row in hotspots[:max(1, limit)]:
            share = (float(row.get("total_ms", 0) or 0) / total) * 100.0
            print(
                "  - "
                f"{row.get('name', '?')} calls={row.get('calls', 0)} "
                f"avg={_fmt_ms(row.get('avg_ms', 0))} p95={_fmt_ms(row.get('p95_ms', 0))} "
                f"total={_fmt_ms(row.get('total_ms', 0))} share={share:.1f}%"
            )


def _emit_output(content: str, *, out: str | None = None) -> None:
    if out:
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content + ("" if content.endswith("\n") else "\n"), encoding="utf-8")
        print(f"[probe] salvo em: {target}")
        return
    print(content)


def _try_local_runtime(limit: int) -> tuple[Optional[dict], Optional[str]]:
    """
    Tenta obter telemetria local:
     - primeiro, via engine.telemetry.core.get_runtime_status
     - depois, via arquivo telemetry/server_runtime.json (snapshot do servidor)
    Retorna (payload, mode) onde mode é 'local' / 'file' / None
    """
    try:
        # import local function from the telemetry core (safe, fail-silent)
        from engine.telemetry.core import get_runtime_status  # type: ignore
        payload = get_runtime_status(limit=limit)
        return payload, "local"
    except Exception:
        # fallback: check for snapshot file (written by server flush)
        try:
            p = Path("engine/telemetry") / "server_runtime.json"
            if p.exists():
                payload = json.loads(p.read_text(encoding="utf-8"))
                return payload, "file"
        except Exception:
            pass
    return None, None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orn-probe", description="Consulta telemetria do ORN server / runtime.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--json", dest="as_json", action="store_true", help="Saída JSON bruta")
    parser.add_argument("--limit", type=int, default=5, help="Quantidade máxima de hotspots na saída")
    parser.add_argument("--out", default=None, help="Arquivo de saída (útil no Windows em vez de /tmp)")
    args = parser.parse_args(argv)

    payload = query_server_status(host=args.host, port=args.port)
    mode = "server" if payload is not None else None

    if payload is None:
        payload, mode = _try_local_runtime(limit=max(1, args.limit))
        
    # === NOVA LINHA AQUI ===
    if payload is not None:
        _append_vulcan_hotspots(payload)

    # Final: se payload ainda None -> sem telemetria
    if payload is None:
        if args.as_json:
            _emit_output(json.dumps({"status": "offline", "error": "no_telemetry_available"}, ensure_ascii=False, indent=2), out=args.out)
        else:
            _emit_output("[probe] nenhuma telemetria disponível (server/runtime/file)", out=args.out)
        return 1

    # human header: show mode so user knows where data came from
    if not args.as_json:
        _emit_output(f"[probe] mode: {mode}", out=args.out)

    if args.as_json:
        trimmed = dict(payload)
        if "telemetry_hotspots" in trimmed and isinstance(trimmed["telemetry_hotspots"], list):
            trimmed["telemetry_hotspots"] = trimmed["telemetry_hotspots"][:max(1, args.limit)]
        _emit_output(json.dumps(trimmed, ensure_ascii=False, indent=2), out=args.out)
    else:
        _print_human_status(payload, limit=max(1, args.limit))
    return 0

def _append_vulcan_hotspots(payload: dict) -> None:
    """Lê telemetria do Vulcan Embedded e mescla nos hotspots nativos do ORN."""
    try:
        p = Path("telemetry") / "vulcan_runtime.jsonl"
        if not p.exists(): return
        
        vulcan_agg = {}
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                data = json.loads(line)
                stats = data.get("vulcan_stats", {})
                for fn, st in stats.items():
                    if fn not in vulcan_agg:
                        vulcan_agg[fn] = {"calls": 0, "total_ms": 0.0}
                    vulcan_agg[fn]["calls"] += st.get("hits", 0)
                    vulcan_agg[fn]["total_ms"] += st.get("total_ms", 0.0)
        
        if vulcan_agg:
            hotspots = payload.setdefault("telemetry_hotspots",[])
            for fn, st in vulcan_agg.items():
                calls = st["calls"]
                total_ms = st["total_ms"]
                avg_ms = total_ms / calls if calls else 0.0
                hotspots.append({
                    "name": f"[⚡VULCAN] {fn}",
                    "calls": calls,
                    "avg_ms": avg_ms,
                    "p95_ms": avg_ms, # fallback
                    "total_ms": total_ms
                })
            # Reordena do mais custoso pro mais leve
            hotspots.sort(key=lambda x: x.get("total_ms", 0), reverse=True)
    except Exception:
        pass

if __name__ == "__main__":
    raise SystemExit(main())