# -*- coding: utf-8 -*-
"""Bootstrap helpers for ORN server runtime."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def looks_like_doxoade_root(path_str: str | None) -> bool:
    if not path_str:
        return False
    try:
        p = Path(path_str).resolve()
    except Exception:
        return False
    return (p / "doxoade" / "__init__.py").exists()


def discover_doxoade_root() -> str | None:
    # 1. Env var explícita tem prioridade
    env_root = os.environ.get("DOXOADE_ROOT")
    if looks_like_doxoade_root(env_root):
        return str(Path(env_root).resolve())

    # 2. Sobe a árvore de diretórios a partir deste arquivo
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if looks_like_doxoade_root(str(parent)):
            return str(parent)

    # 3. doxoade instalado no venv atual (site-packages)
    try:
        import importlib.util
        spec = importlib.util.find_spec("doxoade")
        if spec and spec.origin:
            pkg_root = Path(spec.origin).parent.parent
            if looks_like_doxoade_root(str(pkg_root)):
                return str(pkg_root)
    except Exception:
        pass

    # 4. Varre o PATH — detecta projeto doxoade via venv/Scripts no PATH
    #    Ex: C:\...\doxoade\venv\Scripts → sobe até encontrar doxoade/__init__.py
    path_env = os.environ.get("PATH", "")
    sep = ";" if os.name == "nt" else ":"
    for entry in path_env.split(sep):
        entry = entry.strip().strip('"')
        if not entry:
            continue
        try:
            p = Path(entry).resolve()
        except Exception:
            continue
        # sobe até 4 níveis procurando a raiz do projeto doxoade
        for candidate in [p, *p.parents][:5]:
            if looks_like_doxoade_root(str(candidate)):
                return str(candidate)

    return None


def vulcan_boot() -> tuple[bool, str]:
    root = discover_doxoade_root()
    if root and root not in sys.path:
        sys.path.insert(0, root)
        os.environ["DOXOADE_ROOT"] = root

    try:
        import doxoade  # noqa: F401
    except ImportError as exc:
        return False, (
            f"'doxoade' nao encontrado em sys.path nem instalado no venv.\n"
            f"ImportError: {exc}\n"
            f"Solucoes:\n"
            f"  a) Execute na raiz do projeto\n"
            f"  b) pip install -e <raiz>\n"
            f"  c) defina DOXOADE_ROOT=<raiz>\n"
        )

    try:
        from doxoade.tools.vulcan.runtime import find_vulcan_project_root, install_meta_finder

        root_path = find_vulcan_project_root(Path.cwd()) or find_vulcan_project_root(__file__)
        if root_path is None:
            return False, (
                "doxoade importado OK, mas '.doxoade/vulcan/bin' nao encontrado.\n"
                "Execute 'doxoade vulcan lib' antes de iniciar o servidor."
            )

        install_meta_finder(root_path)

        lib_bin = root_path / ".doxoade" / "vulcan" / "lib_bin"
        n_bins = len(list(lib_bin.glob("*.pyd"))) if lib_bin.exists() else 0
        return True, f"raiz='{root_path}' | {n_bins} binario(s) em lib_bin/"
    except Exception:
        return False, f"MetaFinder falhou:\n{traceback.format_exc()}"
