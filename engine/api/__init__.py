# -*- coding: utf-8 -*-
"""engine.api — inferência transport-agnostic.

Imports são lazy (PEP 562) para evitar RuntimeWarning quando o módulo é
executado com `python -m engine.api.events`.
"""
from __future__ import annotations

_LAZY = {
    "StreamEvent":           ("engine.api.events", "StreamEvent"),
    "to_ndjson":             ("engine.api.events", "to_ndjson"),
    "parse_ndjson_line":     ("engine.api.events", "parse_ndjson_line"),
    "iter_events_from_lines":("engine.api.events", "iter_events_from_lines"),
    "InferenceFacade":       ("engine.api.facade", "InferenceFacade"),
}

__all__ = list(_LAZY)


def __getattr__(name: str):
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module 'engine.api' has no attribute {name!r}")
    mod_name, attr = target
    import importlib
    mod = importlib.import_module(mod_name)
    return getattr(mod, attr)
