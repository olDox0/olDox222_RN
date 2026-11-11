# -*- coding: utf-8 -*-
"""Reverte think() e adiciona trace em fix() por AST (não str.replace)."""
import ast
import re
from pathlib import Path

p = Path("engine/cli.py")
src = p.read_text(encoding="utf-8")
original = src

# ══════════════════════════════════════════════════════════════
# 1. REVERTER think() — bloco exato do mody show
# ══════════════════════════════════════════════════════════════
think_buggy = '''    if not result.success:
        for err in result.errors:
            if not verbose and "raw_output do modelo" in err:
                continue
            for line in err.splitlines():
                Display.error(line)
        if verbose and result.metadata.get("surgical_trace"):
            _print_surgical_trace(result.metadata["surgical_trace"])
        raise SystemExit(1)
'''
think_original = '''    if not result.success:
        for err in result.errors:
            Display.error(err)
        raise SystemExit(1)
'''

if think_buggy in src:
    src = src.replace(think_buggy, think_original, 1)
    print("[OK] think() revertido (removeu -v filter + trace call)")
else:
    print("[X] think() bloco não encontrado — pode já ter sido revertido ou ter whitespace diferente")
    print("    esperado (primeiras 3 linhas):")
    for line in think_buggy.splitlines()[:3]:
        print(f"    {repr(line)}")

# ══════════════════════════════════════════════════════════════
# 2. LOCALIZAR fix() via findstr-like search
# ══════════════════════════════════════════════════════════════
m = re.search(r'^def fix\(', src, re.MULTILINE)
if not m:
    print("[X] def fix( não encontrado")
    raise SystemExit(1)

fix_start = m.start()
line_of_fix = src[:fix_start].count("\n") + 1
print(f"[i] def fix( está na linha {line_of_fix}")

# Achar primeiro `if not result.success:` depois de fix()
tail = src[fix_start:]
m_err = re.search(
    r'^    if not result\.success:\n'
    r'(?:        [^\n]*\n)*?'
    r'        raise SystemExit\(1\)\n',
    tail,
    re.MULTILINE,
)
if not m_err:
    print("[X] bloco `if not result.success:` de fix() não encontrado")
    print("    rode: doxoade mody show -p {}-{} engine\\cli.py".format(
        line_of_fix, line_of_fix + 60
    ))
    raise SystemExit(1)

old_block = m_err.group(0)
line_of_block = src[:fix_start + m_err.start()].count("\n") + 1
print(f"[i] bloco de erro de fix() está nas linhas {line_of_block}–{line_of_block + old_block.count(chr(10)) - 1}")

# Se já tem trace, não re-aplicar
if "surgical_trace" in old_block:
    print("[i] fix() já tem trace call, pulando")
else:
    new_block = '''    if not result.success:
        for err in result.errors:
            if not verbose and "raw_output do modelo" in err:
                continue
            for line in err.splitlines():
                Display.error(line)
        if verbose and result.metadata.get("surgical_trace"):
            _print_surgical_trace(result.metadata["surgical_trace"])
        raise SystemExit(1)
'''
    abs_start = fix_start + m_err.start()
    abs_end   = fix_start + m_err.end()
    src = src[:abs_start] + new_block + src[abs_end:]
    print("[OK] fix() phase 1 recebeu -v filter + trace call")

# ══════════════════════════════════════════════════════════════
# 3. Fase 2 (apply_res) — também pode precisar
# ══════════════════════════════════════════════════════════════
# Buscar `if not apply_res.success:` no fix()
m_apply = re.search(
    r'^    if not apply_res\.success:\n'
    r'(?:        [^\n]*\n)*?'
    r'        raise SystemExit\(1\)\n',
    src[fix_start:],
    re.MULTILINE,
)
if m_apply:
    old_apply = m_apply.group(0)
    line_apply = src[:fix_start + m_apply.start()].count("\n") + 1
    if "surgical_trace" not in old_apply:
        new_apply = '''    if not apply_res.success:
        for err in apply_res.errors:
            if not verbose and "raw_output do modelo" in err:
                continue
            for line in err.splitlines():
                Display.error(line)
        if verbose and apply_res.metadata.get("surgical_trace"):
            _print_surgical_trace(apply_res.metadata["surgical_trace"])
        raise SystemExit(1)
'''
        abs_start = fix_start + m_apply.start()
        abs_end   = fix_start + m_apply.end()
        src = src[:abs_start] + new_apply + src[abs_end:]
        print(f"[OK] fix() phase 2 (apply_res) nas linhas {line_apply} também patcheado")
    else:
        print("[i] fix() phase 2 já tem trace")

# ══════════════════════════════════════════════════════════════
# Aplicar
# ══════════════════════════════════════════════════════════════
if src != original:
    p.write_text(src, encoding="utf-8")
    print("\n[i] engine/cli.py atualizado")
    print("[i] próximo: python -m py_compile engine/cli.py")
else:
    print("\n[i] nada mudou")