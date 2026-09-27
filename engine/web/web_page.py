# -*- coding: utf-8 -*-
"""Carrega HTML estático da interface web ORN."""

from __future__ import annotations

from pathlib import Path

_HTML_PATH = Path(__file__).with_name("static") / "index.html"
HTML = _HTML_PATH.read_text(encoding="utf-8")

