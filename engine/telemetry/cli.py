# -*- coding: utf-8 -*-
"""CLI utilitário para telemetria do ORN."""

from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path


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


def _print_human_status(payload: dict, *, limit: int = 5) -> None:
    print(f"status: {payload.get('status', 'unknown')}")
    print(f"requests: {payload.get('requests', 0)}")
    print(f"errors: {payload.get('errors', 0)}")
    print(f"avg_elapsed_s: {payload.get('avg_elapsed_s', 0)}")
    boot = payload.get("boot_perf", {})
    if boot:
        print("boot_perf:")
        print(f"  - vulcan_boot: {_fmt_ms(boot.get('vulcan_boot_ms', 0))}")
        print(f"  - model_load : {_fmt_ms(boot.get('model_load_ms', 0))}")

    ai = payload.get("ai_perf", {})
    if ai:
        print("ai_perf:")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orn-probe", description="Consulta telemetria do ORN server.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--json", dest="as_json", action="store_true", help="Saída JSON bruta")
    parser.add_argument("--limit", type=int, default=5, help="Quantidade máxima de hotspots na saída")
    parser.add_argument("--out", default=None, help="Arquivo de saída (útil no Windows em vez de /tmp)")
    args = parser.parse_args(argv)

    payload = query_server_status(host=args.host, port=args.port)
    if payload is None:
        if args.as_json:
            _emit_output(json.dumps({"status": "offline", "error": "server_unreachable"}, ensure_ascii=False, indent=2), out=args.out)
        else:
            _emit_output("[probe] servidor offline", out=args.out)
        return 1

    if args.as_json:
        trimmed = dict(payload)
        if "telemetry_hotspots" in trimmed and isinstance(trimmed["telemetry_hotspots"], list):
            trimmed["telemetry_hotspots"] = trimmed["telemetry_hotspots"][:max(1, args.limit)]
        _emit_output(json.dumps(trimmed, ensure_ascii=False, indent=2), out=args.out)
    else:
        _print_human_status(payload, limit=max(1, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
