# -*- coding: utf-8 -*-
# engine/server/server_bench.py
"""
ORN — Vulcan Library Benchmark
================================
Confirma se llama_cpp compilado esta sendo usado e mede ganho real.

Uso:
  python engine/server/server_bench.py               # benchmark via servidor
  python engine/server/server_bench.py --runs 20     # mais amostras
  python engine/server/server_bench.py --inspect     # so inspecao de modulos
  python engine/server/server_bench.py --deep        # inspect + bench local + servidor
  python engine/server/server_bench.py --local       # bench local (import + load)

Requerimentos:
  - Para bench via servidor: orn-server start deve estar rodando
  - Para --deep/--local: executar a partir da raiz do projeto ORN
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import sys
import time
import traceback
from pathlib import Path

# ── Constantes — definidas antes de qualquer uso ─────────────────────────────
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8371

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
DIM    = "\033[2m"

# Prompts fixos para garantir comparabilidade entre runs
_BENCH_PROMPTS = [
    ("curto",  "Ola, tudo bem?",                                          32),
    ("medio",  "Explique o que e recursao em programacao.",               64),
    ("longo",  "Escreva uma funcao Python que calcula o fatorial de n.", 128),
]


# ── Helpers de socket ─────────────────────────────────────────────────────────

def _raw_query(payload: bytes, host: str, port: int, timeout: float = 120.0) -> dict | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            s.settimeout(None)
            s.sendall(payload)
            data = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
                if data.endswith(b"\n"):
                    break
        return json.loads(data.decode("utf-8").strip())
    except Exception as exc:
        print(f"{RED}[SOCKET] {exc}{RESET}")
        return None


def _query(prompt: str, max_tokens: int, host: str, port: int) -> dict | None:
    payload = (json.dumps({"prompt": prompt, "max_tokens": max_tokens}) + "\n").encode()
    return _raw_query(payload, host, port)


def _status(host: str, port: int) -> dict | None:
    return _raw_query(b"STATUS\n", host, port, timeout=5.0)


# ── Bootstrap doxoade (mesmo algoritmo do server.py) ─────────────────────────

def _bootstrap_doxoade() -> bool:
    """Tenta tornar doxoade importavel. Retorna True se conseguiu."""
    # Variavel de ambiente explicita
    env_root = os.environ.get("DOXOADE_ROOT")
    if env_root:
        p = str(Path(env_root).resolve())
        if p not in sys.path:
            sys.path.insert(0, p)

    # Sobe a arvore a partir deste arquivo
    if not env_root:
        here = Path(__file__).resolve()
        for parent in [here, *here.parents]:
            if (parent / "doxoade" / "__init__.py").exists():
                p = str(parent)
                if p not in sys.path:
                    sys.path.insert(0, p)
                break

    try:
        import doxoade  # noqa: F401
        return True
    except ImportError:
        return False


# ── Inspecao de modulos ───────────────────────────────────────────────────────

def inspect_llama_cpp() -> dict:
    """
    Carrega llama_cpp com Vulcan ativo e inspeciona qual arquivo foi usado.
    Retorna dict com resultado completo da inspecao.
    """
    result = {
        "vulcan_active":   False,
        "vulcan_msg":      "",
        "llama_file_py":   None,
        "llama_file_used": None,
        "is_native":       False,
        "lib_bin_files":   [],
        "error":           None,
    }

    if not _bootstrap_doxoade():
        result["error"] = (
            "'doxoade' nao importavel. "
            "Execute a partir da raiz do projeto ou defina DOXOADE_ROOT."
        )
        return result

    # Inventario de binarios disponiveis
    try:
        from doxoade.tools.vulcan.runtime import find_vulcan_project_root, install_meta_finder

        root = (
            find_vulcan_project_root(Path.cwd())
            or find_vulcan_project_root(__file__)
        )
        if root:
            lib_bin = root / ".doxoade" / "vulcan" / "lib_bin"
            if lib_bin.exists():
                result["lib_bin_files"] = [p.name for p in sorted(lib_bin.glob("*.pyd"))]
            install_meta_finder(root)
            result["vulcan_active"] = True
            result["vulcan_msg"]    = f"MetaFinder instalado para '{root}'"
        else:
            result["vulcan_msg"] = ".doxoade/vulcan/bin nao encontrado"

    except Exception as exc:
        result["vulcan_msg"] = f"MetaFinder falhou: {exc}\n{traceback.format_exc()}"

    # Arquivo .py original (sem vulcan)
    try:
        spec = importlib.util.find_spec("llama_cpp")
        if spec and spec.origin:
            result["llama_file_py"] = spec.origin
    except Exception:
        pass

    # Importa com vulcan ativo e verifica origem real
    try:
        for key in list(sys.modules.keys()):
            if "llama_cpp" in key:
                del sys.modules[key]

        import llama_cpp
        origin = getattr(llama_cpp, "__file__", None)
        if origin is None:
            spec = getattr(llama_cpp, "__spec__", None)
            if spec:
                origin = getattr(spec, "origin", None)
        result["llama_file_used"] = str(origin) if origin else "desconhecido"
        used = result["llama_file_used"]
        result["is_native"] = used.endswith(".pyd") or used.endswith(".so")

    except Exception as exc:
        result["error"] = f"Import llama_cpp falhou: {exc}\n{traceback.format_exc()}"

    return result


def print_inspection(r: dict) -> None:
    print(f"\n{CYAN}{'─'*62}{RESET}")
    print(f"{BOLD}  INSPECAO DE MODULOS — llama_cpp{RESET}")
    print(f"{CYAN}{'─'*62}{RESET}")

    v_str = f"{GREEN}ATIVO{RESET}" if r["vulcan_active"] else f"{RED}FALHOU{RESET}"
    print(f"  Vulcan MetaFinder  : {v_str}")
    for line in r["vulcan_msg"].splitlines()[:3]:
        print(f"  {DIM}{line}{RESET}")

    print(f"\n  Binarios em lib_bin/ : {len(r['lib_bin_files'])}")
    for f in r["lib_bin_files"][:10]:
        tag = f" {GREEN}← llama{RESET}" if "llama" in f.lower() else ""
        print(f"    {DIM}{f}{RESET}{tag}")
    if len(r["lib_bin_files"]) > 10:
        print(f"    {DIM}... +{len(r['lib_bin_files'])-10} outros{RESET}")

    print(f"\n  Arquivo .py original : {DIM}{r['llama_file_py']}{RESET}")
    print(f"  Arquivo carregado    : {DIM}{r['llama_file_used']}{RESET}")

    if r["is_native"]:
        print(f"  Usando binario nativo: {GREEN}SIM{RESET}")
    else:
        print(f"  Usando binario nativo: {YELLOW}NAO — Python puro{RESET}")

    if r["error"]:
        print(f"\n  {RED}ERRO: {r['error'][:300]}{RESET}")

    print(f"{CYAN}{'─'*62}{RESET}\n")


# ── Benchmark via servidor ────────────────────────────────────────────────────

def run_server_bench(runs: int, host: str, port: int) -> None:
    print(f"\n{CYAN}{'─'*62}{RESET}")
    print(f"{BOLD}  BENCHMARK — Servidor {host}:{port}{RESET}")
    print(f"{CYAN}{'─'*62}{RESET}")

    st = _status(host, port)
    if st is None:
        print(f"{RED}  Servidor offline. Execute: orn-server start{RESET}")
        return

    vulcan_str = f"{GREEN}ATIVO{RESET}" if st.get("vulcan") else f"{YELLOW}Python puro{RESET}"
    print(f"  Backend    : {vulcan_str}")
    print(f"  Uptime     : {st.get('uptime_s', 0):.1f}s")
    print(f"  Requests   : {st.get('requests', 0)} anteriores")
    if not st.get("vulcan"):
        for line in st.get("vulcan_detail", "").splitlines()[:3]:
            print(f"  {YELLOW}{line}{RESET}")
    print()

    all_times: list[float] = []
    errors = 0

    for label, prompt, max_tokens in _BENCH_PROMPTS:
        times: list[float] = []
        print(f"  {BOLD}[{label.upper()}]{RESET}  max_tokens={max_tokens}  ({runs} runs)")
        print(f"  Prompt: {DIM}{prompt[:60]}{RESET}")

        for i in range(runs):
            t0   = time.perf_counter()
            resp = _query(prompt, max_tokens, host, port)
            wall = round(time.perf_counter() - t0, 3)

            if resp is None:
                print(f"    run {i+1:02d}: {RED}TIMEOUT/ERRO{RESET}")
                errors += 1
                continue

            if resp.get("error"):
                print(f"    run {i+1:02d}: {RED}ERRO — {resp['error'][:80]}{RESET}")
                if resp.get("traceback"):
                    for tb_line in resp["traceback"].splitlines()[-4:]:
                        print(f"             {DIM}{tb_line}{RESET}")
                errors += 1
                continue

            srv_t = resp.get("elapsed_s", wall)
            times.append(srv_t)
            all_times.append(srv_t)

            bar_len = min(int(srv_t * 8), 32)
            bar_col = GREEN if srv_t < 2.0 else YELLOW if srv_t < 5.0 else RED
            bar = f"{bar_col}{'█' * bar_len}{'░' * (32 - bar_len)}{RESET}"
            print(f"    run {i+1:02d}: {srv_t:6.3f}s  {bar}")

        if times:
            avg  = sum(times) / len(times)
            best = min(times)
            p95  = sorted(times)[max(0, int(len(times) * 0.95) - 1)]
            toks = max_tokens / avg if avg > 0 else 0
            print(f"  {DIM}avg={avg:.3f}s  best={best:.3f}s  p95={p95:.3f}s  ~{toks:.1f} tok/s{RESET}")
        print()

    print(f"{CYAN}{'─'*62}{RESET}")
    if all_times:
        total_avg  = sum(all_times) / len(all_times)
        total_best = min(all_times)
        print(f"  {BOLD}TOTAL  runs={len(all_times)}  erros={errors}{RESET}")
        print(f"  avg global : {total_avg:.3f}s")
        print(f"  melhor run : {total_best:.3f}s")
    else:
        print(f"  {RED}Nenhuma medicao valida. Verifique o servidor.{RESET}")
    print(f"{CYAN}{'─'*62}{RESET}\n")


# ── Benchmark local ───────────────────────────────────────────────────────────

def run_local_bench(runs: int) -> None:
    """Mede tempo de import e load do modelo diretamente (sem servidor)."""
    print(f"\n{CYAN}{'─'*62}{RESET}")
    print(f"{BOLD}  BENCHMARK LOCAL — import + load do modelo{RESET}")
    print(f"{CYAN}{'─'*62}{RESET}")

    _bootstrap_doxoade()

    # Mede import de llama_cpp
    import_times = []
    for i in range(runs):
        for key in list(sys.modules.keys()):
            if "llama_cpp" in key:
                del sys.modules[key]
        t0 = time.perf_counter()
        try:
            import llama_cpp  # noqa: F401
            import_times.append(time.perf_counter() - t0)
            print(f"  import #{i+1}: {import_times[-1]*1000:.1f}ms")
        except Exception as exc:
            print(f"{RED}  import falhou: {exc}{RESET}")
            break

    if import_times:
        avg_i = sum(import_times) / len(import_times)
        print(f"  {DIM}avg import: {avg_i*1000:.1f}ms{RESET}\n")

    # Mede load do modelo
    try:
        from engine.core.llm_bridge import BridgeConfig
        cfg = BridgeConfig()
        if not cfg.model_path.exists():
            print(f"  {YELLOW}Modelo nao encontrado em {cfg.model_path}{RESET}")
            print(f"  {YELLOW}Pulando bench de load.{RESET}")
        else:
            from llama_cpp import Llama
            load_runs = min(runs, 2)  # max 2 — carregamento e lento
            for i in range(load_runs):
                t0  = time.perf_counter()
                llm = Llama(
                    model_path   = str(cfg.model_path),
                    n_ctx        = cfg.n_ctx,
                    n_threads    = cfg.n_threads,
                    n_gpu_layers = cfg.n_gpu_layers,
                    verbose      = False,
                )
                elapsed = time.perf_counter() - t0
                llm.close()
                del llm
                print(f"  load #{i+1}: {elapsed:.2f}s")

    except ImportError as exc:
        print(f"  {YELLOW}BridgeConfig indisponivel: {exc}{RESET}")
    except Exception as exc:
        print(f"  {RED}Erro: {exc}{RESET}")
        traceback.print_exc()

    print(f"{CYAN}{'─'*62}{RESET}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    # global declarado ANTES de qualquer uso — fix do SyntaxError
    parser = argparse.ArgumentParser(
        description="Benchmark Vulcan/llama_cpp para o ORN Server"
    )
    parser.add_argument("--runs",    type=int, default=5,
                        help="Requisicoes por prompt (default: 5)")
    parser.add_argument("--inspect", action="store_true",
                        help="Inspeciona quais modulos estao sendo usados")
    parser.add_argument("--deep",    action="store_true",
                        help="Inspecao + bench local + bench servidor")
    parser.add_argument("--local",   action="store_true",
                        help="Bench local (import + load) sem servidor")
    parser.add_argument("--host",    type=str, default=_DEFAULT_HOST,
                        help=f"Host do servidor (default: {_DEFAULT_HOST})")
    parser.add_argument("--port",    type=int, default=_DEFAULT_PORT,
                        help=f"Porta do servidor (default: {_DEFAULT_PORT})")
    args = parser.parse_args()

    host = args.host
    port = args.port

    print(f"\n{BOLD}  ORN Vulcan Benchmark{RESET}  —  {host}:{port}")

    if args.inspect or args.deep:
        r = inspect_llama_cpp()
        print_inspection(r)

    if args.local or args.deep:
        run_local_bench(runs=args.runs)

    if not args.inspect:
        run_server_bench(runs=args.runs, host=host, port=port)


if __name__ == "__main__":
    main()