# -*- coding: utf-8 -*-
"""Corrige trace print: move de think() para fix()."""
from pathlib import Path

p = Path("engine/cli.py")
src = p.read_text(encoding="utf-8")
original = src

# ─────────────────────────────────────────────────────────
# 1. Reverter think() para o código original (sem -v filter,
#    sem trace, pois verbose não existe nesse escopo)
# ─────────────────────────────────────────────────────────
think_buggy = '''        if not verbose and "raw_output do modelo" in err:
            continue
        for line in err.splitlines():
            Display.error(line)
    if verbose and result.metadata.get("surgical_trace"):
        _print_surgical_trace(result.metadata["surgical_trace"])
    raise SystemExit(1)

Display.separator()
if raw:
    print(result.output)'''

think_original = '''        Display.error(err)
    raise SystemExit(1)

Display.separator()
if raw:
    print(result.output)'''

if think_buggy in src:
    src = src.replace(think_buggy, think_original, 1)
    print("  [OK] think() revertido")
else:
    print("  [X] bloco buggy de think() não encontrado")
    print("      rode `doxoade mody show -p 428-450 engine/cli.py` e cole no chat")

# ─────────────────────────────────────────────────────────
# 2. Adicionar trace print em fix() (após o -v filter)
# ─────────────────────────────────────────────────────────
fix_old = '''if not result.success:
        for err in result.errors:
            if not verbose and "raw_output do modelo" in err:
                continue
            for line in err.splitlines():
                Display.error(line)
        raise SystemExit(1)

    Display.separator()
    print(result.output)
    Display.separator()

    if dry_run:'''

fix_new = '''if not result.success:
        for err in result.errors:
            if not verbose and "raw_output do modelo" in err:
                continue
            for line in err.splitlines():
                Display.error(line)
        if verbose and result.metadata.get("surgical_trace"):
            _print_surgical_trace(result.metadata["surgical_trace"])
        raise SystemExit(1)

    Display.separator()
    print(result.output)
    Display.separator()

    if dry_run:'''

if fix_old in src:
    src = src.replace(fix_old, fix_new, 1)
    print("  [OK] fix() recebeu o trace print")
else:
    print("  [X] bloco de fix() não encontrado")
    print("      rode `doxoade mody show -p 1130-1180 engine/cli.py` e cole no chat")

# ─────────────────────────────────────────────────────────
# 3. Remover campo duplicado em DiffResult (diff_engine.py)
# ─────────────────────────────────────────────────────────
p2 = Path("engine/tools/diff_engine.py")
src2 = p2.read_text(encoding="utf-8")

dup = '''    surgical_trace: dict | None = None
    surgical_trace: dict | None = None    # ← NOVO
'''
single = '''    surgical_trace: dict | None = None    # F5.5b
'''

if dup in src2:
    src2 = src2.replace(dup, single, 1)
    p2.write_text(src2, encoding="utf-8")
    print("  [OK] DiffResult campo duplicado removido")
else:
    print("  [i] campo duplicado não encontrado (talvez já foi corrigido)")

# ─────────────────────────────────────────────────────────
# Aplicar mudanças em cli.py
# ─────────────────────────────────────────────────────────
if src != original:
    p.write_text(src, encoding="utf-8")
    print("  [OK] engine/cli.py atualizado")

print("\nPróximo: python -m py_compile engine/cli.py engine/tools/diff_engine.py")