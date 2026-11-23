# -*- coding: utf-8 -*-
# engine\api\facade.py
"""InferenceFacade — interface única de inferência, transport-agnostic.

Modos:
  "server" : TCP para orn-server (porta 8371) — processo separado
  "direct" : bridge em processo (sem TCP) — "servidor acoplado"
  "auto"   : tenta server, cai para direct se offline (default)

Nenhuma dependência de HTTP, Click, ou UI.
"""
from __future__ import annotations

import sys
import logging
import threading
import time
from typing import Iterator, Literal

from engine.api.events import StreamEvent

logger = logging.getLogger("orn.api")

Prefer = Literal["auto", "server", "direct"]
Mode   = Literal["server", "direct", "offline"]


class InferenceFacade:
    def __init__(self, prefer: Prefer = "auto") -> None:
        if prefer not in ("auto", "server", "direct"):
            raise ValueError(f"prefer inválido: {prefer!r}")
        self._prefer: Prefer = prefer
        self._mode:   Mode   = "offline"
        self._bridge         = None
        self._probed         = False
        self._infer_lock     = threading.Lock()

    # ── API pública ──────────────────────────────────────
    @property
    def mode(self) -> Mode:
        if not self._probed:
            self._resolve()
        return self._mode

    def ask(self, prompt: str, max_tokens: int = 128) -> str:
        if not prompt:
            raise ValueError("prompt vazio")
        mode = self._resolve()
        if mode == "server":
            out = self._server_ask(prompt, max_tokens)
            if out is not None:
                return out
            self._mode = self._fallback_direct()
            if self._mode == "direct":
                return self._direct_ask(prompt, max_tokens)
            raise RuntimeError("inferência indisponível")
        if mode == "direct":
            return self._direct_ask(prompt, max_tokens)
        raise RuntimeError("inferência indisponível (offline)")

    def ask_stream(self, prompt: str, max_tokens: int = 128) -> Iterator[StreamEvent]:
        if not prompt:
            raise ValueError("prompt vazio")
        mode = self._resolve()
        if mode == "server":
            yield from self._server_stream(prompt, max_tokens)
            return
        if mode == "direct":
            yield from self._direct_stream(prompt, max_tokens)
            return
        yield StreamEvent(kind="error", error="inferência offline")

    def status(self) -> dict:
        mode = self._resolve()
        info: dict = {"facade_mode": mode, "prefer": self._prefer}
        if mode == "server":
            try:
                from engine.tools.server_client import status as _st
                s = _st()
                if s:
                    info.update({
                        "server_status":   s.get("status", "?"),
                        "server_requests": s.get("requests", 0),
                        "server_uptime_s": s.get("uptime_s", 0),
                        "server_port":     s.get("port"),
                        "ai_perf":         s.get("ai_perf", {}),
                    })
            except Exception as exc:
                info["server_error"] = str(exc)
        return info

    def shutdown(self) -> None:
        if self._bridge is not None:
            try:
                self._bridge.shutdown()
            except Exception:
                pass
            self._bridge = None
        self._probed = False
        self._mode   = "offline"

    # ── internos ─────────────────────────────────────────
    def _resolve(self) -> Mode:
        if self._probed:
            return self._mode
        self._probed = True
        if self._prefer == "direct":
            self._mode = "direct"
        elif self._prefer == "server":
            self._mode = "server" if self._server_online() else "offline"
        else:  # auto
            self._mode = "server" if self._server_online() else "direct"
        return self._mode

    def _server_online(self) -> bool:
        try:
            from engine.tools.server_client import is_server_online
            return bool(is_server_online())
        except Exception:
            return False

    def _fallback_direct(self) -> Mode:
        try:
            self._ensure_bridge()
            return "direct"
        except Exception:
            return "offline"

    def _server_ask(self, prompt: str, max_tokens: int) -> str | None:
        try:
            from engine.tools.server_client import query as _q
            resp = _q(prompt, max_tokens=max_tokens)
            if resp is None or resp.get("error"):
                return None
            return str(resp.get("output", ""))
        except Exception:
            return None

    def _direct_ask(self, prompt: str, max_tokens: int) -> str:
        bridge = self._ensure_bridge()
        with self._infer_lock:
            return bridge.ask(prompt, max_tokens=max_tokens)

    def _server_stream(self, prompt: str, max_tokens: int):
        try:
            from engine.web.web_proxy      import stream_infer_events
            from engine.tools.server_client import HOST as _H, PORT as _P
        except ImportError:
            yield StreamEvent(kind="error", error="stream proxy indisponível")
            return
        for raw in stream_infer_events(prompt, max_tokens, host=_H, infer_port=_P):
            ev = StreamEvent.from_raw(raw)
            if ev is not None:
                yield ev

    def _direct_stream(self, prompt: str, max_tokens: int):
        logger.info(f"[FACADE] Iniciando stream (direct) | prompt_len={len(prompt)} | max_tokens={max_tokens}")
        bridge = self._ensure_bridge()
        stream_fn = getattr(bridge, "stream_ask", None)
        
        if stream_fn is None:
            logger.warning("[FACADE] Bridge não tem stream_ask, usando fallback síncrono.")
            try:
                out = bridge.ask(prompt, max_tokens=max_tokens)
            except Exception as exc:
                yield StreamEvent(kind="error", error=str(exc))
                return
            yield StreamEvent(kind="chunk", delta=out, chunk_idx=0)
            yield StreamEvent(kind="done",  output=out, elapsed_s=0.0)
            return

        t0 = time.monotonic()
        self._infer_lock.acquire()
        try:
            idx = 0
            acc: list[str] = []
            try:
                for piece in stream_fn(prompt, max_tokens=max_tokens):
                    if not piece:
                        continue
                    acc.append(piece)
                    yield StreamEvent(kind="chunk", delta=piece, chunk_idx=idx)
                    idx += 1
            except Exception as exc:
                logger.error(f"[FACADE] Erro no bridge: {exc}")
                yield StreamEvent(kind="error", error=str(exc))
                return
                
            elapsed = round(time.monotonic() - t0, 2)
            logger.info(f"[FACADE] Stream finalizado | total_chunks={idx} | tempo={elapsed}s")
            yield StreamEvent(
                kind="done", 
                output="".join(acc), 
                elapsed_s=elapsed
            )
        finally:
            self._infer_lock.release()

    def _ensure_bridge(self):
        if self._bridge is None:
            from engine.core.llm_bridge import SiCDoxBridge
            self._bridge = SiCDoxBridge()
        return self._bridge
