# -*- coding: utf-8 -*-
"""CLI utilitário para telemetria do ORN."""

from __future__ import annotations

import argparse
import json
import socket


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8371


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


def _print_human_status(payload: dict) -> None:
    print(f"status: {payload.get('status', 'unknown')}")
    print(f"requests: {payload.get('requests', 0)}")
    print(f"errors: {payload.get('errors', 0)}")
    print(f"avg_elapsed_s: {payload.get('avg_elapsed_s', 0)}")
    hotspots = payload.get("telemetry_hotspots", [])
    if hotspots:
        print("hotspots:")
        for row in hotspots:
            print(
                "  - "
                f"{row.get('name', '?')} calls={row.get('calls', 0)} "
                f"avg={row.get('avg_ms', 0)}ms p95={row.get('p95_ms', 0)}ms"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orn-probe", description="Consulta telemetria do ORN server.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--json", dest="as_json", action="store_true", help="Saída JSON bruta")
    args = parser.parse_args(argv)

    payload = query_server_status(host=args.host, port=args.port)
    if payload is None:
        print("[probe] servidor offline")
        return 1

    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_human_status(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
