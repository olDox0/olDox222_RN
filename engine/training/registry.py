# -*- coding: utf-8 -*-
# engine/training/registry.py
"""
ModelRegistry — fachada orientada a objeto sobre model_catalog.py.

Uso interno pelos comandos `orn models ...`. Não é dependência do runtime
de inferência (o BridgeConfig usa model_catalog.resolve_active_model()
diretamente, mais leve).

God: Hades (persistência) + Atena (organização).
OSL-6:  all()/get() retornam cópias/novas dataclasses.
OSL-7:  add() valida entrada; get() retorna None se ausente.
OSL-15: IOError/JSONDecodeError caem em estado vazio, nunca propagam.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from engine.tools import model_catalog as mc


@dataclass
class ModelEntry:
    alias:      str
    path:       Path
    base:       str
    quant:      str
    tags:       list[str] = field(default_factory=list)
    source:     str = ""
    created_at: str = ""
    adapter:    str | None = None
    size_mb:    float | None = None
    sha256:     str | None = None

    def to_dict(self) -> dict:
        return {
            "path":       str(self.path).replace("\\", "/"),
            "base":       self.base,
            "quant":      self.quant,
            "tags":       list(self.tags),
            "source":     self.source,
            "created_at": self.created_at,
            **({"adapter": self.adapter} if self.adapter else {}),
        }

    @classmethod
    def from_dict(cls, alias: str, data: dict) -> "ModelEntry":
        return cls(
            alias=alias,
            path=Path(data.get("path", "")),
            base=str(data.get("base", "")),
            quant=str(data.get("quant", "")),
            tags=list(data.get("tags", []) or []),
            source=str(data.get("source", "")),
            created_at=str(data.get("created_at", "")),
            adapter=data.get("adapter"),
        )


class ModelRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, ModelEntry] = {}
        self._active: str | None = None
        self.load()

    # --- IO ---------------------------------------------------------------

    def load(self) -> None:
        cat = mc.load_catalog()
        models = cat.get("models", {}) if isinstance(cat, dict) else {}
        self._entries = {
            alias: ModelEntry.from_dict(alias, data)
            for alias, data in models.items()
            if isinstance(data, dict)
        }
        active = cat.get("active_alias")
        self._active = active if isinstance(active, str) and active in self._entries else None
        self._merge_local_cache()

    def _merge_local_cache(self) -> None:
        cache = mc.load_local_cache()
        local = cache.get("models", {}) if isinstance(cache, dict) else {}
        for alias, entry in self._entries.items():
            local_row = local.get(alias, {})
            if isinstance(local_row, dict):
                entry.size_mb = local_row.get("size_mb")
                entry.sha256 = local_row.get("sha256")

    def save(self) -> None:
        cat = mc.load_catalog()
        cat["version"] = 1
        cat["active_alias"] = self._active
        cat["models"] = {a: e.to_dict() for a, e in self._entries.items()}
        mc.save_catalog(cat)

    # --- Consultas --------------------------------------------------------

    def all(self) -> list[ModelEntry]:
        return sorted(self._entries.values(), key=lambda e: e.alias)

    def get(self, alias: str) -> ModelEntry | None:
        return self._entries.get(alias)

    def active(self) -> ModelEntry | None:
        return self._entries.get(self._active) if self._active else None

    def active_alias(self) -> str | None:
        return self._active

    # --- Mutação ----------------------------------------------------------

    def add(self, entry: ModelEntry, *, set_active: bool = False) -> None:
        if not entry.alias:
            raise ValueError("alias vazio")
        if not entry.path:
            raise ValueError("path vazio")
        self._entries[entry.alias] = entry
        if set_active:
            self._active = entry.alias
        self.save()

    def remove(self, alias: str) -> bool:
        if alias not in self._entries:
            return False
        del self._entries[alias]
        if self._active == alias:
            self._active = None
        self.save()
        return True

    def set_active(self, alias: str) -> None:
        if alias not in self._entries:
            raise KeyError(f"alias não catalogado: {alias!r}")
        self._active = alias
        mc.set_active_alias(alias)

    # --- Scan / verify (delega para model_catalog) ------------------------

    def scan(self, models_dir: Path | str = "models", compute_hash: bool = False) -> list[dict]:
        return mc.scan_models(models_dir=models_dir, compute_hash=compute_hash)

    def verify(self, alias: str) -> tuple[bool, str]:
        return mc.verify_entry(alias)
