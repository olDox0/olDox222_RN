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
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------

HOST     = "127.0.0.1"
PORT     = 8371
BACKLOG  = 4
RECV_SZ  = 65536

# PID e log ficam no diretorio do projeto (onde orn-server e chamado)
PID_FILE = Path("server.pid")
LOG_FILE = Path("server.log")


# ---------------------------------------------------------------------------
# Estado global (OSL-3)
# ---------------------------------------------------------------------------

_llm   = None
_cfg   = None
_stats = {"requests": 0, "errors": 0, "total_tokens": 0, "start": None}
_lock  = threading.Lock()


# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------

def _load_model() -> None:
    global _llm, _cfg
    from engine.core.llm_bridge import BridgeConfig
    from llama_cpp import Llama

    _cfg = BridgeConfig()
    if not _cfg.model_path.exists():
        print(f"[ERRO] Modelo nao encontrado: {_cfg.model_path}", flush=True)
        sys.exit(1)

    print(f"[BOOT] {_cfg.model_path.name}", flush=True)
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
    _stats["start"] = time.monotonic()
    print(f"[BOOT] Pronto em {elapsed}s — {HOST}:{PORT}", flush=True)


# ---------------------------------------------------------------------------
# Inferencia
# ---------------------------------------------------------------------------

def _infer(prompt: str, max_tokens: int) -> tuple[str, float]:
    prompt_full = (
        f"<|im_start|>system\n{_cfg.system_prompt}<|im_end|>\n"
        f"<|im_start|>user\n{prompt}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    t0 = time.monotonic()
    with _lock:
        out = _llm(prompt_full, max_tokens=max_tokens,
                   stop=["<|im_end|>", "</s>"], echo=False)
    elapsed = round(time.monotonic() - t0, 3)
    return out["choices"][0]["text"].strip(), elapsed


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _handle(conn: socket.socket) -> None:
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
            return

        # STATUS especial
        if line.upper() == "STATUS":
            up = round(time.monotonic() - _stats["start"], 1) if _stats["start"] else 0
            resp = {"status": "online", "uptime_s": up,
                    "requests": _stats["requests"],
                    "errors": _stats["errors"],
                    "total_tokens": _stats["total_tokens"],
                    "port": PORT}
            conn.sendall((json.dumps(resp) + "\n").encode())
            return

        req        = json.loads(line)
        prompt     = str(req.get("prompt", "")).strip()
        max_tokens = max(1, min(int(req.get("max_tokens", 128)), 2048))

        if not prompt:
            resp = {"output": "", "elapsed_s": 0, "error": "prompt vazio"}
        else:
            _stats["requests"] += 1
            try:
                output, elapsed = _infer(prompt, max_tokens)
                _stats["total_tokens"] += max_tokens
                resp = {"output": output, "elapsed_s": elapsed, "error": None}
            except Exception as e:
                _stats["errors"] += 1
                resp = {"output": "", "elapsed_s": 0, "error": str(e)}

    except json.JSONDecodeError as e:
        resp = {"output": "", "elapsed_s": 0, "error": f"JSON invalido: {e}"}
    except Exception as e:
        resp = {"output": "", "elapsed_s": 0, "error": f"handler: {e}"}
    finally:
        try:
            conn.settimeout(None)
            conn.sendall((json.dumps(resp, ensure_ascii=False) + "\n").encode())
        except Exception:
            pass
        conn.close()


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------

def _serve() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(BACKLOG)
    # Timeout de 1s: accept() nao bloqueia para sempre
    # Ctrl+C e capturado em ate 1s (mesmo fix do orn-web)
    srv.settimeout(1.0)
    PID_FILE.write_text(str(os.getpid()))

    print(f"[SRV] PID={os.getpid()}  Porta={PORT}", flush=True)

    while True:
        try:
            conn, _ = srv.accept()
            threading.Thread(target=_handle, args=(conn,), daemon=True).start()
        except socket.timeout:
            continue   # sem conexao no ultimo 1s — verifica KeyboardInterrupt
        except KeyboardInterrupt:
            print("\n[SRV] Encerrando...", flush=True)
            _shutdown()
            break
        except Exception as e:
            print(f"[SRV] accept error: {e}", flush=True)


def _shutdown() -> None:
    global _llm
    if _llm is not None:
        try:
            _llm.close()
        except Exception:
            pass
        _llm = None
    PID_FILE.unlink(missing_ok=True)
    print("[SRV] Modelo liberado.", flush=True)


# ---------------------------------------------------------------------------
# CLI do servidor
# ---------------------------------------------------------------------------

class ServerCLI:
    """Interface de linha de comando para orn-server."""

    def run(self, args: list[str]) -> None:
        if not args or args[0] == "start":
            bg = "--bg" in args
            self._start(background=bg)
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

    # ----------------------------------------------------------------

    def _start(self, background: bool = False) -> None:
        if self._is_online():
            print(f"[SRV] Servidor ja rodando na porta {PORT}.")
            return

        if background:
            log = open(LOG_FILE, "w")
            subprocess.Popen(
                [sys.executable, "-m", "engine.server", "start"],
                stdout=log, stderr=log,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
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
        print(f"  Status:   ONLINE")
        print(f"  Uptime:   {h:02d}:{m:02d}:{s:02d}")
        print(f"  Requests: {resp['requests']}")
        print(f"  Errors:   {resp['errors']}")
        print(f"  Tokens:   {resp['total_tokens']}")
        print(f"  Porta:    {resp.get('port', PORT)}")

    def _ask(self, prompt: str, max_tokens: int = 128) -> None:
        if not prompt:
            print("[ERRO] Forneça um prompt: orn-server ask 'sua pergunta'")
            return
        resp = self._query(prompt, max_tokens)
        if resp is None:
            print("[ERRO] Servidor offline. Execute: orn-server start")
            return
        if resp.get("error"):
            print(f"[ERRO] {resp['error']}")
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

    # ----------------------------------------------------------------
    # Helpers de socket (reutilizados pelo server_client.py)
    # ----------------------------------------------------------------

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
                s.settimeout(2.0)
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