# -*- coding: utf-8 -*-
"""Shim de compatibilidade — `engine/web/web_server.py` foi modularizado.

Mantém `from engine.web.web_server import WebCLI, WebServer, ORNHandler`
funcionando para o `__main__.py` e qualquer import externo.
"""
from engine.web.cli import WebCLI
from engine.web.handler import ORNHandler
from engine.web.server import WebServer

__all__ = ["WebCLI", "WebServer", "ORNHandler"]
