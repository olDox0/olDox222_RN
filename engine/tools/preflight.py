# -*- coding: utf-8 -*-
"""Preflight — Verificação completa do ambiente ORN antes de rodar.

Uso: python -m engine.tools.preflight
"""
import os
import sys
import socket
from pathlib import Path

class Preflight:
    def __init__(self):
        self.ok = 0
        self.warn = 0
        self.fail = 0
        self.results = []

    def check(self, name: str, condition: bool, msg_ok: str, msg_fail: str, is_warning: bool = False):
        if condition:
            self.ok += 1
            self.results.append(("OK", name, msg_ok))
        else:
            if is_warning:
                self.warn += 1
                self.results.append(("WARN", name, msg_fail))
            else:
                self.fail += 1
                self.results.append(("FAIL", name, msg_fail))

    def print_report(self):
        print("\n" + "="*60)
        print(" ⚕️  ORN PREFLIGHT — VERIFICAÇÃO DE AMBIENTE")
        print("="*60)
        
        for status, name, msg in self.results:
            if status == "OK":
                print(f"  \033[1;32m[OK]\033[0m   {name:<22} {msg}")
            elif status == "WARN":
                print(f"  \033[1;33m[WARN]\033[0m {name:<22} {msg}")
            else:
                print(f"  \033[1;31m[FAIL]\033[0m {name:<22} {msg}")
                
        print("-" * 60)
        print(f"  Totais: {self.ok} OK | {self.warn} WARN | {self.fail} FAIL")
        print("="*60 + "\n")
        return self.fail == 0


def _is_port_open(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False


def run_preflight() -> bool:
    p = Preflight()

    # 1. Python
    py_ok = sys.version_info >= (3, 10)
    p.check("Python >= 3.10", py_ok, f"v{sys.version.split()[0]}", f"v{sys.version.split()[0]} (Muito antigo)")

    # 2. Modelo GGUF
    try:
        from engine.core.llm_bridge import BridgeConfig
        cfg = BridgeConfig()
        model_path = cfg.model_path
        model_exists = model_path.exists()
        if model_exists:
            size_mb = model_path.stat().st_size / (1024 * 1024)
            p.check("Modelo GGUF", True, f"{model_path.name} ({size_mb:.0f} MB)", "")
        else:
            p.check("Modelo GGUF", False, "", f"Ausente em {model_path}")
    except Exception as e:
        p.check("Modelo GGUF", False, "", f"Erro ao carregar BridgeConfig: {e}")

    # 3. Backend Nativo (orn.dll)
    dll_path = Path(__file__).parent.parent.parent / "native" / "orn.dll"
    if dll_path.exists():
        size_kb = dll_path.stat().st_size / 1024
        p.check("Backend Nativo (orn.dll)", True, f"Presente ({size_kb:.0f} KB)", "")
    else:
        p.check("Backend Nativo (orn.dll)", False, "", "Ausente. Usará fallback Python.", is_warning=True)

    # 4. Frontend
    html_path = Path(__file__).parent.parent / "web" / "static" / "index.html"
    p.check("Frontend (index.html)", html_path.exists(), str(html_path.name), "Ausente")

    # 5. Portas
    server_online = _is_port_open(8371)
    p.check("Porta 8371 (orn-server)", server_online, "Aberta (Servidor online)", "Fechada (Fallback direto será usado)", is_warning=True)
    
    web_online = _is_port_open(8372)
    p.check("Porta 8372 (orn web)", web_online, "Aberta", "Fechada", is_warning=True)

    return p.print_report()


if __name__ == "__main__":
    success = run_preflight()
    sys.exit(0 if success else 1)
