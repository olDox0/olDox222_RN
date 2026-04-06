# -*- coding: utf-8 -*-
"""
ORN — Web Interface Server (Apolo)
Servidor HTTP local que serve a interface web e faz proxy para o SiCDox Server.

Porta: 8372 (web) -> 8371 (inferencia)
Uso:
  orn-web start          inicia e abre o browser
  orn-web start --no-browser  inicia sem abrir browser
  orn-web stop           para o servidor

Mudancas v0.3:
  - Auto-search two-pass integrado no POST /ask
  - Response JSON inclui source e source_url
  - renderMarkdown: indentacao e tabs preservados
  - Badge de fonte exibido na interface

OSL-18: stdlib apenas (http.server, json, threading, webbrowser, socket).
OSL-15: Erros de proxy nao derrubam o servidor web.
God: Apolo — da forma e clareza ao pensamento do Hefesto.
"""

from __future__ import annotations

import json
import os
# [DOX-UNUSED] import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from engine.web import web_proxy

WEB_PORT   = 8372
INFER_PORT = 8371
HOST       = "127.0.0.1"
PID_FILE   = Path("web_server.pid")


# ---------------------------------------------------------------------------
# HTML da interface
# ---------------------------------------------------------------------------

from engine.web.web_page import HTML


# ---------------------------------------------------------------------------
# Auto-search two-pass (inline — sem import do engine para manter stdlib)
# ---------------------------------------------------------------------------

def _decide_search(prompt: str) -> str | None:
    return web_proxy.decide_search(prompt, host=HOST, infer_port=INFER_PORT)


def _parse_search_decision(text: str) -> str | None:
    return web_proxy.parse_search_decision(text)


def _run_crawler(query: str) -> tuple[str, str, str]:
    return web_proxy.run_crawler(query)


def _suggest_max_tokens(prompt: str) -> int:
    """Escolhe max_tokens automaticamente para manter paridade com `orn think`."""
    try:
        from engine.core.executive import _adaptive_max_tokens  # noqa: PLC0415

        return max(64, min(int(_adaptive_max_tokens(prompt)), 2048))
    except Exception:
        return 384


def _apply_code_hook_with_server_bridge(output: str, task: str, max_tokens: int) -> str:
    """Aplica o mesmo mecanismo de correção pós-inferência usado no restante do sistema."""
    try:
        from engine.thinking.code_hook import apply_code_hook  # noqa: PLC0415

        class ServerBridge:
            def ask(self, p: str, max_tokens: int = 256, **kwargs) -> str:
                r = _query_infer_raw(
                    (json.dumps({"prompt": p, "max_tokens": max_tokens}) + "\n").encode("utf-8")
                )
                return str(r.get("output", "")) if r else ""

        class DummyValidator:
            def validar_output(self, text: str, lang: str | None = None):
                return True, ""

        return apply_code_hook(
            output=output,
            task=task,
            bridge=ServerBridge(),
            validator=DummyValidator(),
            max_retries=1,
            run_isolated=True,
        )
    except Exception:
        return output


def _normalize_stream_event(raw: dict) -> dict | None:
    """Normaliza payloads stream vindos de versões diferentes do backend."""
    if not isinstance(raw, dict):
        return None
    if "event" in raw:
        return raw
    # Compatibilidade: resposta não-stream encapsulada como JSON único.
    if "output" in raw and "elapsed_s" in raw:
        return {
            "event": "done",
            "output": raw.get("output", ""),
            "elapsed_s": raw.get("elapsed_s", 0),
            "error": raw.get("error"),
        }
    if raw.get("error"):
        return {"event": "error", "error": raw.get("error")}
    return None


# ---------------------------------------------------------------------------
# Handler HTTP
# ---------------------------------------------------------------------------

class ORNHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        try:
            self.send_response(code)
            if ctype:
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", HTML.encode("utf-8"))
        elif self.path == "/status":
            resp = _query_infer_raw(b"STATUS\n")
            if resp is None:
                resp = {"status": "offline", "error": "orn-server nao encontrado"}
            self._send(200, "application/json", json.dumps(resp).encode())
        elif self.path == "/favicon.ico":
            self._send(204, "", b"")
        else:
            self._send(404, "", b"")

    def do_POST(self):
        if self.path == "/ask_stream":
            self._handle_ask_stream()
            return

        if self.path != "/ask":
            self._send(404, "", b"")
            return

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            req = json.loads(body)
        except Exception:
            req = {}

        prompt = str(req.get("prompt", "")).strip()
        if "max_tokens" in req:
            max_tokens = max(1, min(int(req.get("max_tokens", 128)), 2048))
        else:
            max_tokens = _suggest_max_tokens(prompt)

        if not prompt:
            resp = {"output": "", "elapsed_s": 0, "error": "prompt vazio",
                    "source": None, "source_url": None}
            self._send(200, "application/json",
                       json.dumps(resp, ensure_ascii=False).encode())
            return

        # ---------------------------------------------------------------
        # TWO-PASS AUTÔNOMO
        # 1ª pass: decide se precisa de busca
        # ---------------------------------------------------------------
        ctx_block  = ""
        source     = None
        source_url = None

        search_term = _decide_search(prompt)
        if search_term:
            ctx_block, source, source_url = _run_crawler(search_term)
            # Se crawler falhou — source fica None, continua sem contexto

        # Monta prompt final
        if ctx_block:
            full_prompt = ctx_block + "\n[TASK]\n" + prompt
        else:
            full_prompt = prompt

        # ---------------------------------------------------------------
        # 2ª pass: inferência com contexto
        # ---------------------------------------------------------------
        payload = (json.dumps({
            "prompt":     full_prompt,
            "max_tokens": max_tokens
        }) + "\n").encode()

        infer_resp = _query_infer_raw(payload)

        if infer_resp is None:
            resp = {"output": "", "elapsed_s": 0,
                    "error": "orn-server offline. Execute: orn-server start",
                    "source": None, "source_url": None}
        else:
            output = str(infer_resp.get("output", ""))
            output = _apply_code_hook_with_server_bridge(output, prompt, max_tokens)
            resp = {
                "output":     output,
                "elapsed_s":  infer_resp.get("elapsed_s", 0),
                "error":      infer_resp.get("error"),
                "source":     source or None,
                "source_url": source_url or None,
            }

        out = json.dumps(resp, ensure_ascii=False).encode()
        self._send(200, "application/json", out)

    def _handle_ask_stream(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            req = json.loads(body)
        except Exception:
            req = {}

        prompt = str(req.get("prompt", "")).strip()
        if "max_tokens" in req:
            max_tokens = max(1, min(int(req.get("max_tokens", 128)), 2048))
        else:
            max_tokens = _suggest_max_tokens(prompt)

        if not prompt:
            self._send(
                200,
                "application/x-ndjson; charset=utf-8",
                (json.dumps({"event": "error", "error": "prompt vazio"}, ensure_ascii=False) + "\n").encode("utf-8"),
            )
            return

        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            sent_terminal = False
            for raw_event in web_proxy.stream_infer_events(prompt, max_tokens, host=HOST, infer_port=INFER_PORT):
                event = _normalize_stream_event(raw_event)
                if event is None:
                    continue
                if event.get("event") in {"done", "error"}:
                    sent_terminal = True
                # Encaminha eventos do servidor de inferência quase em passthrough.
                line = json.dumps(event, ensure_ascii=False) + "\n"
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
            if not sent_terminal:
                line = json.dumps({"event": "error", "error": "stream encerrado sem resposta"}, ensure_ascii=False) + "\n"
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as exc:
            try:
                line = json.dumps({"event": "error", "error": str(exc)}, ensure_ascii=False) + "\n"
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Socket helper — reutilizado por handler e funções inline
# ---------------------------------------------------------------------------

def _query_infer_raw(payload: bytes) -> dict | None:
    return web_proxy.query_infer_raw(payload, host=HOST, infer_port=INFER_PORT)

# ---------------------------------------------------------------------------
# WebCLI
# ---------------------------------------------------------------------------

class WebCLI:

    def run(self, args: list[str]) -> None:
        if not args or args[0] == "start":
            no_browser = "--no-browser" in args
            self._start(open_browser=not no_browser)
        elif args[0] == "stop":
            self._stop()
        else:
            print("orn-web start [--no-browser]")
            print("orn-web stop")

    def _start(self, open_browser: bool = True) -> None:
        url = f"http://{HOST}:{WEB_PORT}"
        srv = HTTPServer((HOST, WEB_PORT), ORNHandler)
        srv.socket.settimeout(1.0)
        PID_FILE.write_text(str(os.getpid()))

        print(f"[WEB] Interface ORN em: {url}", flush=True)
        print(f"[WEB] PID={os.getpid()}  Ctrl+C para parar", flush=True)

        if open_browser:
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()

        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n[WEB] Encerrando...", flush=True)
        finally:
            srv.server_close()
            PID_FILE.unlink(missing_ok=True)

    def _stop(self) -> None:
        if not PID_FILE.exists():
            print("[WEB] Nenhum servidor ativo.")
            return
        pid = int(PID_FILE.read_text().strip())
        try:
            import signal
            os.kill(pid, signal.SIGTERM)
            PID_FILE.unlink(missing_ok=True)
            print(f"[WEB] Encerrado (PID {pid}).")
        except Exception as e:
            import traceback
            print(f"[WEB] Erro: {e}")
            print(f"\033[31m ■ Erro: {e}")
            traceback.print_tb(e.__traceback__)
