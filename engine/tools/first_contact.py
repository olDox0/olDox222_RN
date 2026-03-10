# -*- coding: utf-8 -*-
"""
ORN — First Contact (Hefesto)
Verificação de ambiente antes da primeira inferência.

Calibrado para hardware low-end (Celeron N2808, REP.INFRA.20260209.GOLD).
Detecta problemas antes do load de 80 segundos para não desperdiçar tempo.

OSL-5.2: Valida todo o ambiente antes de tentar carregar o modelo.
OSL-18:  Stdlib apenas (os, sys, pathlib, importlib).
God: Hefesto — verifica se a forja está em condições antes de acender.
"""

from __future__ import annotations

import sys
# [DOX-UNUSED] from pathlib import Path


def check_environment() -> list[str]:
    """Verifica o ambiente e retorna lista de problemas encontrados.

    Executado por `orn config --show` antes de qualquer inferência.
    Não levanta exceções — retorna problemas como strings descritivas.

    Returns:
        Lista de strings com problemas encontrados.
        Lista vazia = ambiente OK, pronto para `orn think`.
    """
    issues: list[str] = []

    # 1. Python >= 3.10 (union type hints, match/case)
    _check_python(issues)

    # 2. llama-cpp-python instalado e importável
    _check_llama_cpp(issues)

    # 3. Modelo .gguf presente no path esperado
    _check_model(issues)

    # 4. Click instalado
    _check_click(issues)

    # 5. NumPy instalado (VectorDB Fase 3)
    _check_numpy(issues)

    return issues


# ---------------------------------------------------------------------------
# Verificações individuais (OSL-4: cada função faz uma coisa)
# ---------------------------------------------------------------------------

def _check_python(issues: list[str]) -> None:
    """Python >= 3.10 obrigatório."""
    if sys.version_info < (3, 10):
        issues.append(
            f"Python >= 3.10 necessário. Atual: {sys.version.split()[0]}"
        )


def _check_llama_cpp(issues: list[str]) -> None:
    """llama-cpp-python deve ser importável.

    Celeron N2808: instalado via w64devkit (GCC 15.2 + MinGW).
    Se ausente, indica o comando correto para instalar.
    """
    try:
        import importlib.util
        spec = importlib.util.find_spec("llama_cpp")
        if spec is None:
            raise ImportError("não encontrado")
        # Verifica versão se disponível
        import llama_cpp
        ver = getattr(llama_cpp, "__version__", "?")
        # Tudo OK — não adiciona issue
        _ = ver
    except ImportError:
        issues.append(
            "llama-cpp-python NÃO instalado.\n"
            "     Instalar com wheel pré-compilada (sem precisar de MSVC):\n"
            "       pip install llama-cpp-python "
            "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu\n"
            "     Ou verificar instalação pelo w64devkit (doxoade):\n"
            "       python -c \"import llama_cpp; print(llama_cpp.__version__)\""
        )


def _check_model(issues: list[str]) -> None:
    """Modelo .gguf deve existir no path padrão."""
    from engine.core.llm_bridge import BridgeConfig   # noqa: PLC0415
    cfg = BridgeConfig()
    if not cfg.model_path.exists():
        issues.append(
            f"Modelo não encontrado: {cfg.model_path}\n"
            "     Baixar em: https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF\n"
            "     Arquivo: qwen2.5-coder-0.5b-instruct-q4_k_m.gguf\n"
            "     Colocar em: models/sicdox/Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF/"
        )
    else:
        size_mb = cfg.model_path.stat().st_size / (1024 * 1024)
        if size_mb < 100:
            issues.append(
                f"Modelo suspeito: {cfg.model_path.name} tem apenas {size_mb:.0f}MB.\n"
                "     Arquivo pode estar corrompido ou incompleto."
            )


def _check_click(issues: list[str]) -> None:
    """Click deve estar instalado."""
    try:
        import click
        _ = click.__version__
    except ImportError:
        issues.append("click não instalado. Executar: pip install click>=8.1")


def _check_numpy(issues: list[str]) -> None:
    """NumPy necessário para VectorDB (Fase 3).

    REP.INFRA §5.1: atualizações do numpy devem ser precedidas por teste
    de compatibilidade — vínculo binário rígido com ABI do llama-cpp-python.
    """
    try:
        import numpy as np
        ver = np.__version__
        # Avisa se versão for muito nova (potencial incompatibilidade ABI)
        major, minor = (int(x) for x in ver.split(".")[:2])
        if major >= 3:
            issues.append(
                f"NumPy {ver} detectado. Versão >= 3.x pode ter incompatibilidade\n"
                "     de ABI com llama-cpp-python. Testar com:\n"
                "       python -c \"from llama_cpp import Llama; print('OK')\""
            )
    except ImportError:
        issues.append("numpy não instalado. Executar: pip install numpy>=1.26")


# ---------------------------------------------------------------------------
# Sumário de performance esperada (informativo para orn config --show)
# ---------------------------------------------------------------------------

def hardware_profile() -> dict[str, str]:
    """Retorna perfil de hardware detectado. OSL-12: informativo."""
    import platform

    profile = {
        "python":   sys.version.split()[0],
        "platform": platform.platform(),
        "machine":  platform.machine(),
    }

    # Detecta capacidades SSE/AVX (informativo — não bloqueia)
    try:
        import subprocess
        result = subprocess.run(
            ["python", "-c",
             "from llama_cpp import Llama; print(Llama.__doc__ or 'loaded')"],
            capture_output=True, text=True, timeout=5
        )
        profile["llama_cpp"] = "OK" if result.returncode == 0 else "ERRO"
    except Exception:
        profile["llama_cpp"] = "não verificado"

    return profile