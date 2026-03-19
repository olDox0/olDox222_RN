# -*- coding: utf-8 -*-
# engine/server/server.py
"""
ORN — SiCDox Server
Servidor local de inferência. Carrega o modelo UMA VEZ, serve continuamente.

Protocolo (TCP local):
  Request:  JSON linha {"prompt": "...", "max_tokens": 128}
  Response: JSON linha {"output": "...", "elapsed_s": 1.23, "error": null}

Comando especial:
  b"STATUS\n" -> JSON com uptime, requests, errors e métricas

OSL-3:  Modelo carregado uma vez no startup.
OSL-7:  Toda requisição retorna JSON com "error" explícito.
OSL-15: Erros de inferência não derrubam o servidor.
OSL-18: stdlib + dependências do projeto.
God: Hefesto — fornalha contínua; a forja não apaga entre peças.
"""

from __future__ import annotations

import json
import os
import platform
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from engine.telemetry import GLOBAL_TELEMETRY, orn_probe

try:
    import resource as _resource  # Unix only
    _HAS_RESOURCE = True
except ImportError:
    _HAS_RESOURCE = False


HOST = "127.0.0.1"
PORT = 8371
BACKLOG = 4
RECV_SZ = 65536

PID_FILE = Path("server.pid")
LOG_FILE = Path("server.log")

_llm = None
_cfg = None
_lock = threading.Lock()

_stats: dict[str, Any] = {
    "requests": 0,
    "errors": 0,
    "total_tokens": 0,
    "total_elapsed_s": 0.0,
    "start": None,
    "infer_calls": 0,
    "last_infer_s": 0.0,
    "last_prompt_chars": 0,
    "last_output_chars": 0,
    "last_max_tokens": 0,
    "sum_prompt_chars": 0,
    "sum_output_chars": 0,
    "last_llm_call_ms": 0.0,
    "last_lock_wait_ms": 0.0,
    "sum_llm_call_ms": 0.0,
    "sum_lock_wait_ms": 0.0,
}

_boot_perf = {
    "vulcan_boot_ms": 0.0,
    "model_load_ms": 0.0,
}

_VULCAN_ACTIVE = False
_VULCAN_MSG = ""


# ---------------------------------------------------------------------------
# Bootstrap do doxoade / Vulcan
# ---------------------------------------------------------------------------

def _looks_like_doxoade_root(path_str: str | None) -> bool:
    if not path_str:
        return False
    try:
        p = Path(path_str).resolve()
    except Exception:
        return False
    return (p / "doxoade" / "__init__.py").exists()


def _discover_doxoade_root() -> str | None:
    env_root = os.environ.get("DOXOADE_ROOT")
    if _looks_like_doxoade_root(env_root):
        return str(Path(env_root).resolve())

    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "doxoade" / "__init__.py").exists():
            return str(parent)

    return None


def _vulcan_boot() -> tuple[bool, str]:
    root = _discover_doxoade_root()
    if root and root not in sys.path:
        sys.path.insert(0, root)
        os.environ["DOXOADE_ROOT"] = root

    try:
        import doxoade  # noqa: F401
    except ImportError as exc:
        return False, (
            f"'doxoade' nao encontrado em sys.path nem instalado no venv.\n"
            f"ImportError: {exc}\n"
            f"Solucoes:\n"
            f"  a) Execute na raiz do projeto\n"
            f"  b) pip install -e <raiz>\n"
            f"  c) defina DOXOADE_ROOT=<raiz>\n"
        )

    try:
        from doxoade.tools.vulcan.runtime import find_vulcan_project_root, install_meta_finder

        root_path = find_vulcan_project_root(Path.cwd()) or find_vulcan_project_root(__file__)
        if root_path is None:
            return False, (
                "doxoade importado OK, mas '.doxoade/vulcan/bin' nao encontrado.\n"
                "Execute 'doxoade vulcan lib' antes de iniciar o servidor."
            )

        install_meta_finder(root_path)

        lib_bin = root_path / ".doxoade" / "vulcan" / "lib_bin"
        n_bins = len(list(lib_bin.glob("*.pyd"))) if lib_bin.exists() else 0
        return True, f"raiz='{root_path}' | {n_bins} binario(s) em lib_bin/"
    except Exception:
        return False, f"MetaFinder falhou:\n{traceback.format_exc()}"


_t_boot0 = time.monotonic()
_VULCAN_ACTIVE, _VULCAN_MSG = _vulcan_boot()
_boot_perf["vulcan_boot_ms"] = round((time.monotonic() - _t_boot0) * 1000.0, 3)

if _VULCAN_ACTIVE:
    print(f"[VULCAN] OK — {_VULCAN_MSG}", flush=True)
else:
    for _line in _VULCAN_MSG.splitlines():
        print(f"[VULCAN] {_line}", flush=True)
    print("[VULCAN] Continuando com Python puro (OSL-15).", flush=True)


# ---------------------------------------------------------------------------
# Telemetria / utilidades
# ---------------------------------------------------------------------------

def _observe_telemetry(name: str, elapsed_ms: float, *, category: str = "exec") -> None:
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


def _flush_telemetry_snapshot() -> None:
    try:
        GLOBAL_TELEMETRY.flush_json(Path("telemetry") / "server_runtime.json")
    except Exception:
        pass


def _system_perf_snapshot() -> dict[str, Any]:
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

    return {
        "pid": os.getpid(),
        "threads": threading.active_count(),
        "cpu_count": os.cpu_count() or 0,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "rss_mb": rss_mb,
        "load_1m": load_1m,
    }


def _json_line(resp: dict[str, Any]) -> bytes:
    return (json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8")


def _read_line_from_socket(conn: socket.socket, timeout: float = 10.0) -> str:
    conn.settimeout(timeout)
    data = bytearray()
    while True:
        chunk = conn.recv(RECV_SZ)
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in data:
            break
    return data.decode("utf-8", errors="replace").strip()


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

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

    t0 = time.monotonic()

    kwargs: dict[str, Any] = {
        "model_path": str(_cfg.model_path),
        "n_ctx": _cfg.n_ctx,
        "n_threads": _cfg.n_threads,
        "n_gpu_layers": _cfg.n_gpu_layers,
        "n_batch": _cfg.n_batch,
        "n_threads_batch": _cfg.n_threads_batch,
        "use_mmap": _cfg.use_mmap,
        "use_mlock": _cfg.use_mlock,
        "verbose": False,
    }

    if _cfg.cache_type_k:
        kwargs["type_k"] = _cfg.cache_type_k
    if _cfg.cache_type_v:
        kwargs["type_v"] = _cfg.cache_type_v
    if _cfg.rope_freq_base is not None:
        kwargs["rope_freq_base"] = _cfg.rope_freq_base
    if _cfg.rope_freq_scale is not None:
        kwargs["rope_freq_scale"] = _cfg.rope_freq_scale
    if _cfg.flash_attn is not None:
        kwargs["flash_attn"] = _cfg.flash_attn
    if _cfg.no_alloc:
        kwargs["no_alloc"] = True
    if _cfg.pin_threads:
        kwargs["pin_threads"] = True
    if _cfg.cont_batching:
        kwargs["cont_batching"] = True

    try:
        _llm = Llama(**kwargs)
    except TypeError as exc:
        unsupported = (
            "type_k", "type_v", "rope_freq_base", "rope_freq_scale", "flash_attn",
            "no_alloc", "use_mmap", "pin_threads", "cont_batching",
        )
        if not any(tok in str(exc) for tok in unsupported):
            raise
        for tok in unsupported:
            kwargs.pop(tok, None)
        _llm = Llama(**kwargs)

    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 3)
    _boot_perf["model_load_ms"] = elapsed_ms
    _observe_telemetry("server.boot.model_load", elapsed_ms, category="boot")
    _stats["start"] = time.monotonic()
    print(f"[BOOT] Pronto em {round(elapsed_ms / 1000.0, 1)}s — {HOST}:{PORT}", flush=True)


@orn_probe(category="exec", critical=True, probe_name="server.infer")
def _infer(prompt: str, max_tokens: int) -> tuple[str, float]:
    if _llm is None or _cfg is None:
        raise RuntimeError("Modelo nao carregado.")

    prompt_full = (
        f"<|im_start|>system\n{_cfg.system_prompt}<|im_end|>\n"
        f"<|im_start|>user\n{prompt}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

    t0 = time.monotonic()
    t_wait0 = t0

    with _lock:
        lock_wait_ms = (time.monotonic() - t_wait0) * 1000.0
        t_llm0 = time.monotonic()

        infer_kwargs: dict[str, Any] = {
            "max_tokens": max_tokens,
            "stop": ["<|im_end|>", "</s>"],
            "echo": False,
            "temperature": _cfg.temperature,
            "top_p": _cfg.top_p,
            "top_k": _cfg.top_k,
            "repeat_penalty": _cfg.repeat_penalty,
        }

        if _cfg.min_p is not None:
            infer_kwargs["min_p"] = float(_cfg.min_p)

        out = _llm(prompt_full, **infer_kwargs)
        llm_call_ms = (time.monotonic() - t_llm0) * 1000.0

    _observe_telemetry("server.infer.lock_wait", lock_wait_ms)
    _observe_telemetry("server.infer.llm_call", llm_call_ms)

    with _lock:
        _stats["last_lock_wait_ms"] = round(lock_wait_ms, 4)
        _stats["last_llm_call_ms"] = round(llm_call_ms, 4)
        _stats["sum_lock_wait_ms"] += lock_wait_ms
        _stats["sum_llm_call_ms"] += llm_call_ms

    elapsed = round(time.monotonic() - t0, 3)
    return out["choices"][0]["text"].strip(), elapsed


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def _telemetry_hotspots(limit: int = 3) -> list[dict[str, Any]]:
    try:
        snap = GLOBAL_TELEMETRY.snapshot()
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
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


def _handle_status() -> dict[str, Any]:
    up = round(time.monotonic() - _stats["start"], 1) if _stats["start"] else 0
    req = _stats["requests"]
    avg = round(_stats["total_elapsed_s"] / req, 3) if req > 0 else 0
    infer_calls = _stats["infer_calls"]

    avg_prompt_chars = round(_stats["sum_prompt_chars"] / infer_calls, 2) if infer_calls else 0
    avg_output_chars = round(_stats["sum_output_chars"] / infer_calls, 2) if infer_calls else 0
    last_tokens_per_s = round((_stats["last_max_tokens"] / _stats["last_infer_s"]) if _stats["last_infer_s"] else 0, 3)
    total_tokens_per_s = round((_stats["total_tokens"] / _stats["total_elapsed_s"]) if _stats["total_elapsed_s"] else 0, 3)
    last_output_chars_per_s = round((_stats["last_output_chars"] / _stats["last_infer_s"]) if _stats["last_infer_s"] else 0, 3)
    avg_lock_wait_ms = round((_stats["sum_lock_wait_ms"] / infer_calls) if infer_calls else 0, 4)
    avg_llm_call_ms = round((_stats["sum_llm_call_ms"] / infer_calls) if infer_calls else 0, 4)
    last_non_llm_ms = round(max((_stats["last_infer_s"] * 1000.0) - _stats["last_llm_call_ms"], 0.0), 4)
    last_llm_share_pct = round((_stats["last_llm_call_ms"] / (_stats["last_infer_s"] * 1000.0) * 100.0) if _stats["last_infer_s"] else 0, 2)

    return {
        "status": "online",
        "uptime_s": up,
        "requests": req,
        "errors": _stats["errors"],
        "total_tokens": _stats["total_tokens"],
        "avg_elapsed_s": avg,
        "port": PORT,
        "vulcan": _VULCAN_ACTIVE,
        "vulcan_detail": _VULCAN_MSG,
        "boot_perf": dict(_boot_perf),
        "system_perf": _system_perf_snapshot(),
        "ai_perf": {
            "infer_calls": infer_calls,
            "last_infer_s": _stats["last_infer_s"],
            "last_max_tokens": _stats["last_max_tokens"],
            "last_prompt_chars": _stats["last_prompt_chars"],
            "last_output_chars": _stats["last_output_chars"],
            "avg_prompt_chars": avg_prompt_chars,
            "avg_output_chars": avg_output_chars,
            "last_tokens_per_s": last_tokens_per_s,
            "total_tokens_per_s": total_tokens_per_s,
            "last_output_chars_per_s": last_output_chars_per_s,
            "last_lock_wait_ms": _stats["last_lock_wait_ms"],
            "last_llm_call_ms": _stats["last_llm_call_ms"],
            "avg_lock_wait_ms": avg_lock_wait_ms,
            "avg_llm_call_ms": avg_llm_call_ms,
            "last_non_llm_ms": last_non_llm_ms,
            "last_llm_share_pct": last_llm_share_pct,
        },
        "telemetry_hotspots": _telemetry_hotspots(),
    }


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def _handle(conn: socket.socket) -> None:
    resp: dict[str, Any] = {"output": "", "elapsed_s": 0, "error": "internal error"}

    try:
        line = _read_line_from_socket(conn, timeout=10.0)
        if not line:
            resp = {"output": "", "elapsed_s": 0, "error": "payload vazio"}
            return

        if line.upper() == "STATUS":
            resp = _handle_status()
            return

        req_data = json.loads(line)
        prompt = str(req_data.get("prompt", "")).strip()
        max_tokens = max(1, min(int(req_data.get("max_tokens", 128)), 2048))

        if not prompt:
            resp = {"output": "", "elapsed_s": 0, "error": "prompt vazio"}
            return

        with _lock:
            _stats["requests"] += 1

        try:
            output, elapsed = _infer(prompt, max_tokens)
            with _lock:
                _stats["total_tokens"] += max_tokens
                _stats["total_elapsed_s"] += elapsed
                _stats["infer_calls"] += 1
                _stats["last_infer_s"] = elapsed
                _stats["last_prompt_chars"] = len(prompt)
                _stats["last_output_chars"] = len(output)
                _stats["last_max_tokens"] = max_tokens
                _stats["sum_prompt_chars"] += len(prompt)
                _stats["sum_output_chars"] += len(output)

            resp = {"output": output, "elapsed_s": elapsed, "error": None}
        except Exception as e:
            with _lock:
                _stats["errors"] += 1
            resp = {
                "output": "",
                "elapsed_s": 0,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }

    except json.JSONDecodeError as e:
        resp = {"output": "", "elapsed_s": 0, "error": f"JSON invalido: {e}"}
    except Exception as e:
        resp = {
            "output": "",
            "elapsed_s": 0,
            "error": f"handler: {e}",
            "traceback": traceback.format_exc(),
        }
    finally:
        try:
            conn.sendall(_json_line(resp))
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Serve / shutdown
# ---------------------------------------------------------------------------

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


def _sigterm_handler(signum, frame):
    print("[SRV] Sinal recebido — iniciando shutdown ordenado.", flush=True)
    try:
        _shutdown()
    except Exception:
        pass
    sys.exit(0)


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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class ServerCLI:
    """Interface de linha de comando para orn-server."""

    def run(self, args: list[str]) -> None:
        if not args or args[0] == "start":
            start_args = args[1:] if args else []
            background = "--bg" in start_args

            cache_type_k = self._arg_value(start_args, "--cache-type-k")
            cache_type_v = self._arg_value(start_args, "--cache-type-v")
            active_window = self._arg_value(start_args, "--active-window")
            rope_freq_base = self._arg_value(start_args, "--rope-freq-base")
            rope_freq_scale = self._arg_value(start_args, "--rope-freq-scale")
            flash_attn = self._arg_value(start_args, "--flash-attn")
            min_p = self._arg_value(start_args, "--min-p")
            pin_threads = "--pin-threads" in start_args
            cont_batching = "--cont-batching" in start_args
            no_mmap = "--no-mmap" in start_args
            no_alloc = "--no-alloc" in start_args

            self._start(
                background=background,
                cache_type_k=cache_type_k,
                cache_type_v=cache_type_v,
                active_window=active_window,
                rope_freq_base=rope_freq_base,
                rope_freq_scale=rope_freq_scale,
                flash_attn=flash_attn,
                min_p=min_p,
                pin_threads=pin_threads,
                cont_batching=cont_batching,
                no_mmap=no_mmap,
                no_alloc=no_alloc,
            )
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

    def _start(
        self,
        background: bool = False,
        cache_type_k: str | None = None,
        cache_type_v: str | None = None,
        active_window: str | None = None,
        rope_freq_base: str | None = None,
        rope_freq_scale: str | None = None,
        flash_attn: str | None = None,
        min_p: str | None = None,
        pin_threads: bool = False,
        cont_batching: bool = False,
        no_mmap: bool = False,
        no_alloc: bool = False,
    ) -> None:
        if self._is_online():
            print(f"[SRV] Servidor ja rodando na porta {PORT}.")
            return

        if background:
            log = open(LOG_FILE, "w", encoding="utf-8")
            child_args = [sys.executable, "-m", "engine.server.server", "start"]
            if cache_type_k:
                child_args += ["--cache-type-k", cache_type_k]
            if cache_type_v:
                child_args += ["--cache-type-v", cache_type_v]
            if active_window:
                child_args += ["--active-window", active_window]
            if rope_freq_base:
                child_args += ["--rope-freq-base", rope_freq_base]
            if rope_freq_scale:
                child_args += ["--rope-freq-scale", rope_freq_scale]
            if flash_attn:
                child_args += ["--flash-attn", flash_attn]
            if min_p:
                child_args += ["--min-p", min_p]
            if pin_threads:
                child_args += ["--pin-threads"]
            if cont_batching:
                child_args += ["--cont-batching"]
            if no_mmap:
                child_args += ["--no-mmap"]
            if no_alloc:
                child_args += ["--no-alloc"]

            subprocess.Popen(
                child_args,
                stdout=log,
                stderr=log,
                env=self._start_env(
                    cache_type_k,
                    cache_type_v,
                    active_window,
                    rope_freq_base,
                    rope_freq_scale,
                    flash_attn,
                    min_p,
                    pin_threads,
                    cont_batching,
                    no_mmap,
                    no_alloc,
                ),
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            log.close()
            print(f"[SRV] Iniciado em background. Log: {LOG_FILE}")
            print("[SRV] Aguarde ~5s e verifique: orn-server status")
            return

        try:
            signal.signal(signal.SIGTERM, _sigterm_handler)
            signal.signal(signal.SIGINT, _sigterm_handler)
        except Exception:
            pass

        self._apply_start_env(
            cache_type_k,
            cache_type_v,
            active_window,
            rope_freq_base,
            rope_freq_scale,
            flash_attn,
            min_p,
            pin_threads,
            cont_batching,
            no_mmap,
            no_alloc,
        )
        _load_model()
        _serve()

    def _stop(self) -> None:
        if not PID_FILE.exists():
            print("[SRV] Nenhum servidor ativo (server.pid nao encontrado).")
            return

        try:
            pid = int(PID_FILE.read_text().strip())
        except Exception:
            print("[SRV] PID file corrupto.")
            PID_FILE.unlink(missing_ok=True)
            return

        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                os.kill(pid, signal.SIGTERM)

            wait_timeout = 5.0
            waited = 0.0
            interval = 0.1
            while waited < wait_timeout:
                try:
                    if os.name != "nt":
                        os.kill(pid, 0)
                    else:
                        proc = None
                    time.sleep(interval)
                    waited += interval
                except OSError:
                    break
            else:
                if os.name != "nt":
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except Exception:
                        pass

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
        m, s = divmod(rem, 60)

        print("  Status:      ONLINE")
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

        system_perf = resp.get("system_perf", {})
        if system_perf:
            print("  System perf:")
            print(f"    - pid={system_perf.get('pid', 0)} threads={system_perf.get('threads', 0)}")
            print(f"    - cpu_count={system_perf.get('cpu_count', 0)} load_1m={system_perf.get('load_1m', 0)}")
            print(f"    - rss_mb={system_perf.get('rss_mb', 0)}")

        ai_perf = resp.get("ai_perf", {})
        if ai_perf:
            print("  IA perf:")
            print(f"    - infer_calls={ai_perf.get('infer_calls', 0)}")
            print(f"    - last_infer_s={ai_perf.get('last_infer_s', 0)}")
            print(f"    - last_tokens_per_s={ai_perf.get('last_tokens_per_s', 0)}")
            print(f"    - total_tokens_per_s={ai_perf.get('total_tokens_per_s', 0)}")
            print(f"    - last_prompt_chars={ai_perf.get('last_prompt_chars', 0)}")
            print(f"    - last_output_chars={ai_perf.get('last_output_chars', 0)}")
            print(f"    - last_lock_wait_ms={ai_perf.get('last_lock_wait_ms', 0)}")
            print(f"    - last_llm_call_ms={ai_perf.get('last_llm_call_ms', 0)}")
            print(f"    - last_non_llm_ms={ai_perf.get('last_non_llm_ms', 0)}")
            print(f"    - last_llm_share_pct={ai_perf.get('last_llm_share_pct', 0)}")

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

    @staticmethod
    def _arg_value(args: list[str], flag: str) -> str | None:
        if flag not in args:
            return None
        idx = args.index(flag)
        if idx + 1 >= len(args):
            return None
        value = args[idx + 1].strip()
        return value or None

    @staticmethod
    def _start_env(
        cache_type_k: str | None,
        cache_type_v: str | None,
        active_window: str | None,
        rope_freq_base: str | None,
        rope_freq_scale: str | None,
        flash_attn: str | None,
        min_p: str | None,
        pin_threads: bool,
        cont_batching: bool,
        no_mmap: bool,
        no_alloc: bool,
    ) -> dict[str, str]:
        env = os.environ.copy()
        if cache_type_k:
            env["ORN_CACHE_TYPE_K"] = cache_type_k
        if cache_type_v:
            env["ORN_CACHE_TYPE_V"] = cache_type_v
        if active_window:
            env["ORN_ACTIVE_WINDOW"] = active_window
        if rope_freq_base:
            env["ORN_ROPE_FREQ_BASE"] = rope_freq_base
        if rope_freq_scale:
            env["ORN_ROPE_FREQ_SCALE"] = rope_freq_scale
        if flash_attn:
            env["ORN_FLASH_ATTN"] = flash_attn
        if min_p:
            env["ORN_MIN_P"] = min_p
        if pin_threads:
            env["ORN_PIN_THREADS"] = "1"
        if cont_batching:
            env["ORN_CONT_BATCHING"] = "1"
        if no_mmap:
            env["ORN_USE_MMAP"] = "0"
        if no_alloc:
            env["ORN_NO_ALLOC"] = "1"

        root = _discover_doxoade_root()
        if root:
            env["DOXOADE_ROOT"] = root
        return env

    def _apply_start_env(
        self,
        cache_type_k: str | None,
        cache_type_v: str | None,
        active_window: str | None,
        rope_freq_base: str | None,
        rope_freq_scale: str | None,
        flash_attn: str | None,
        min_p: str | None,
        pin_threads: bool,
        cont_batching: bool,
        no_mmap: bool,
        no_alloc: bool,
    ) -> None:
        env = self._start_env(
            cache_type_k,
            cache_type_v,
            active_window,
            rope_freq_base,
            rope_freq_scale,
            flash_attn,
            min_p,
            pin_threads,
            cont_batching,
            no_mmap,
            no_alloc,
        )
        os.environ.update(env)

    def _help(self) -> None:
        print("orn-server <comando> [opcoes]")
        print("  start          inicia servidor (foreground)")
        print("  start --bg     inicia em background")
        print("  start --active-window 512")
        print("  start --cache-type-k q8_0 --cache-type-v q4_0")
        print("  start --cache-type-k none --cache-type-v off")
        print("  start --rope-freq-base 10000 --rope-freq-scale 1.0")
        print("  start --flash-attn on")
        print("  start --min-p 0.01")
        print("  start --pin-threads --cont-batching")
        print("  start --no-mmap --no-alloc")
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

    def _query_status(self) -> dict[str, Any] | None:
        return self._raw_query(b"STATUS\n")

    def _query(self, prompt: str, max_tokens: int) -> dict[str, Any] | None:
        payload = (json.dumps({"prompt": prompt, "max_tokens": max_tokens}) + "\n").encode("utf-8")
        return self._raw_query(payload)

    def _raw_query(self, payload: bytes) -> dict[str, Any] | None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(60.0)
                s.connect((HOST, PORT))
                s.settimeout(None)
                s.sendall(payload)
                data = bytearray()
                while True:
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if data.endswith(b"\n"):
                        break
            return json.loads(data.decode("utf-8").strip())
        except Exception:
            return None


def main(argv: list[str] | None = None) -> None:
    cli = ServerCLI()
    cli.run(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    main()