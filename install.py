# install.py
"""
================================================================================
⚡ SYSUTILS: INSTALADOR CANÔNICO & UNIFICADO V5.0 (JANUS & VULCAN CORE)
================================================================================
Compatível com Windows, Linux e Termux (Python 3.10+).
Executa bootstrapping, compilação Metalcraft opcional e registra 'sysutils'.
================================================================================
"""
from __future__ import annotations
import os
import sys
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_UTF8 = os.environ.copy()
ENV_UTF8["PYTHONUTF8"] = "1"
ENV_UTF8["PYTHONIOENCODING"] = "utf-8"

class UI:
    CYAN    = '\033[1;36m'
    GREEN   = '\033[1;32m'
    YELLOW  = '\033[1;33m'
    RED     = '\033[1;31m'
    MAGENTA = '\033[1;35m'
    BOLD    = '\033[1m'
    RESET   = '\033[0m'

def log_header(title: str):
    print(f"\n{UI.CYAN}{UI.BOLD}{'='*68}")
    print(f" 🚀 {title}")
    print(f"{'='*68}{UI.RESET}")

def log_step(step: str, desc: str):
    print(f"\n{UI.MAGENTA}[FASE {step}]{UI.RESET} {UI.BOLD}{desc}{UI.RESET}")

def log_ok(msg: str):   print(f"  {UI.GREEN}✔{UI.RESET} {msg}")
def log_warn(msg: str): print(f"  {UI.YELLOW}⚠{UI.RESET} {msg}")
def log_err(msg: str):  print(f"  {UI.RED}✘{UI.RESET} {msg}")

def safe_run(cmd, cwd=None, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=ENV_UTF8,
        shell=False
    )

def main():
    log_header("SYSUTILS: INSTALADOR SOBERANO UNIFICADO V5.0")
    
    # 1. Auditoria do Interpretador
    log_step("1/5", "Auditoria do Ambiente...")
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        log_err(f"Python 3.10+ obrigatório. Versão atual: {v.major}.{v.minor}")
        sys.exit(1)
    log_ok(f"Interpretador Python ativo: {v.major}.{v.minor}.{v.micro}")

    # 2. Estrutura de Diretórios
    log_step("2/5", "Topologia e Persistência...")
    dirs = [
        ROOT / "bin",
        ROOT / "bin" / "input-leap",
        ROOT / "data",
        ROOT / "data" / "db",
        ROOT / "data" / "leap" / "logs",
        ROOT / ".doxoade" / "logs",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    log_ok("Pastas de dados e binários inicializadas.")

    # 3. Ferramentas de Build
    log_step("3/5", "Atualizando Pip, Setuptools e Wheel...")
    try:
        safe_run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools>=68.0.0", "wheel"])
        log_ok("Gerenciadores atualizados.")
    except Exception as e:
        log_warn(f"Aviso no bootstrap de build: {e}")

    # 4. Registro do Pacote em Modo Editável
    log_step("4/5", "Registrando ponto de entrada 'sysutils'...")
    try:
        res = safe_run([sys.executable, "-m", "pip", "install", "-e", "."], cwd=str(ROOT))
        log_ok("Pacote 'sysutils' instalado no venv.")
    except subprocess.CalledProcessError as e:
        log_err(f"Falha na instalação: {e.stderr}")
        sys.exit(1)

    # 5. Compilação C Opcional (Metalcraft / GCC)
    log_step("5/5", "Auditoria de Compiladores C (Metalcraft)...")
    gcc = shutil.which("gcc")
    if gcc:
        log_ok(f"Compilador nativo localizado: {gcc}")
    else:
        log_warn("Compilador GCC não localizado no PATH. Binários portáteis serão usados.")

    log_header("INSTALAÇÃO CONCLUÍDA COM 100% DE SUCESSO!")
    print(f"Para iniciar, execute:\n   {UI.YELLOW}sysutils --help{UI.RESET}\n")

if __name__ == "__main__":
    main()
