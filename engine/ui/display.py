# -*- coding: utf-8 -*-
"""
ORN — UI / Display (Apolo)
Todas as funções de output no terminal passam por aqui.

OSL-4:  Cada método faz exatamente uma coisa.
OSL-17: Nenhum módulo de lógica imprime diretamente — tudo passa pelo Display.
OSL-18: Usa engine.ui.colors (doxcolors) — zero deps externas.
God: Apolo — clareza, ordem e legibilidade no terminal.
"""

import sys

from engine.ui.colors import c, ok, warn, erro, info, header, dimmed

# ---------------------------------------------------------------------------
# Constantes visuais
# ---------------------------------------------------------------------------

_SEP_MAJOR = "═" * 60
_SEP_MINOR = "─" * 60
_BANNER = r"""
        ████████████  ████████████  ███     ████
      ████████████  ████████████  █████   ████
    ████████████  ████ ████     ████   █████
  ████████████  ████     ████ ████     ███
   o l D o x 2 2 2    R e d e    N e u r a l
    
"""


class Display:
    """Namespace estático para todos os outputs do ORN.

    OSL-4: Métodos curtos, cada um com uma responsabilidade.
    OSL-17: Única fonte de saída — módulos de lógica nunca printam diretamente.
    """

    # ------------------------------------------------------------------
    # Identidade
    # ------------------------------------------------------------------

    @staticmethod
    def banner() -> None:
        """Exibe o banner ASCII do ORN."""
        print(header(_BANNER))
        print(dimmed("  AI CLI para Código — Qwen2.5-Coder local"))
        print(dimmed(f"  {_SEP_MINOR}"))
        print()

    # ------------------------------------------------------------------
    # Seções e separadores
    # ------------------------------------------------------------------

    @staticmethod
    def section(comando: str, alvo: str) -> None:
        """Cabeçalho de seção para um comando."""
        alvo_str = f" → {alvo}" if alvo else ""
        print(f"\n{header(_SEP_MAJOR)}")
        print(header(f"  [{comando}]{alvo_str}"))
        print(header(_SEP_MAJOR))

    @staticmethod
    def separator() -> None:
        """Linha separadora menor."""
        print(dimmed(_SEP_MINOR))

    # ------------------------------------------------------------------
    # Mensagens de status
    # ------------------------------------------------------------------

    @staticmethod
    def success(msg: str) -> None:
        print(ok(f"  [OK] {msg}"))

    @staticmethod
    def warn(msg: str) -> None:
        print(warn(f"  [!]  {msg}"))

    @staticmethod
    def error(msg: str, fatal: bool = False) -> None:
        """OSL-7: fatal=True encerra o processo — usar com moderação."""
        print(erro(f"  [ERRO] {msg}"), file=sys.stderr)
        if fatal:
            sys.exit(1)

    @staticmethod
    def info(msg: str) -> None:
        print(info(f"  {msg}"))

    @staticmethod
    def thinking(prompt: str) -> None:
        """Indica que o modelo está processando."""
        print(warn("\n  [ORN] Processando: ") + info(f'"{prompt}"'))
        print(dimmed("  Aguarde..."))

    # ------------------------------------------------------------------
    # Desenvolvimento / stubs
    # ------------------------------------------------------------------

    @staticmethod
    def not_implemented(comando: str) -> None:
        """Placeholder para comandos ainda não implementados."""
        print(warn(f"\n  [TODO] '{comando}' ainda não implementado."))
        print(dimmed("  Consulte o roadmap em docs/ORN_planejamento.md"))

    # ------------------------------------------------------------------
    # Dados estruturados
    # ------------------------------------------------------------------

    @staticmethod
    def kv(chave: str, valor: str) -> None:
        """Par chave → valor alinhado."""
        print(f"  {dimmed(chave.ljust(20))} {info(str(valor))}")

    @staticmethod
    def lista(titulo: str, itens: list[str]) -> None:
        """Lista com título. OSL-5.2: valida itens."""
        if not itens:
            return
        print(header(f"\n  {titulo}"))
        for item in itens:
            print(info(f"    • {item}"))

    @staticmethod
    def code_block(codigo: str, lang: str = "") -> None:
        """Bloco de código destacado no terminal."""
        lang_label = f" [{lang.upper()}]" if lang else ""
        pad = 40 - len(lang)
        print(dimmed(f"\n  ┌─ Código{lang_label} {'─' * max(pad, 4)}"))
        for linha in codigo.splitlines():
            print(f"  │ {c.get('CYAN')}{linha}{c.get('RESET')}")
        print(dimmed("  └" + "─" * 46))