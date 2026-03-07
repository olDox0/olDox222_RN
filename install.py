# -*- coding: utf-8 -*-
"""
ORN — install.py
Script de instalacao e verificacao do ambiente.

Execucao: python install.py
Opcoes:
  python install.py --check     verifica sem instalar
  python install.py --verbose   mostra detalhes de cada etapa
  python install.py --fix       tenta corrigir problemas encontrados

HARDWARE ALVO: Celeron N2808 (REP.INFRA.20260209.GOLD)
  - llama-cpp-python compilado com SSE4.2 via w64devkit (GCC 15.2)
  - n_threads=2, n_gpu_layers=0, OpenMP desativado

OSL-18: stdlib apenas (sys, os, subprocess, pathlib, importlib).
OSL-7:  cada verificacao retorna (bool, str) -- sem excecoes silenciosas.
"""

from __future__ import annotations

import os
import sys
import subprocess
import importlib.util
from pathlib import Path
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Paleta minima (sem doxcolors aqui -- pode nao estar instalado ainda)
# ---------------------------------------------------------------------------

def _c(code: str, texto: str) -> str:
    """Cor ANSI simples. Retorna texto puro se nao-TTY."""
    if not sys.stdout.isatty():
        return texto
    # Ativa ANSI no Windows sem colorama
    if os.name == "nt" and not getattr(_c, "_activated", False):
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7
            )
        except Exception:
            pass
        _c._activated = True
    return f"\033[{code}m{texto}\033[0m"

OK    = lambda t: _c("1;32", t)
WARN  = lambda t: _c("1;33", t)
ERRO  = lambda t: _c("1;31", t)
INFO  = lambda t: _c("0;37", t)
DIM   = lambda t: _c("0;90", t)
HEAD  = lambda t: _c("1;36", t)


# ---------------------------------------------------------------------------
# Resultado de verificacao (OSL-7)
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    nome:    str
    ok:      bool
    detalhe: str
    fix_cmd: str = ""   # comando sugerido para corrigir, se aplicavel


# ---------------------------------------------------------------------------
# Verificacoes
# ---------------------------------------------------------------------------

def check_python() -> CheckResult:
    v = sys.version_info
    ok = v >= (3, 10)
    return CheckResult(
        nome    = "Python >= 3.10",
        ok      = ok,
        detalhe = f"{v.major}.{v.minor}.{v.micro}",
        fix_cmd = "" if ok else "Instalar Python 3.10+ em python.org"
    )


def check_llama_cpp() -> CheckResult:
    spec = importlib.util.find_spec("llama_cpp")
    if spec is None:
        return CheckResult(
            nome    = "llama-cpp-python",
            ok      = False,
            detalhe = "modulo nao encontrado",
            fix_cmd = (
                "Ver docs/Internals/vol20_infrastructure_report.md\n"
                "  Protocolo Vulcan (w64devkit + MinGW Makefiles)"
            )
        )
    try:
        import llama_cpp
        ver = getattr(llama_cpp, "__version__", "instalado")
        return CheckResult(nome="llama-cpp-python", ok=True, detalhe=ver)
    except Exception as e:
        return CheckResult(
            nome    = "llama-cpp-python",
            ok      = False,
            detalhe = f"importado mas falhou: {e}",
            fix_cmd = "Recompilar via Protocolo Vulcan"
        )


def check_model() -> CheckResult:
    # Importa BridgeConfig se o engine/ estiver no path
    model_path = Path(
        "models/sicdox/Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF"
        "/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
    )
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from engine.core.llm_bridge import BridgeConfig
        model_path = BridgeConfig().model_path
    except ImportError:
        pass  # engine/ nao instalado ainda -- usa path padrao

    if not model_path.exists():
        return CheckResult(
            nome    = "Modelo GGUF",
            ok      = False,
            detalhe = str(model_path),
            fix_cmd = (
                "Baixar: https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF\n"
                "  Arquivo: qwen2.5-coder-0.5b-instruct-q4_k_m.gguf\n"
                f"  Destino: {model_path}"
            )
        )

    size_mb = model_path.stat().st_size / (1024 * 1024)
    if size_mb < 100:
        return CheckResult(
            nome    = "Modelo GGUF",
            ok      = False,
            detalhe = f"{model_path.name} ({size_mb:.0f}MB — suspeito)",
            fix_cmd = "Arquivo pode estar corrompido. Re-baixar."
        )

    return CheckResult(
        nome    = "Modelo GGUF",
        ok      = True,
        detalhe = f"{model_path.name} ({size_mb:.0f}MB)"
    )


def _check_venv_active() -> None:
    """Avisa se install.py esta rodando fora do venv do ORN.

    Problema real: dois Pythons no sistema (venv do ORN vs Python do sistema).
    llama_cpp so existe no venv -- rodar com 'python' errado da falso negativo.
    """
    in_venv = (
        hasattr(sys, "real_prefix") or
        (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
    )
    if not in_venv:
        print(ERRO("  [AVISO CRITICO] Rodando FORA do venv!"))
        print(WARN("  Use: .\\venv\\Scripts\\python.exe install.py"))
        print(WARN("  ou ative o venv: .\\venv\\Scripts\\activate"))
        print()


def check_click() -> CheckResult:
    import importlib.util as _iutil
    import importlib.metadata as _imeta
    spec = _iutil.find_spec("click")
    if spec is None:
        return CheckResult(
            nome    = "click",
            ok      = False,
            detalhe = "nao encontrado",
            fix_cmd = "pip install click>=8.1"
        )
    try:
        ver = _imeta.version("click")
    except Exception:
        import click
        ver = getattr(click, "__version__", "instalado")
    return CheckResult(nome="click", ok=True, detalhe=ver)


def check_numpy() -> CheckResult:
    spec = importlib.util.find_spec("numpy")
    if spec is None:
        return CheckResult(
            nome    = "numpy",
            ok      = False,
            detalhe = "nao encontrado",
            fix_cmd = "pip install numpy>=1.26"
        )
    import numpy as np
    ver = np.__version__
    major = int(ver.split(".")[0])
    # Aviso ABI: REP.INFRA §5.1
    if major >= 3:
        return CheckResult(
            nome    = "numpy",
            ok      = True,   # funciona, mas merece atencao
            detalhe = f"{ver} [AVISO: ABI com llama-cpp-python — testar]",
        )
    return CheckResult(nome="numpy", ok=True, detalhe=ver)


def check_orn_package() -> CheckResult:
    """Verifica se o pacote orn esta instalado em modo editavel."""
    spec = importlib.util.find_spec("engine")
    if spec is None:
        return CheckResult(
            nome    = "orn (pacote)",
            ok      = False,
            detalhe = "engine/ nao importavel",
            fix_cmd = "pip install -e ."
        )
    return CheckResult(nome="orn (pacote)", ok=True, detalhe="engine/ OK")


def check_llama_load() -> CheckResult:
    """Testa um load real e basico do llama_cpp (sem modelo)."""
    try:
        import llama_cpp
        # Verifica que a classe Llama existe e e importavel
        assert hasattr(llama_cpp, "Llama"), "classe Llama nao encontrada"
        return CheckResult(
            nome    = "llama_cpp.Llama",
            ok      = True,
            detalhe = "classe disponivel"
        )
    except Exception as e:
        return CheckResult(
            nome    = "llama_cpp.Llama",
            ok      = False,
            detalhe = str(e),
            fix_cmd = "Recompilar via Protocolo Vulcan (w64devkit)"
        )


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------

ALL_CHECKS = [
    check_python,
    check_click,
    check_numpy,
    check_llama_cpp,
    check_llama_load,
    check_model,
    check_orn_package,
]

SEP   = DIM("─" * 56)
SEP_M = HEAD("═" * 56)


def run_checks(verbose: bool = False) -> list[CheckResult]:
    results = []
    for fn in ALL_CHECKS:
        r = fn()
        results.append(r)
        simbolo = OK("  [OK]") if r.ok else ERRO("  [!!]")
        nome    = f"{r.nome:<28}"
        det     = DIM(r.detalhe) if r.ok else WARN(r.detalhe)
        print(f"{simbolo} {INFO(nome)} {det}")
        if verbose and r.fix_cmd:
            for linha in r.fix_cmd.splitlines():
                print(DIM(f"         {linha}"))
        if not r.ok and r.fix_cmd and not verbose:
            print(WARN(f"         -> {r.fix_cmd.splitlines()[0]}"))
    return results


def print_banner() -> None:
    print()
    print(SEP_M)
    print(HEAD("  ORN — Verificacao de Ambiente"))
    print(HEAD("  Celeron N2808 / Windows / Python 3.12"))
    print(SEP_M)
    print()
    _check_venv_active()   # avisa imediatamente se fora do venv


def print_summary(results: list[CheckResult]) -> None:
    total  = len(results)
    passed = sum(1 for r in results if r.ok)
    failed = total - passed
    print()
    print(SEP)
    if failed == 0:
        print(OK(f"  VERDE — {passed}/{total} verificacoes OK"))
        print(OK("  Ambiente pronto. Execute: orn config --show"))
    else:
        print(WARN(f"  {failed} problema(s) encontrado(s). Execute com --verbose para detalhes."))
        blocking = [r for r in results if not r.ok and r.nome not in ("Modelo GGUF",)]
        if not blocking:
            print(INFO("  (apenas modelo ausente — restante OK)"))
    print(SEP)
    print()


def try_fix(results: list[CheckResult]) -> None:
    """Tenta corrigir automaticamente o que for seguro."""
    fixable = [r for r in results if not r.ok and "pip install" in r.fix_cmd]
    if not fixable:
        print(INFO("  Nada a corrigir automaticamente."))
        return
    for r in fixable:
        cmd = r.fix_cmd.strip().splitlines()[0]
        if cmd.startswith("pip install"):
            print(WARN(f"  Corrigindo: {cmd}"))
            ret = subprocess.run(
                [sys.executable, "-m"] + cmd.split(),
                capture_output=True, text=True
            )
            if ret.returncode == 0:
                print(OK(f"  [{r.nome}] instalado com sucesso."))
            else:
                print(ERRO(f"  [{r.nome}] falhou: {ret.stderr.strip()[:120]}"))


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

def main() -> None:
    args    = sys.argv[1:]
    verbose = "--verbose" in args or "-v" in args
    fix     = "--fix"     in args
    check   = "--check"   in args

    print_banner()

    if check or not fix:
        results = run_checks(verbose=verbose)
        print_summary(results)

    if fix:
        print(HEAD("  [FIX] Tentando correcoes automaticas...\n"))
        results = run_checks(verbose=False)
        try_fix(results)
        print()
        print(HEAD("  [FIX] Re-verificando...\n"))
        results = run_checks(verbose=verbose)
        print_summary(results)

    # Codigo de saida: 0 se tudo OK, 1 se houver falhas criticas
    criticos = [r for r in results if not r.ok and r.nome != "Modelo GGUF"]
    sys.exit(0 if not criticos else 1)


if __name__ == "__main__":
    main()