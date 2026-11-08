# -*- coding: utf-8 -*-
"""Corrige o cli.py após o patch surgical do teste 3.

- renomeia repl_cmd → session_cmd
- restaura docstring + import dentro da função
- remove o import solto antes do decorator
"""
from pathlib import Path

p = Path("engine/cli.py")
src = p.read_text(encoding="utf-8")
original = src

# 1. Renomear comando e função
src = src.replace('@cli.command("repl_cmd")', '@cli.command("session")')
src = src.replace('def repl_cmd(initial_file):', 'def session_cmd(initial_file):')

# 2. Restaurar docstring + import dentro da função
old_body = '''def session_cmd(initial_file):
    """REPL interativa com o ORN."""
    from engine.tools.server_client import is_server_online'''
new_body = '''def session_cmd(initial_file):
    """REPL para edição interativa com o ORN."""
    from engine.core.executive import SiCDoxExecutive
    from engine.tools.server_client import is_server_online'''
src = src.replace(old_body, new_body)

# 3. Remover o import solto antes do decorator
src = src.replace(
    'from engine.core.executive import SiCDoxExecutive\n\n@cli.command("session")',
    '@cli.command("session")',
)

if src == original:
    print("⚠ nada mudou — verifique se o arquivo está no estado esperado")
else:
    p.write_text(src, encoding="utf-8")
    print("✓ engine/cli.py corrigido")