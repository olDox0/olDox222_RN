# -*- coding: utf-8 -*-
"""
ORN — UI / Colors (Afrodite)
Integração com doxcolors (ColorManager) — zero dependências externas.

OSL-18: Stdlib apenas (os, sys, ctypes). Sem colorama.
OSL-4:  Funções curtas — cada uma retorna string colorida sem efeito colateral.
OSL-3:  ColorManager é singleton; load_conf() chamado uma vez no import.
God: Afrodite — se ninguém gosta de usar, o sistema morreu.

Uso:
    from engine.ui.colors import c, ok, warn, erro, info, header, dimmed
    print(ok("Tudo certo!"))
    print(f"{c.BRIGHT_CYAN}texto{c.RESET}")
"""

import os
import sys
from functools import wraps
from pathlib import Path


# ---------------------------------------------------------------------------
# ColorManager — doxcolors (incubado internamente, zero deps)
# Adaptado de colors.py para integração com ORN engine.
# ---------------------------------------------------------------------------

class ColorManager:
    """Gerenciador de cores ANSI com lazy activation e conf externo.

    Singleton — uma única instância em toda a execução.
    Ativa ANSI no Windows via ctypes (sem colorama).
    Lê definições de colors.conf no mesmo diretório.
    """

    _instance    = None
    _initialized = False
    _cache: dict = {}
    _is_tty      = sys.stdout.isatty()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get(self, name: str) -> str:
        """Retorna código ANSI para *name*, ou '' se não-TTY / não encontrado."""
        if not sys.stdout.isatty():
            return ""
        self._activate_ansi()
        return self._cache.get(name.upper(), "")

    def __getattr__(self, name: str) -> str:
        """Acesso por atributo: c.BRIGHT_GREEN, c.RESET, etc."""
        return self.get(name)

    def paint(self, color_name: str):
        """Decorador: pinta toda a saída stdout de uma função."""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                code  = self.get(color_name)
                reset = self.get("RESET")
                if code:
                    sys.stdout.write(code)
                    sys.stdout.flush()
                try:
                    return func(*args, **kwargs)
                finally:
                    if code:
                        sys.stdout.write(reset)
                        sys.stdout.flush()
            return wrapper
        return decorator

    def _activate_ansi(self) -> None:
        """Ativa ANSI no Windows via ctypes (uma vez). OSL-3."""
        if not self._initialized:
            if self._is_tty and os.name == "nt":
                try:
                    import ctypes
                    handle = ctypes.windll.kernel32.GetStdHandle(-11)
                    ctypes.windll.kernel32.SetConsoleMode(handle, 7)
                except Exception:
                    pass
            self._initialized = True

    def load_conf(self, filename: str | None = None) -> None:
        """Carrega definições de colors.conf.

        OSL-5.2: Verifica existência antes de abrir.
        OSL-18:  Stdlib apenas.
        """
        if filename is None:
            filename = str(Path(__file__).parent / "colors.conf")
        if not os.path.exists(filename):
            return
        with open(filename, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" not in line:
                        continue
                    name, _, code = line.partition("=")
                    self._cache[name.strip().upper()] = f"\033[{code.strip()}m"

    def catalogar(self) -> None:
        """Imprime tabela visual das cores carregadas. Dev only."""
        self._activate_ansi()
        print("\n=== CATÁLOGO ORN COLORS ===")
        for i, (k, v) in enumerate(self._cache.items()):
            print(f"{v}{k:<20}\033[0m", end="  ")
            if (i + 1) % 5 == 0:
                print()
        print("\n===========================\n")


# ---------------------------------------------------------------------------
# Instâncias globais
# ---------------------------------------------------------------------------

c         = ColorManager()
doxcolors = c           # alias compatível com doxcolors externo
colors    = c           # alias compatível com: from engine.ui.colors import colors

# Carrega colors.conf automaticamente no import (OSL-3: uma vez)
c.load_conf()


# ---------------------------------------------------------------------------
# Helpers usados pelo display.py (OSL-4: cada um faz uma coisa)
# ---------------------------------------------------------------------------

def colorir(texto: str, nome_cor: str) -> str:
    """Envolve texto na cor e reseta. Retorna '' para vazio."""
    if not texto:
        return ""
    return f"{c.get(nome_cor)}{texto}{c.get('RESET')}"

def ok(texto: str)     -> str: return colorir(texto, "BRIGHT_GREEN")
def warn(texto: str)   -> str: return colorir(texto, "BRIGHT_YELLOW")
def erro(texto: str)   -> str: return colorir(texto, "BRIGHT_RED")
def info(texto: str)   -> str: return colorir(texto, "WHITE")
def header(texto: str) -> str: return colorir(texto, "BRIGHT_CYAN")
def dimmed(texto: str) -> str: return colorir(texto, "DARK_GRAY")


if __name__ == "__main__":
    c.catalogar()