# -*- coding: utf-8 -*-
"""WebCLI — ponto de entrada de `orn web` com modos de inferência."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from engine.web.server import WebServer, PID_FILE


_HELP = """\
orn web start [opções]
  --auto        (default) usa orn-server se online, senão embarcado
  --embedded    força bridge em processo (servidor acoplado, 1 PID)
  --proxy       força uso de orn-server externo (porta 8371)
  --port N      porta HTTP (default 8372)
  --no-browser  não abre navegador
orn web stop    encerra processo via PID file
"""


class WebCLI:
    def run(self, args: list[str]) -> None:
        if not args or args[0] in ("-h", "--help", "help"):
            print(_HELP)
            return
        if args[0] == "stop":
            self._stop()
            return
        if args[0] != "start":
            print(f"[WEB] subcomando desconhecido: {args[0]}")
            print(_HELP)
            raise SystemExit(2)
        
        if "--bg" in args:
            self._start_bg(args)
            return

        prefer = "auto"
        if "--embedded" in args:
            prefer = "direct"
        elif "--proxy" in args:
            prefer = "server"
        port = self._int_flag(args, "--port", 8372)
        open_browser = "--no-browser" not in args
        WebServer(
            prefer=prefer, port=port, open_browser=open_browser,
        ).start()

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

    def _stop(self) -> None:
        if not PID_FILE.exists():
            print("[WEB] Nenhum servidor ativo.")
            return
        try:
            pid = int(PID_FILE.read_text().strip())
        except (ValueError, OSError) as exc:
            print(f"[WEB] PID file inválido: {exc}")
            return
        try:
            import signal
            os.kill(pid, signal.SIGTERM)
            PID_FILE.unlink(missing_ok=True)
            print(f"[WEB] Encerrado (PID {pid}).")
        except ProcessLookupError:
            PID_FILE.unlink(missing_ok=True)
            print(f"[WEB] PID {pid} já não existe — limpando PID file.")
        except Exception as exc:
            print(f"[WEB] Erro ao parar: {exc}")

    @staticmethod
    def _int_flag(args: list[str], flag: str, default: int) -> int:
        if flag not in args:
            return default
        i = args.index(flag)
        if i + 1 >= len(args):
            return default
        try:
            return int(args[i + 1])
        except ValueError:
            return default
