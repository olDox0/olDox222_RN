# -*- coding: utf-8 -*-
# engine/server/server.py
"""
ORN — SiCDox Server
Servidor local de inferencia. Carrega o modelo UMA VEZ, serve para sempre.

Protocolo (TCP local):
  Request:  JSON linha  {"prompt": "...", "max_tokens": 128}
  Response: JSON linha  {"output": "...", "elapsed_s": 1.23, "error": null}

Comando especial (sem JSON):
  b"STATUS\n"  -> JSON com uptime, requests, errors

OSL-3:  Modelo carregado uma vez no startup.
OSL-7:  Toda requisicao retorna JSON com "error" explicito.
OSL-15: Erros de inferencia nao derrubam o servidor.
OSL-18: stdlib apenas (socket, json, threading, pathlib, subprocess).
God: Hefesto — fornalha continua; a forja nao apaga entre pecas.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

from engine.telemetry import GLOBAL_TELEMETRY, orn_probe


# ---------------------------------------------------------------------------
# [VULCAN] Bootstrap do MetaFinder
# Deve ocorrer ANTES de qualquer import de terceiros (llama_cpp, etc.)
#
# Estrategia de localizacao do doxoade (em ordem de prioridade):
#   1. Variavel DOXOADE_ROOT definida no ambiente
#   2. Pasta local doxoade/ subindo a arvore a partir de __file__
#   3. Pacote instalado no venv (importavel diretamente, sem sys.path extra)
#      — caso tipico quando doxoade esta em site-packages
# ---------------------------------------------------------------------------

def _vulcan_boot() -> tuple[bool, str]:
    """
    Garante que doxoade seja importavel e instala o VulcanMetaFinder.
    Retorna (sucesso: bool, mensagem_detalhada: str).
    OSL-15: nunca propaga excecao — falha = Python puro, servidor continua.
    """
    # ── Etapa 1: injetar sys.path se necessario ──────────────────────────────

    # Caso 1: variavel de ambiente explicita (deploy / CI)
    env_root = os.environ.get("DOXOADE_ROOT")
    if env_root:
        env_path = str(Path(env_root).resolve())
        if env_path not in sys.path:
            sys.path.insert(0, env_path)

    # Caso 2: pasta local — sobe a arvore a partir deste arquivo
    if not env_root:
        here = Path(__file__).resolve()
        for parent in [here, *here.parents]:
            if (parent / "doxoade" / "__init__.py").exists():
                root_str = str(parent)
                if root_str not in sys.path:
                    sys.path.insert(0, root_str)
                break

    # Caso 3: pacote instalado no venv → ja importavel, nada a fazer

    # ── Etapa 2: verificar se o import funciona ──────────────────────────────
    try:
        import doxoade  # noqa: F401
    except ImportError as exc:
        return False, (
            f"'doxoade' nao encontrado em sys.path nem instalado no venv.\n"
            f"  ImportError: {exc}\n"
            f"  Solucoes:\n"
            f"    a) Execute na raiz do projeto: cd <raiz> && orn-server start\n"
            f"    b) Instale o pacote: pip install -e <raiz>\n"
            f"    c) Defina: set DOXOADE_ROOT=<raiz_que_contem_pasta_doxoade>"
        )

    # ── Etapa 3: instalar MetaFinder ─────────────────────────────────────────
    try:
        from doxoade.tools.vulcan.runtime import find_vulcan_project_root, install_meta_finder

        # Tenta localizar .doxoade/vulcan/bin a partir do CWD e de __file__
        root = (
            find_vulcan_project_root(Path.cwd())
            or find_vulcan_project_root(__file__)
        )
        if root is None:
            return False, (
                "doxoade importado OK, mas '.doxoade/vulcan/bin' nao encontrado.\n"
                f"  Certifique-se de rodar 'doxoade vulcan lib' antes de iniciar o servidor.\n"
                f"  CWD atual: {Path.cwd()}"
            )

        install_meta_finder(root)

        lib_bin = root / ".doxoade" / "vulcan" / "lib_bin"
        n_bins  = len(list(lib_bin.glob("*.pyd"))) if lib_bin.exists() else 0
        return True, f"raiz='{root}' | {n_bins} binario(s) em lib_bin/"

    except Exception:
        return False, f"MetaFinder falhou:\n{traceback.format_exc()}"


# Ativa ANTES dos imports de terceiros
_t_boot0 = time.monotonic()
_VULCAN_ACTIVE, _VULCAN_MSG = _vulcan_boot()
_VULCAN_BOOT_MS = round((time.monotonic() - _t_boot0) * 1000.0, 3)

if _VULCAN_ACTIVE:
    print(f"[VULCAN] OK — {_VULCAN_MSG}", flush=True)
else:
    for _line in _VULCAN_MSG.splitlines():
        print(f"[VULCAN] {_line}", flush=True)
    print("[VULCAN] Continuando com Python puro (OSL-15).", flush=True)


# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------

HOST     = "127.0.0.1"
PORT     = 8371
BACKLOG  = 4
RECV_SZ  = 65536

PID_FILE = Path("server.pid")
LOG_FILE = Path("server.log")


# ---------------------------------------------------------------------------
# Estado global (OSL-3)
# ---------------------------------------------------------------------------

_llm   = None
_cfg   = None
_stats = {
    "requests":        0,
    "errors":          0,
    "total_tokens":    0,
    "total_elapsed_s": 0.0,
    "start":           None,
}
_boot_perf = {
    "vulcan_boot_ms": _VULCAN_BOOT_MS,
    "model_load_ms": 0.0,
}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Boot do modelo
# ---------------------------------------------------------------------------


def _observe_telemetry(name: str, elapsed_ms: float, *, category: str = "exec") -> None:
    """Registro fail-silent de métricas para fases internas do servidor."""
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


def _load_model() -> None:
    global _llm, _cfg
    from engine.core.llm_bridge import BridgeConfig
    from llama_cpp import Llama

    _cfg = BridgeConfig()
    if not _cfg.model_path.exists():
        print(f"[ERRO] Modelo nao encontrado: {_cfg.model_path}", flush=True)
        sys.exit(1)

    backend = "VULCAN/nativo" if _VULCAN_ACTIVE else "Python puro"
    print(f"[BOOT] {_cfg.model_path.name}  [{backend}]", flush=True)
    print(f"[BOOT] n_threads={_cfg.n_threads}  n_ctx={_cfg.n_ctx}", flush=True)

    t0   = time.monotonic()
    _llm = Llama(
        model_path   = str(_cfg.model_path),
        n_ctx        = _cfg.n_ctx,
        n_threads    = _cfg.n_threads,
        n_gpu_layers = _cfg.n_gpu_layers,
        verbose      = False,
    )
    elapsed = round(time.monotonic() - t0, 1)
    _boot_perf["model_load_ms"] = round(elapsed * 1000.0, 3)
    _observe_telemetry("server.boot.model_load", _boot_perf["model_load_ms"], category="boot")
    _stats["start"] = time.monotonic()
    print(f"[BOOT] Pronto em {elapsed}s — {HOST}:{PORT}", flush=True)


# ---------------------------------------------------------------------------
# Inferencia
# ---------------------------------------------------------------------------

@orn_probe(category="exec", critical=True, probe_name="server.infer")
def _infer(prompt: str, max_tokens: int) -> tuple[str, float]:
    prompt_full = (
        f"<|im_start|>system\n{_cfg.system_prompt}<|im_end|>\n"
        f"<|im_start|>user\n{prompt}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    t0 = time.monotonic()
    t_wait0 = time.monotonic()
    with _lock:
        lock_wait_ms = (time.monotonic() - t_wait0) * 1000.0
        t_llm0 = time.monotonic()
        out = _llm(
            prompt_full,
            max_tokens     = max_tokens,
            stop           = ["<|im_end|>", "</s>"],
            echo           = False,
            temperature    = _cfg.temperature,
            top_p          = _cfg.top_p,
            top_k          = _cfg.top_k,
            repeat_penalty = _cfg.repeat_penalty,
        )
        llm_call_ms = (time.monotonic() - t_llm0) * 1000.0

    _observe_telemetry("server.infer.lock_wait", lock_wait_ms)
    _observe_telemetry("server.infer.llm_call", llm_call_ms)

    elapsed = round(time.monotonic() - t0, 3)
    return out["choices"][0]["text"].strip(), elapsed



# ---------------------------------------------------------------------------
# Handler de conexao
# ---------------------------------------------------------------------------


def _telemetry_hotspots(limit: int = 3) -> list[dict]:
    """Resumo de gargalos de telemetria para endpoint STATUS."""
    try:
        snap = GLOBAL_TELEMETRY.snapshot()
    except Exception:
        return []

    rows: list[dict] = []
    for name, stats in snap.items():
        calls = int(stats.get("calls", 0) or 0)
        avg_ms = float(stats.get("avg_ms", 0) or 0)
        rows.append(
            {
                "name": name,
                "calls": calls,
                "avg_ms": avg_ms,
                "p95_ms": float(stats.get("p95_ms", 0) or 0),
                "total_ms": round(calls * avg_ms, 4),
            }
        )

    rows.sort(key=lambda x: x["total_ms"], reverse=True)
    return rows[: max(1, limit)]


def _flush_telemetry_snapshot() -> None:
    try:
        GLOBAL_TELEMETRY.flush_json(Path("telemetry") / "server_runtime.json")
    except Exception:
        # Telemetria nunca pode derrubar o servidor.
        pass


def _handle(conn: socket.socket) -> None:
    # OSL-7: resp sempre definida — cliente nunca fica pendurado sem resposta
    resp: dict = {"output": "", "elapsed_s": 0, "error": "internal error"}

    try:
        conn.settimeout(10)
        data = b""
        while True:
            chunk = conn.recv(RECV_SZ)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break

        line = data.decode("utf-8").strip()
        if not line:
            resp = {"output": "", "elapsed_s": 0, "error": "payload vazio"}
            return

        # STATUS especial
        if line.upper() == "STATUS":
            up  = round(time.monotonic() - _stats["start"], 1) if _stats["start"] else 0
            req = _stats["requests"]
            avg = round(_stats["total_elapsed_s"] / req, 3) if req > 0 else 0
            resp = {
                "status":         "online",
                "uptime_s":       up,
                "requests":       req,
                "errors":         _stats["errors"],
                "total_tokens":   _stats["total_tokens"],
                "avg_elapsed_s":  avg,
                "port":           PORT,
                "vulcan":         _VULCAN_ACTIVE,
                "vulcan_detail":  _VULCAN_MSG,
                "boot_perf":      dict(_boot_perf),
                "telemetry_hotspots": _telemetry_hotspots(),
            }
            return

        req_data   = json.loads(line)
        prompt     = str(req_data.get("prompt", "")).strip()
        max_tokens = max(1, min(int(req_data.get("max_tokens", 128)), 2048))

        if not prompt:
            resp = {"output": "", "elapsed_s": 0, "error": "prompt vazio"}
        else:
            _stats["requests"] += 1
            try:
                output, elapsed = _infer(prompt, max_tokens)
                _stats["total_tokens"]    += max_tokens
                _stats["total_elapsed_s"] += elapsed
                resp = {"output": output, "elapsed_s": elapsed, "error": None}
            except Exception as e:
                _stats["errors"] += 1
                resp = {
                    "output":    "",
                    "elapsed_s": 0,
                    "error":     str(e),
                    "traceback": traceback.format_exc(),
                }

    except json.JSONDecodeError as e:
        resp = {"output": "", "elapsed_s": 0, "error": f"JSON invalido: {e}"}
    except Exception as e:
        resp = {
            "output":    "",
            "elapsed_s": 0,
            "error":     f"handler: {e}",
            "traceback": traceback.format_exc(),
        }
    finally:
        try:
            conn.settimeout(None)
            conn.sendall((json.dumps(resp, ensure_ascii=False) + "\n").encode())
        except Exception:
            pass
        conn.close()


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def _serve() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(BACKLOG)
    srv.settimeout(1.0)
    PID_FILE.write_text(str(os.getpid()))
    print(f"[SRV] PID={os.getpid()}  Porta={PORT}", flush=True)

    while True:
        try:
            conn, _ = srv.accept()
            threading.Thread(target=_handle, args=(conn,), daemon=True).start()
        except socket.timeout:
            continue
        except KeyboardInterrupt:
            print("\n[SRV] Encerrando...", flush=True)
            _shutdown()
            break
        except Exception as e:
            print(f"[SRV] accept error: {e}", flush=True)
            traceback.print_exc()


def _shutdown() -> None:
    global _llm
    if _llm is not None:
        try:
            _llm.close()
        except Exception:
            pass
        _llm = None
    if _VULCAN_ACTIVE:
        try:
            from doxoade.tools.vulcan.runtime import uninstall_meta_finder
            uninstall_meta_finder()
        except Exception:
            pass
    _flush_telemetry_snapshot()
    PID_FILE.unlink(missing_ok=True)
    print("[SRV] Modelo liberado.", flush=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class ServerCLI:
    """Interface de linha de comando para orn-server."""

    def run(self, args: list[str]) -> None:
        if not args or args[0] == "start":
            self._start(background="--bg" in args)
        elif args[0] == "stop":
            self._stop()
        elif args[0] == "status":
            self._status()
        elif args[0] == "ask":
            prompt = " ".join(args[1:]) if len(args) > 1 else ""
            tokens = 128
            if "--tokens" in args:
                idx = args.index("--tokens")
                tokens = int(args[idx + 1]) if idx + 1 < len(args) else 128
            self._ask(prompt, tokens)
        else:
            self._help()

    def _start(self, background: bool = False) -> None:
        if self._is_online():
            print(f"[SRV] Servidor ja rodando na porta {PORT}.")
            return
        if background:
            log = open(LOG_FILE, "w")
            subprocess.Popen(
                [sys.executable, "-m", "engine.server", "start"],
                stdout=log, stderr=log,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            print(f"[SRV] Iniciado em background. Log: {LOG_FILE}")
            print(f"[SRV] Aguarde ~5s e verifique: orn-server status")
        else:
            _load_model()
            _serve()

    def _stop(self) -> None:
        if not PID_FILE.exists():
            print("[SRV] Nenhum servidor ativo (server.pid nao encontrado).")
            return
        pid = int(PID_FILE.read_text().strip())
        try:
            import signal
            os.kill(pid, signal.SIGTERM)
            PID_FILE.unlink(missing_ok=True)
            print(f"[SRV] Encerrado (PID {pid}).")
        except ProcessLookupError:
            PID_FILE.unlink(missing_ok=True)
            print(f"[SRV] Processo {pid} ja encerrado.")
        except Exception as e:
            print(f"[SRV] Erro ao parar: {e}")

    def _status(self) -> None:
        resp = self._query_status()
        if resp is None:
            print("[SRV] Offline.")
            return
        up = resp.get("uptime_s", 0)
        h, rem = divmod(int(up), 3600)
        m, s   = divmod(rem, 60)
        print(f"  Status:      ONLINE")
        print(f"  Uptime:      {h:02d}:{m:02d}:{s:02d}")
        print(f"  Requests:    {resp['requests']}")
        print(f"  Errors:      {resp['errors']}")
        print(f"  Tokens:      {resp['total_tokens']}")
        print(f"  Avg latency: {resp.get('avg_elapsed_s', 0)}s")
        print(f"  Porta:       {resp.get('port', PORT)}")
        vulcan_str = "ATIVO" if resp.get("vulcan") else "Python puro"
        print(f"  Vulcan:      {vulcan_str}")
        if not resp.get("vulcan"):
            for line in resp.get("vulcan_detail", "").splitlines()[:4]:
                print(f"               {line}")
        boot_perf = resp.get("boot_perf", {})
        if boot_perf:
            print("  Boot perf:")
            print(f"    - vulcan_boot_ms={boot_perf.get('vulcan_boot_ms', 0)}")
            print(f"    - model_load_ms={boot_perf.get('model_load_ms', 0)}")
        hotspots = resp.get("telemetry_hotspots", [])
        if hotspots:
            print("  Telemetria (hotspots):")
            for row in hotspots[:3]:
                print(
                    "    - "
                    f"{row.get('name','?')} calls={row.get('calls', 0)} "
                    f"avg={row.get('avg_ms', 0)}ms p95={row.get('p95_ms', 0)}ms"
                )

    def _ask(self, prompt: str, max_tokens: int = 128) -> None:
        if not prompt:
            print("[ERRO] Forneca um prompt: orn-server ask 'sua pergunta'")
            return
        resp = self._query(prompt, max_tokens)
        if resp is None:
            print("[ERRO] Servidor offline. Execute: orn-server start")
            return
        if resp.get("error"):
            print(f"[ERRO] {resp['error']}")
            if resp.get("traceback"):
                print(resp["traceback"])
        else:
            print(resp["output"])
            print(f"\n[{resp['elapsed_s']}s]")

    def _help(self) -> None:
        print("orn-server <comando> [opcoes]")
        print("  start          inicia servidor (foreground)")
        print("  start --bg     inicia em background")
        print("  stop           para o servidor")
        print("  status         exibe uptime e estatisticas")
        print('  ask "prompt"   consulta direta ao modelo')
        print('  ask "prompt" --tokens 200')

    def _is_online(self) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect((HOST, PORT))
            return True
        except (ConnectionRefusedError, OSError):
            return False

    def _query_status(self) -> dict | None:
        return self._raw_query(b"STATUS\n")

    def _query(self, prompt: str, max_tokens: int) -> dict | None:
        payload = (json.dumps({"prompt": prompt, "max_tokens": max_tokens}) + "\n").encode()
        return self._raw_query(payload)

    def _raw_query(self, payload: bytes) -> dict | None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(60.0)
                s.connect((HOST, PORT))
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
        except Exception:
            return None