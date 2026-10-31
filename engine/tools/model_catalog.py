# -*- coding: utf-8 -*-
# engine/tools/model_catalog.py
"""
ORN Model Catalog — leitura/escrita do catálogo de modelos GGUF.

Dois arquivos:
  data/model_catalog.json        -> intenção/contrato (commitado no git)
  data/model_catalog.local.json  -> hashes/sizes reais da máquina (gitignored)

God: Hades (persistência) + Hermes (resolução de alias).
OSL-6:  get_*() retornam cópia, não referência interna.
OSL-7:  resolve_*() retornam None explícito quando não encontrado.
OSL-15: qualquer erro de IO cai em fallback silencioso.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
from pathlib import Path
from typing import Any

_CATALOG_PATH = Path("data") / "model_catalog.json"
_LOCAL_PATH   = Path("data") / "model_catalog.local.json"
_SCAN_DIR     = Path("models")


# ---------------------------------------------------------------------------
# Paths e IO
# ---------------------------------------------------------------------------

def catalog_path() -> Path:
    """Caminho do catálogo commitado (contrato)."""
    return _CATALOG_PATH


def local_path() -> Path:
    """Caminho do cache local (hashes/sizes por máquina)."""
    return _LOCAL_PATH


def _read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return default


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_catalog() -> dict:
    """Carrega o catálogo commitado. Retorna cópia (OSL-6)."""
    return _read_json(_CATALOG_PATH, {"version": 1, "active_alias": None, "models": {}})


def save_catalog(data: dict) -> None:
    """Persiste o catálogo commitado."""
    _write_json(_CATALOG_PATH, data)


def load_local_cache() -> dict:
    """Carrega o cache local de hashes/sizes. Retorna cópia."""
    return _read_json(
        _LOCAL_PATH,
        {"version": 1, "machine_id": platform.node(), "models": {}},
    )


def save_local_cache(data: dict) -> None:
    """Persiste o cache local."""
    _write_json(_LOCAL_PATH, data)


# ---------------------------------------------------------------------------
# Resolução de alias
# ---------------------------------------------------------------------------

def get_entry(alias: str) -> dict | None:
    """Retorna a entrada do catálogo (dict) ou None. OSL-7."""
    cat = load_catalog()
    entry = cat.get("models", {}).get(alias)
    if isinstance(entry, dict):
        return dict(entry)  # cópia (OSL-6)
    return None


def list_entries() -> list[tuple[str, dict]]:
    """Lista (alias, entry) ordenado por alias."""
    cat = load_catalog()
    models = cat.get("models", {})
    if not isinstance(models, dict):
        return []
    return sorted(
        ((a, dict(e)) for a, e in models.items() if isinstance(e, dict)),
        key=lambda x: x[0],
    )


def get_active_alias() -> str | None:
    """Retorna o active_alias do catálogo, ou None."""
    cat = load_catalog()
    alias = cat.get("active_alias")
    return alias if isinstance(alias, str) and alias else None


def set_active_alias(alias: str) -> None:
    """Define o active_alias no catálogo. Valida que o alias existe."""
    cat = load_catalog()
    if alias not in cat.get("models", {}):
        raise KeyError(f"alias não catalogado: {alias!r}")
    cat["active_alias"] = alias
    save_catalog(cat)


def resolve_alias(alias: str) -> Path | None:
    """Resolve um alias específico para Path. None se não existe/arquivo ausente."""
    entry = get_entry(alias)
    if entry is None:
        return None
    raw = entry.get("path")
    if not raw:
        return None
    p = Path(raw)
    return p if p.exists() else None


def resolve_active_model() -> Path | None:
    """
    Resolve o modelo ativo com precedência:
      1. env ORN_MODEL_PATH       (override absoluto)
      2. env ORN_MODEL_ALIAS      (alias específico)
      3. catálogo active_alias
    Retorna None se nada resolver — o chamador decide o fallback.
    """
    env_path = os.environ.get("ORN_MODEL_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    env_alias = os.environ.get("ORN_MODEL_ALIAS", "").strip()
    if env_alias:
        p = resolve_alias(env_alias)
        if p is not None:
            return p

    active = get_active_alias()
    if active:
        return resolve_alias(active)

    return None


# ---------------------------------------------------------------------------
# Scan e verificação
# ---------------------------------------------------------------------------

def _sha256_of(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _size_mb(path: Path) -> float:
    try:
        return round(path.stat().st_size / (1024 * 1024), 1)
    except OSError:
        return 0.0


def scan_models(
    models_dir: Path | str = _SCAN_DIR,
    compute_hash: bool = False,
) -> list[dict]:
    """
    Varre o diretório de modelos, encontra .gguf, e reconcilia com o catálogo.
    Retorna lista de dicts:
      {"alias": str, "path": str, "known": bool,
       "size_mb": float, "sha256": str|None}
    Não adiciona automaticamente ao catálogo — o chamador decide.
    """
    root = Path(models_dir)
    if not root.exists():
        return []

    cat = load_catalog()
    known_paths: dict[str, str] = {
        str(Path(e.get("path", ""))).replace("\\", "/"): a
        for a, e in cat.get("models", {}).items()
        if isinstance(e, dict) and e.get("path")
    }

    results: list[dict] = []
    for gguf in sorted(root.rglob("*.gguf")):
        rel = str(gguf).replace("\\", "/")
        alias = known_paths.get(rel)
        row = {
            "alias":    alias,
            "path":     rel,
            "known":    alias is not None,
            "size_mb":  _size_mb(gguf),
            "sha256":   None,
        }
        if compute_hash:
            try:
                row["sha256"] = _sha256_of(gguf)
            except OSError:
                row["sha256"] = None
        results.append(row)

    return results


def verify_entry(alias: str) -> tuple[bool, str]:
    """
    Verifica integridade de um alias.
    Retorna (ok, motivo).
    """
    entry = get_entry(alias)
    if entry is None:
        return False, f"alias não catalogado: {alias!r}"

    raw = entry.get("path")
    if not raw:
        return False, "entrada sem campo 'path'"

    p = Path(raw)
    if not p.exists():
        return False, f"arquivo ausente: {p}"

    cache = load_local_cache()
    cached = cache.get("models", {}).get(alias, {})
    cached_hash = cached.get("sha256")
    if not cached_hash:
        return True, f"arquivo presente ({_size_mb(p)} MB), sem hash registrado"

    actual = _sha256_of(p)
    if actual != cached_hash:
        return False, f"sha256 divergente (esperado {cached_hash[:12]}..., obtido {actual[:12]}...)"

    return True, f"ok ({_size_mb(p)} MB, sha256 {actual[:12]}...)"
