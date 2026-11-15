# -*- coding: utf-8 -*-
"""WebServer — orquestra HTTP + InferenceFacade (auto/embedded/proxy)."""
from __future__ import annotations

import functools
import os
import sys
import logging
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

from engine.api import InferenceFacade
from engine.web.handler import ORNHandler
from engine.web.stream_cache import StreamCache

HOST = "127.0.0.1"
WEB_PORT = 8372
PID_FILE = Path("web_server.pid")


class WebServer:
    def __init__(
        self, *, prefer: str = "auto",
        port: int = WEB_PORT, open_browser: bool = True,
    ) -> None:
        self.port = int(port)
        self.prefer = prefer
        self.open_browser = open_browser
        self.facade = InferenceFacade(prefer=prefer)
        self.cache = StreamCache()
        self._srv: ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}"

    def start(self) -> None:
        # Configura o log para mandar pro arquivo E pro terminal
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            handlers=[
                logging.FileHandler('web_server.log', mode='a', encoding='utf-8'),
                logging.StreamHandler(sys.stdout)  # <--- Mostra no terminal
            ]
        )
        logger = logging.getLogger("orn.web.server")
        logger.info("--- Iniciando Servidor Web ---")
        
        handler_cls = functools.partial(
            ORNHandler, facade=self.facade, cache=self.cache,
        )
        self._srv = ThreadingHTTPServer((HOST, self.port), handler_cls)
        self._srv.socket.settimeout(1.0)
        PID_FILE.write_text(str(os.getpid()))
        print(f"[WEB] Interface ORN em: {self.url}", flush=True)
        print(f"[WEB] Modo: {self.facade.mode}  PID={os.getpid()}", flush=True)
        
        if self.open_browser:
            threading.Timer(0.8, lambda: webbrowser.open(self.url)).start()
        try:
            self._srv.serve_forever()
        except KeyboardInterrupt:
            print("\n[WEB] Encerrando...", flush=True)
        finally:
            self.stop()

    def stop(self) -> None:
        if self._srv is not None:
            try:
                self._srv.server_close()
            except Exception:
                pass
            self._srv = None
        try:
            self.facade.shutdown()
        except Exception:
            pass
        PID_FILE.unlink(missing_ok=True)

    def _start_bg(self, args: list[str]) -> None:
        import subprocess
        import sys
        child_args = [a for a in args if a != "--bg"]
        log_file = open("web_server.log", "w", encoding="utf-8")
        subprocess.Popen(
            [sys.executable, "-m", "engine.web"] + child_args,
            stdout=log_file,
            stderr=log_file,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        log_file.close()
        print("[WEB] Iniciado em background. Log: web_server.log")


def _bind(*args, facade: InferenceFacade, cache: StreamCache, **kwargs):
    """Injeta dependências no handler sem herdar (evita global)."""
    handler = ORNHandler(*args, **kwargs)
    handler.facade = facade
    handler.cache = cache
    return handler
