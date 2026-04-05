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
  - llama-cpp-python compilado com SSE4.1 via w64devkit (GCC)
  - GGML_NATIVE=ON, GGML_OPENMP=ON, GGML_LTO=ON, sem BLAS
  - n_threads=2, n_gpu_layers=0

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
# Flags de build do llama-cpp-python para N2808
# Centralizado aqui para ficar facil de ajustar futuramente.
# ---------------------------------------------------------------------------

LLAMA_CMAKE_ARGS = " ".join([
    "-DGGML_BLAS=OFF",
    "-DGGML_OPENMP=OFF",
    "-DGGML_LTO=OFF",
    "-DGGML_NATIVE=OFF",

    # 🔥 CRÍTICO (adicione isso)
    "-DGGML_AVX=OFF",
    "-DGGML_AVX2=OFF",
    "-DGGML_FMA=OFF",
    "-DGGML_F16C=OFF",

    "-DGGML_SSE42=OFF",
    "-DGGML_BMI2=OFF",

    "-DBUILD_SHARED_LIBS=OFF",
    '-G "MinGW Makefiles"',
    "-DCMAKE_C_COMPILER=gcc",
    "-DCMAKE_CXX_COMPILER=g++",
    "-DCMAKE_SHARED_LINKER_FLAGS=-fopenmp",
])

CFLAGS_OPT = "-O2 -msse4.1 -mfpmath=sse -fno-finite-math-only"
#CFLAGS_OPT = "-O2 -msse4.1 -mfpmath=sse -ffast-math"
#CFLAGS_OPT = "-O3 -march=silvermont -ffast-math -funroll-loops"

# ---------------------------------------------------------------------------
# Resultado de verificacao (OSL-7)
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    nome:    str
    ok:      bool
    detalhe: str
    fix_cmd: str = ""   # comando sugerido para corrigir, se aplicavel
    fix_fn:  object = None  # callable opcional para --fix (nao serializado)


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
            fix_cmd = "pip install llama-cpp-python  (com CMAKE_ARGS -- use --fix)",
            fix_fn  = install_llama_cpp,
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
            fix_cmd = "Recompilar via --fix (w64devkit + CMAKE_ARGS otimizado)",
            fix_fn  = install_llama_cpp,
        )


def check_model() -> CheckResult:
    model_path = Path(
        "models/sicdox/Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF"
        "/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
    )
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from engine.core.llm_bridge import BridgeConfig
        model_path = BridgeConfig().model_path
    except ImportError:
        pass

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
    """Avisa se install.py esta rodando fora do venv do ORN."""
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
    if major >= 3:
        return CheckResult(
            nome    = "numpy",
            ok      = True,
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
            fix_cmd = "Recompilar via --fix (w64devkit + CMAKE_ARGS otimizado)",
            fix_fn  = install_llama_cpp,
        )


# ---------------------------------------------------------------------------
# Instalacao otimizada do llama-cpp-python (N2808 / w64devkit)
# ---------------------------------------------------------------------------

def install_llama_cpp() -> bool:
    """
    Instala llama-cpp-python.

    Estrategia:
      1) tenta wheel binaria (rapido)
      2) se falhar, compila otimizado para Silvermont
    """

    print(INFO("  Tentando instalar wheel binaria..."))

    ret = subprocess.run([
        sys.executable,
        "-m",
        "pip",
        "install",
        "llama-cpp-python",
        "--prefer-binary",
    ])

    if ret.returncode == 0:
        print(OK("  Wheel instalada com sucesso."))
        return True

    print(WARN("  Wheel nao disponivel. Compilando localmente..."))

    W64_BIN = (
        r"C:\Users\olDox222\Documents\A20251122\DOSSIER\Altonomo\Projetos_E_Programas\Projeto OADE\doxoade\thirdparty\w64devkit\bin"
    )

    env = os.environ.copy()
    env["PATH"] = W64_BIN + os.pathsep + env.get("PATH", "")
    env["CMAKE_ARGS"] = LLAMA_CMAKE_ARGS
    env["FORCE_CMAKE"] = "1"
    env["CFLAGS"] = "-O2 -msse4.1 -mfpmath=sse -fno-finite-math-only -fopenmp" 
    env["CXXFLAGS"] = env["CFLAGS"]
    env["LDFLAGS"] = "-fopenmp"

    print(DIM(f"  CFLAGS: {CFLAGS_OPT}"))
    print(DIM(f"  CMAKE_ARGS: {LLAMA_CMAKE_ARGS}"))
    print(WARN("  Compilando llama.cpp otimizado..."))
    print()

    ret = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "llama-cpp-python",
            "--force-reinstall",
            "--no-cache-dir",
        ],
        env=env,
    )

    return ret.returncode == 0


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

def check_openmp():
    try:
        import llama_cpp
        info = getattr(llama_cpp, "__file__", "")
        print("  llama_cpp path:", info)
        return True
    except Exception:
        return False

def check_llama_backend():
    try:
# [DOX-UNUSED]         from llama_cpp import llama_cpp
        print("  backend carregado")
        return True
    except Exception:
        return False

def print_banner() -> None:
    print()
    print(SEP_M)
    print(HEAD("  ORN — Verificacao de Ambiente"))
    print(HEAD("  Celeron N2808 / Windows / Python 3.12"))
    print(SEP_M)
    print()
    _check_venv_active()


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
    """
    Tenta corrigir automaticamente problemas encontrados.

    Ordem de prioridade:
      1. fix_fn definido no CheckResult (ex: install_llama_cpp)
      2. fix_cmd comecando com 'pip install' (instalacao simples)
    """
    fixable = [r for r in results if not r.ok and (r.fix_fn or "pip install" in r.fix_cmd)]
    if not fixable:
        print(INFO("  Nada a corrigir automaticamente."))
        return

    for r in fixable:
        print()
        print(HEAD(f"  [{r.nome}]"))

        # Caso especial: fix_fn definido (ex: llama-cpp-python com CMAKE_ARGS)
        if r.fix_fn is not None:
            ok = r.fix_fn()
            if ok:
                print(OK(f"  [{r.nome}] instalado com sucesso."))
            else:
                print(ERRO(f"  [{r.nome}] falhou. Verifique o log acima."))
                print(WARN("  Dica: confirme que gcc (w64devkit) e cmake estao no PATH."))
            continue

        # Caso padrao: pip install simples
        cmd = r.fix_cmd.strip().splitlines()[0]
        if cmd.startswith("pip install"):
            print(WARN(f"  Executando: {cmd}"))
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
    print(HEAD("  Celeron N2808 / Windows / Python 3.12"))
    print(DIM("  Flags: --check | --verbose | --fix | --recompile"))
    
    if check or not fix:
        results = run_checks(verbose=verbose)
        print_summary(results)

    recompile = "--recompile" in args

    if recompile:
        print(HEAD("  [RECOMPILE] Recompilando llama-cpp-python com flags otimizadas...\n"))
        print(DIM(f"  CMAKE_ARGS: {LLAMA_CMAKE_ARGS}"))
        ok = install_llama_cpp()
        if ok:
            print(OK("  llama-cpp-python recompilado com sucesso."))
        else:
            print(ERRO("  Falhou. Verifique gcc/cmake no PATH."))
        print()


    if fix:
        print(HEAD("  [FIX] Tentando correcoes automaticas...\n"))
        results = run_checks(verbose=False)
        try_fix(results)
        print()
        print(HEAD("  [FIX] Re-verificando...\n"))
        results = run_checks(verbose=verbose)
        print_summary(results)

    criticos = [r for r in results if not r.ok and r.nome != "Modelo GGUF"]
    sys.exit(0 if not criticos else 1)


if __name__ == "__main__":
    main()