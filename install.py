# -*- coding: utf-8 -*-
# install.py
"""ORN — install.py (Automated Edition)"""
from __future__ import annotations
import os, sys, subprocess, importlib.util
from pathlib import Path
from dataclasses import dataclass

def _c(code: str, texto: str) -> str:
    if not sys.stdout.isatty(): return texto
    if os.name == "nt" and not getattr(_c, "_activated", False):
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception: pass
        _c._activated = True
    return f"\033[{code}m{texto}\033[0m"

OK = lambda t: _c("1;32", t)
WARN = lambda t: _c("1;33", t)
ERRO = lambda t: _c("1;31", t)
INFO = lambda t: _c("0;37", t)
DIM = lambda t: _c("0;90", t)

@dataclass
class CheckResult:
    nome: str
    ok: bool
    detalhe: str
    fix_cmd: str = ""

def check_python() -> CheckResult:
    v = sys.version_info
    return CheckResult(nome="Python >= 3.10", ok=v >= (3, 10), detalhe=f"{v.major}.{v.minor}.{v.micro}")

def check_click() -> CheckResult:
    spec = importlib.util.find_spec("click")
    if spec is None: return CheckResult(nome="click", ok=False, detalhe="nao encontrado", fix_cmd="pip install click>=8.1")
    import click
    return CheckResult(nome="click", ok=True, detalhe=getattr(click, "__version__", "instalado"))

def check_numpy() -> CheckResult:
    spec = importlib.util.find_spec("numpy")
    if spec is None: return CheckResult(nome="numpy", ok=False, detalhe="nao encontrado", fix_cmd="pip install numpy>=1.26")
    import numpy as np
    return CheckResult(nome="numpy", ok=True, detalhe=np.__version__)

def check_orn_package() -> CheckResult:
    spec = importlib.util.find_spec("engine")
    if spec is None: return CheckResult(nome="orn (pacote)", ok=False, detalhe="engine/ nao importavel", fix_cmd="pip install -e .")
    return CheckResult(nome="orn (pacote)", ok=True, detalhe="engine/ OK")

def check_model() -> CheckResult:
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from engine.core.llm_bridge import BridgeConfig
        model_path = BridgeConfig().model_path
    except ImportError:
        model_path = Path("models/sicdox/qwen2.5-coder-0.5b-instruct-q2_k.gguf")
    if not model_path.exists():
        return CheckResult(nome="Modelo GGUF", ok=False, detalhe=str(model_path), fix_cmd="Baixar modelo para models/sicdox/")
    size_mb = model_path.stat().st_size / (1024 * 1024)
    if size_mb < 100:
        return CheckResult(nome="Modelo GGUF", ok=False, detalhe=f"{model_path.name} ({size_mb:.0f}MB — suspeito)", fix_cmd="Arquivo corrompido.")
    return CheckResult(nome="Modelo GGUF", ok=True, detalhe=f"{model_path.name} ({size_mb:.0f}MB)")

def check_llama_cpp() -> CheckResult:
    spec = importlib.util.find_spec("llama_cpp")
    if spec is None: return CheckResult(nome="llama-cpp-python", ok=False, detalhe="modulo nao encontrado", fix_cmd="Executar: python install.py --auto")
    try:
        import llama_cpp
        return CheckResult(nome="llama-cpp-python", ok=True, detalhe=getattr(llama_cpp, "__version__", "instalado"))
    except Exception as e:
        return CheckResult(nome="llama-cpp-python", ok=False, detalhe=f"importado mas falhou: {e}", fix_cmd="Executar: python install.py --auto")

def check_llama_load() -> CheckResult:
    try:
        import llama_cpp
        assert hasattr(llama_cpp, "Llama"), "classe Llama nao encontrada"
        return CheckResult(nome="llama_cpp.Llama", ok=True, detalhe="classe disponivel")
    except Exception as e:
        return CheckResult(nome="llama_cpp.Llama", ok=False, detalhe=str(e), fix_cmd="Executar: python install.py --auto")

def find_winlibs() -> Path | None:
    candidates = [Path(r"C:\winlibs\mingw64\bin"), Path(__file__).parent / "thirdparty" / "winlibs" / "mingw64" / "bin"]
    for p in candidates:
        if (p / "gcc.exe").exists(): return p.parent
    return None

def ensure_winlibs() -> Path:
    path = find_winlibs()
    if path:
        print(f"  {OK('[OK]')} winlibs encontrado em: {path}")
        return path
    print(f"  {WARN('[!]')} winlibs nao encontrado. Baixando automaticamente...")
    install_script = Path(__file__).parent / "install_winlibs.py"
    if install_script.exists():
        subprocess.run([sys.executable, str(install_script)], check=True)
    else:
        print(f"  {ERRO('[ERRO]')} install_winlibs.py nao encontrado.")
        sys.exit(1)
    path = find_winlibs()
    if not path:
        print(f"  {ERRO('[ERRO]')} Falha ao instalar winlibs.")
        sys.exit(1)
    return path

def install_llama_cpp_auto(winlibs_path: Path) -> bool:
    print(f"  {INFO('[FIX]')} Preparando compilacao do llama-cpp-python para i5-1235U...")
    bin_path = str(winlibs_path / "bin")
    os.environ["PATH"] = bin_path + os.pathsep + os.environ.get("PATH", "")
    os.environ["CMAKE_GENERATOR"] = "MinGW Makefiles"
    os.environ["CC"] = "gcc"
    os.environ["CXX"] = "g++"
    os.environ["FORCE_CMAKE"] = "1"
    os.environ["CMAKE_ARGS"] = "-DGGML_NATIVE=ON -DGGML_OPENMP=ON -DGGML_BLAS=OFF -DGGML_LTO=ON"
    
    print(f"  {INFO('[INFO]')} Instalando cmake e ninja no venv...")
    subprocess.run([sys.executable, "-m", "pip", "install", "cmake", "ninja"], check=True, stdout=subprocess.DEVNULL)
    
    print(f"  {INFO('[INFO]')} Limpando instalacoes anteriores...")
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "llama-cpp-python", "-y"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([sys.executable, "-m", "pip", "cache", "purge"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    print(f"  {INFO('[INFO]')} Compilando llama-cpp-python (isso pode levar alguns minutos)...")
    result = subprocess.run([sys.executable, "-m", "pip", "install", "llama-cpp-python==0.3.16", "--no-cache-dir", "--force-reinstall", "--no-binary", "llama-cpp-python"])
    
    if result.returncode == 0:
        print(f"  {OK('[OK]')} llama-cpp-python compilado e instalado com sucesso!")
        return True
    else:
        print(f"  {ERRO('[ERRO]')} Falha na compilacao.")
        return False

def run_checks():
    checks = [check_python(), check_click(), check_numpy(), check_llama_cpp(), check_llama_load(), check_model(), check_orn_package()]
    all_ok = True
    for c in checks:
        status = OK("[OK]") if c.ok else ERRO("[!!]")
        print(f"  {status} {c.nome.ljust(25)} {c.detalhe}")
        if not c.ok and c.fix_cmd:
            print(f"         -> {DIM(c.fix_cmd)}")
            all_ok = False
    print("\n" + "─" * 60)
    if all_ok:
        print(f"  {OK('VERDE')} — 7/7 verificacoes OK")
        print("  Ambiente pronto. Execute: orn config --show")
    else:
        print(f"  {ERRO('PROBLEMAS ENCONTRADOS')} — Execute: python install.py --auto")
    print("─" * 60)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="ORN Environment Setup")
    parser.add_argument("--auto", action="store_true", help="Executa instalacao completa automatica")
    parser.add_argument("--check", action="store_true", help="Apenas verifica o ambiente")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  ORN — Verificacao e Instalacao de Ambiente")
    print("  i5-1235U / Windows / Python 3.12")
    print("=" * 60 + "\n")

    in_venv = (hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix))
    if not in_venv:
        print(f"  {WARN('[AVISO CRITICO]')} Rodando FORA do venv!")
        print(f"  {INFO('Use:')} .\\venv\\Scripts\\python.exe install.py --auto")
        print(f"  {INFO('ou ative o venv:')} .\\venv\\Scripts\\activate\n")

    if args.auto:
        print(f"{INFO('[MODO AUTOMATICO]')} Iniciando configuracao completa...\n")
        winlibs_path = ensure_winlibs()
        print("\n[1/3] Instalando dependencias basicas...")
        subprocess.run([sys.executable, "-m", "pip", "install", "click", "numpy", "cmake", "ninja", "beautifulsoup4", "psutil", "toml"], check=True, stdout=subprocess.DEVNULL)
        print("\n[2/3] Instalando pacote ORN em modo editavel...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], check=True, stdout=subprocess.DEVNULL)
        print("\n[3/3] Compilando motor de inferencia (llama-cpp-python)...")
        success = install_llama_cpp_auto(winlibs_path)
        if success:
            print("\n" + "=" * 60)
            print(f"  {OK('✅ INSTALACAO AUTOMATICA CONCLUIDA COM SUCESSO!')}")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print(f"  {ERRO('❌ A INSTALACAO AUTOMATICA FALHOU.')}")
            print("=" * 60)
            sys.exit(1)
    elif args.check or len(sys.argv) == 1:
        run_checks()
    else:
        print("Use --auto para instalacao completa ou --check para verificar o ambiente.")

if __name__ == "__main__":
    main()
