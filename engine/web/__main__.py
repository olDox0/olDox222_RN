# --- DOXOADE_VULCAN_BOOTSTRAP:START ---
from pathlib import Path as _doxo_path
import importlib.util as _doxo_importlib_util

_doxo_activate_vulcan = None
for _doxo_base in [_doxo_path(__file__).resolve(), *_doxo_path(__file__).resolve().parents]:
    _doxo_runtime_file = _doxo_base / ".doxoade" / "vulcan" / "runtime.py"
    if not _doxo_runtime_file.exists():
        continue
    _doxo_spec = _doxo_importlib_util.spec_from_file_location("_doxoade_vulcan_runtime", str(_doxo_runtime_file))
    if not (_doxo_spec and _doxo_spec.loader):
        continue
    _doxo_mod = _doxo_importlib_util.module_from_spec(_doxo_spec)
    _doxo_spec.loader.exec_module(_doxo_mod)
    _doxo_activate_vulcan = getattr(_doxo_mod, "activate_vulcan", None)
    break

if callable(_doxo_activate_vulcan):
    _doxo_activate_vulcan(globals(), __file__)
# --- DOXOADE_VULCAN_BOOTSTRAP:END ---

# -*- coding: utf-8 -*-
# engine/web/__main__.py
"""
ORN — orn-web entry point
God: Apolo — a interface que da forma ao pensamento.
"""
#from __future__ import annotations
import sys

def main() -> None:
    from engine.web.web_server import WebCLI
    WebCLI().run(sys.argv[1:])

if __name__ == "__main__":
    main()