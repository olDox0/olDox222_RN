# -*- coding: utf-8 -*-
"""Fix 1 (confidence=medium) + Fix 3b (guard indent no fallback).

Evita o bug do f59_observations.py: src não é sobrescrito.
"""
from pathlib import Path

p = Path("engine/tools/diff_engine.py")
src = p.read_text(encoding="utf-8")
changes = 0

# ═══════════════════════════════════════════════════════════════
# Fix 1 — confidence=medium aceito
# ═══════════════════════════════════════════════════════════════
old_cond = 'if best is None or best.confidence != "high":'
new_cond = 'if best is None or best.confidence == "low":'

if old_cond in src:
    n = src.count(old_cond)
    src = src.replace(old_cond, new_cond, 1)
    changes += 1
    print(f"[OK] Fix 1: '{old_cond}' -> '{new_cond}' ({n} ocorrência(s))")
elif new_cond in src:
    print("[i] Fix 1: já aplicado")
else:
    print("[X] Fix 1: padrão não encontrado")

# ═══════════════════════════════════════════════════════════════
# Fix 3b — guard de indent no fallback block
# ═══════════════════════════════════════════════════════════════
old_fb = '''    trace["outcome"] = "ok_block_format"
    snippet_lines = snippet.splitlines()
    new_lines = new_code.rstrip("\\n").splitlines()
    trace["hunks_count"] = 1
    trace["added_lines"] = len(new_lines)
    trace["removed_lines"] = len(snippet_lines)

    return [DiffHunk(
        line=best.symbol.start_line,
        removed=snippet_lines,
        added=new_lines,
    )]'''

new_fb = '''    trace["outcome"] = "ok_block_format"
    snippet_lines = snippet.splitlines()
    new_lines = new_code.rstrip("\\n").splitlines()
    trace["hunks_count"] = 1
    trace["added_lines"] = len(new_lines)
    trace["removed_lines"] = len(snippet_lines)

    # F5.9 Guard 3b: método perdeu indentação no fallback block
    if best.symbol.kind == "method" and new_lines:
        first = new_lines[0]
        if first and not first.startswith((" ", "\\t")):
            trace["outcome"] = "lost_method_indent"
            if symbol_mode == "on":
                return DiffResult(
                    success=False,
                    raw_output=raw,
                    errors=[
                        f"Modelo devolveu `{best.symbol.name}` (método) "
                        "sem indentação. Aplicar quebraria a classe.",
                        "Use -v para ver o raw.",
                    ],
                    elapsed_s=round(time.monotonic() - t0, 2),
                    surgical_trace=trace,
                )
            return None

    return [DiffHunk(
        line=best.symbol.start_line,
        removed=snippet_lines,
        added=new_lines,
    )]'''

if old_fb in src:
    src = src.replace(old_fb, new_fb, 1)
    changes += 1
    print("[OK] Fix 3b: guard indent no fallback")
elif "lost_method_indent" in src:
    print("[i] Fix 3b: já aplicado")
else:
    print("[X] Fix 3b: bloco ok_block_format não encontrado")

# ── Única escrita ──
if changes > 0:
    p.write_text(src, encoding="utf-8")
    print(f"\n[i] {changes} mudança(s) escritas em {p}")
else:
    print("\n[i] nada a escrever")
