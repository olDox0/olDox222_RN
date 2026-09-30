#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
⚡ NEXUS SOVEREIGN SETUP & INSTALLER V4.0 (VULCAN CORE)
Projeto: ORN_proj (CLI: orn_proj)
================================================================================
Instalador autônomo e resiliente para Windows, Linux e Termux.
Cria o ambiente virtual, atualiza ferramentas de build e instala o sistema.
================================================================================
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Força UTF-8 no ambiente Python para subprocessos
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

if os.name == 'nt':
    os.system('')  # Ativa suporte a ANSI no Windows CMD/PowerShell

class UI:
    CYAN    = '\033[1;36m'
    GREEN   = '\033[1;32m'
    YELLOW  = '\033[1;33m'
    RED     = '\033[1;31m'
    MAGENTA = '\033[1;35m'
    BOLD    = '\033[1m'
    DIM     = '\033[2m'
    RESET   = '\033[0m'

def log_header(title: str):
    print(f"\n{UI.CYAN}{UI.BOLD}{'='*68}")
    print(f" 🚀 {title}")
    print(f"{'='*68}{UI.RESET}")

def log_step(step: str, desc: str):
    print(f"\n{UI.MAGENTA}[FASE {step}]{UI.RESET} {UI.BOLD}{desc}{UI.RESET}")

def log_ok(msg: str):
    print(f"  {UI.GREEN}✔{UI.RESET} {msg}")

def log_warn(msg: str):
    print(f"  {UI.YELLOW}⚠{UI.RESET} {msg}")

def log_err(msg: str):
    print(f"  {UI.RED}✘{UI.RESET} {msg}")

def get_venv_paths(root: Path):
    venv_dir = root / "venv"
    if os.name == "nt":
        scripts_dir = venv_dir / "Scripts"
        python_exe = scripts_dir / "python.exe"
        pip_exe = scripts_dir / "pip.exe"
        activate_cmd = f"call {scripts_dir / 'activate.bat'}"
    else:
        scripts_dir = venv_dir / "bin"
        python_exe = scripts_dir / "python"
        pip_exe = scripts_dir / "pip"
        activate_cmd = f"source {scripts_dir / 'activate'}"

    return {
        "venv_dir": venv_dir,
        "scripts_dir": scripts_dir,
        "python": python_exe,
        "pip": pip_exe,
        "activate": activate_cmd
    }

def safe_run(cmd, cwd=None, check=True) -> subprocess.CompletedProcess:
    """Executor blindado contra UnicodeDecodeError no Windows."""
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env
    )

def main():
    log_header("ORN_PROJ: INSTALADOR SOBERANO V4.0")
    paths = get_venv_paths(ROOT)

    # FASE 1: Verificação
    log_step("1/5", "Auditoria do Interpretador Base...")
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        log_err(f"Python 3.10+ é obrigatório. Versão atual: {v.major}.{v.minor}.{v.micro}")
        sys.exit(1)
    log_ok(f"Python Base compatível: {v.major}.{v.minor}.{v.micro}")

    # FASE 2: Venv
    log_step("2/5", "Isolamento de Ambiente Virtual (venv)...")
    if not paths["venv_dir"].exists():
        safe_run([sys.executable, "-m", "venv", str(paths["venv_dir"])])
        log_ok("Ambiente virtual forjado com sucesso.")
    else:
        log_ok("Ambiente virtual existente detectado.")

    # FASE 3: Build Tools
    log_step("3/5", "Bootstrapping de Ferramentas de Build...")
    safe_run([
        str(paths["python"]), "-m", "pip", "install", "--upgrade",
        "pip", "setuptools>=68.0.0", "wheel>=0.41.0"
    ])
    log_ok("Ferramentas de build atualizadas.")

    # FASE 4: Instalação
    log_step("4/5", "Instalação do Pacote em Modo Editável...")
    safe_run([str(paths["python"]), "-m", "pip", "install", "-e", str(ROOT)])
    log_ok("Projeto registrado no ambiente virtual.")

    # FASE 5: Diretórios
    log_step("5/5", "Diretórios de Dados e Persistência...")
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    log_ok("Diretórios essenciais verificados.")

    log_header("INSTALAÇÃO CONCLUÍDA!")
    print(f"{UI.GREEN}{UI.BOLD}Para ativar o ambiente neste terminal:{UI.RESET}\n")
    print(f"  {UI.CYAN}{UI.BOLD}{paths['activate']}{UI.RESET}\n")

if __name__ == '__main__':
    main()
