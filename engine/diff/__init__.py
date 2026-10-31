# -*- coding: utf-8 -*-
# engine/diff/__init__.py
"""
ORN Diff Engine — SEARCH/REPLACE + PatchSurgeon.

Módulos:
  format.py    → parser/formatter de SEARCH/REPLACE blocks
  surgeon.py   → motor de patch (port do mody_patch, sem doxoade)
  preflight.py → classificação de hunks antes de aplicar
  sandbox.py   → wrapper de validação/execução em isolamento

God: Hefesto (transformação) + Ma'at (invariantes de sintaxe).
"""

__version__ = "0.1.0"
