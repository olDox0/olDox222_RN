# -*- coding: utf-8 -*-
"""ORNHandler — request handler HTTP fino. Só orquestra facade + cache + UI."""
from __future__ import annotations

import time
import json
import logging
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from engine.api import StreamEvent, to_ndjson
from engine.web import auto_search
from engine.web.stream_cache import StreamCache
from engine.web.web_page import HTML

# ADICIONE ESTAS DUAS LINHAS:
logger = logging.getLogger("orn.web")

def _suggest_max_tokens(prompt: str) -> int:
    #return 8192
    #return 2048 
    return 1024


class ORNHandler(BaseHTTPRequestHandler):
    # tipos declarados para o type checker; valores vêm do __init__
    facade: object
    cache:  object

    def __init__(self, *args, facade, cache, **kwargs):
        # atribuir ANTES do super() — o super() já dispara do_GET()
        self.facade = facade
        self.cache  = cache
        super().__init__(*args, **kwargs)

    def log_message(self, fmt, *args):
        pass

    # ── GET ─────────────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", HTML.encode("utf-8"))
            return
        if parsed.path == "/favicon.ico":
            self._send(204, "", b"")
            return
        if parsed.path == "/status":
            self._send_json(self.facade.status())
            return
        if parsed.path == "/stream_cache":
            q = parse_qs(parsed.query or "")
            rid = str((q.get("id") or [""])[0]).strip()
            if not rid:
                self._send_json({"error": "id ausente"}, status=400)
                return
            item = self.cache.get(rid)
            if item is None:
                self._send_json({"error": "cache não encontrado"}, status=404)
                return
            self._send_json(item)
            return
        self._send(404, "", b"")

    # ── POST ────────────────────────────────────────────
    def do_POST(self):
        if self.path == "/ask_stream":
            self._handle_ask_stream()
            return
        if self.path == "/ask":
            self._handle_ask_sync()
            return
        self._send(404, "", b"")

    # ── /ask (síncrono) ─────────────────────────────────
    def _handle_ask_sync(self):
        req = self._read_json()
        prompt = str(req.get("prompt", "")).strip()
        max_tokens = self._max_tokens_from(req, prompt)
        if not prompt:
            self._send_json(
                {"output": "", "elapsed_s": 0, "error": "prompt vazio",
                 "source": None, "source_url": None})
            return
        ctx_block, source, source_url = self._resolve_auto_search(prompt)
        full = ctx_block + "\n[TASK]\n" + prompt if ctx_block else prompt
        try:
            output = self.facade.ask(full, max_tokens=max_tokens)
            output = self._apply_code_hook(output, prompt, max_tokens)
            err = None
        except Exception as exc:
            output = ""
            err = str(exc)
        self._send_json({
            "output":     output,
            "elapsed_s":  0,
            "error":      err,
            "source":     source or None,
            "source_url": source_url or None,
        })

    # ── /ask_stream (NDJSON) ────────────────────────────
    def _handle_ask_stream(self):
        req = self._read_json()
        prompt = str(req.get("prompt", "")).strip()
        max_tokens = self._max_tokens_from(req, prompt)

        logger.info(f"[STREAM] INÍCIO | prompt_len={len(prompt)} | max_tokens={max_tokens}")

        if not prompt:
            logger.warning("[STREAM] Prompt vazio rejeitado.")
            body = to_ndjson(StreamEvent(kind="error", error="prompt vazio"))
            self._send(200, "application/x-ndjson; charset=utf-8", body.encode())
            return

        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

            rid = self.cache.start(prompt, max_tokens)
            self._write_event(StreamEvent(kind="start", request_id=rid, max_tokens=max_tokens))

            acc: list[str] = []
            llm_done_ev: StreamEvent | None = None
            chunk_count = 0

            # ── 1. Stream do LLM ──
            for ev in self.facade.ask_stream(prompt, max_tokens=max_tokens):
                ev.request_id = rid
                if ev.kind == "chunk":
                    acc.append(ev.delta)
                    ev.chunk_idx = self.cache.append(rid, ev.delta)
                    chunk_count += 1
                    self._write_event(ev)
                elif ev.kind == "done":
                    llm_done_ev = ev
                    self._write_event(StreamEvent(
                        kind="llm_done",
                        request_id=rid,
                        output=ev.output,
                        elapsed_s=ev.elapsed_s,
                    ))
                elif ev.kind == "error":
                    logger.error(f"[STREAM] error | {ev.error}")
                    self.cache.finish(rid, "".join(acc), 0, error=ev.error)
                    self._write_event(ev)
                    return

            full_text = llm_done_ev.output if (llm_done_ev and llm_done_ev.output) else "".join(acc)

            # ── 2. Hook de validação (se sandbox online) ──
            validated_text = full_text
            changed = False

            if full_text and self._sandbox_status().get("online"):
                logger.info(f"[STREAM] validando via hook ({len(full_text)} chars)")
                try:
                    import re as _re
                    from engine.thinking.code_hook import apply_code_hook
                    from engine.core.logic_filter import SiCDoxValidator

                    facade = self.facade

                    class _FB:
                        def ask(self, p, max_tokens=256, **kw):
                            try:
                                return facade.ask(p, max_tokens=max_tokens)
                            except Exception:
                                return ""

                    hook_out = apply_code_hook(
                        output=full_text,
                        task=prompt,
                        bridge=_FB(),
                        validator=SiCDoxValidator(),
                        max_retries=1,
                        run_isolated=True,
                    )

                    if hook_out and hook_out != full_text:
                        # Extrai o código de cada versão para decidir "mudou de verdade"
                        def _extract_code(text: str) -> str:
                            m = _re.search(r"```(?:c|python)?\s*\n(.*?)```", text or "", _re.DOTALL)
                            if m:
                                return m.group(1).strip()
                            m = _re.search(r"\[code-begin\](.*?)\[code-end\]", text or "", _re.DOTALL)
                            if m:
                                return m.group(1).strip()
                            return ""

                        orig_code = _extract_code(full_text)
                        new_code = _extract_code(hook_out)
                        changed = bool(orig_code) and bool(new_code) and (orig_code != new_code)

                        validated_text = hook_out
                        logger.info(
                            f"[STREAM] hook retornou ({len(hook_out)} chars), "
                            f"changed={changed} (orig={len(orig_code)}c new={len(new_code)}c)"
                        )
                except Exception as exc:
                    logger.warning(f"[STREAM] hook falhou: {exc}")

            # ── 3. Emite validated ──
            self._write_event(StreamEvent(
                kind="validated",
                request_id=rid,
                output=validated_text,
                changed=changed,
            ))

            # ── 4. done final ──
            elapsed = llm_done_ev.elapsed_s if llm_done_ev else 0.0
            self._write_event(StreamEvent(
                kind="done",
                request_id=rid,
                output=validated_text,
                elapsed_s=elapsed,
            ))
            self.cache.finish(rid, validated_text, elapsed)

        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            logger.warning("[STREAM] Cliente desconectou.")
        except Exception as exc:
            logger.exception("[STREAM] Falha fatal")
            try:
                self._write_event(StreamEvent(kind="error", error=str(exc)))
            except Exception:
                pass

    # ── helpers ─────────────────────────────────────────
    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except Exception:
            return {}

    def _max_tokens_from(self, req: dict, prompt: str) -> int:
        if "max_tokens" in req:
            try:
                return max(1, min(int(req["max_tokens"]), 2048))
            except (TypeError, ValueError):
                pass
        return _suggest_max_tokens(prompt)

    def _resolve_auto_search(self, prompt: str):
        try:
            term = auto_search.decide_search(prompt, self.facade)
            if not term:
                return "", "", ""
            return auto_search.run_crawler(term)
        except Exception:
            return "", "", ""

    def _apply_code_hook(self, output: str, task: str, max_tokens: int) -> str:
        try:
            from engine.thinking.code_hook import apply_code_hook
        except Exception:
            return output

        facade = self.facade

        class _FacadeBridge:
            def ask(self, p, max_tokens=256, **kw):
                try:
                    return facade.ask(p, max_tokens=max_tokens)
                except Exception:
                    return ""

        class _DummyValidator:
            def validar_output(self, text, lang=None):
                return True, ""

        try:
            return apply_code_hook(
                output=output, task=task,
                bridge=_FacadeBridge(), validator=_DummyValidator(),
                max_retries=1, run_isolated=True,
            )
        except Exception:
            return output

    def _write_event(self, ev: StreamEvent) -> None:
        self.wfile.write(to_ndjson(ev).encode("utf-8"))
        self.wfile.flush()

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

    def _send_json(self, payload: dict, *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", body)

    def _sandbox_status(self) -> dict:
        """Retorna status do sandbox (cached 30s)."""
        now = time.time()
        cache = getattr(self, "_sandbox_cache", None)
        if cache and now - cache["ts"] < 30:
            return cache["status"]
        try:
            from engine.tools.qemu_daemon import QemuDaemon
            st = QemuDaemon().status()
            status = {"online": st.online, "port": st.port}
        except Exception:
            status = {"online": False, "port": None}
        self._sandbox_cache = {"ts": now, "status": status}
        return status
