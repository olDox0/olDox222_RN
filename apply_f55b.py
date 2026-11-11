# -*- coding: utf-8 -*-
"""Aplica F5.5b — propaga surgical_trace até o CLI. Robusto contra whitespace."""
from pathlib import Path
import sys

def patch_file(path_str: str, patches: list[tuple[str, str, str]]) -> None:
    p = Path(path_str)
    src = p.read_text(encoding="utf-8")
    ok = 0
    fail = 0
    for name, old, new in patches:
        if old not in src:
            print(f"  [X] {name}: old não encontrado")
            fail += 1
            continue
        src = src.replace(old, new, 1)
        ok += 1
        print(f"  [OK] {name}")
    if ok > 0:
        p.write_text(src, encoding="utf-8")
    return ok, fail

# ══════════════════════════════════════════════════════════════
# 1. diff_engine.py — DiffResult ganha campo
# ══════════════════════════════════════════════════════════════
diff_engine_patches = [
    (
        "DiffResult.surgical_trace",
        '    no_op: bool = False\n',
        '    no_op: bool = False\n    surgical_trace: dict | None = None\n',
    ),
]

# ══════════════════════════════════════════════════════════════
# 2. executive.py — propaga trace no metadata (falha)
# ══════════════════════════════════════════════════════════════
exec_fail_patch = (
    "executive._run_fix falha com trace",
    '''                metadata={
                    "elapsed_s":  diff_res.elapsed_s,
                    "applied":    diff_res.applied,
                    "raw_output": diff_res.raw_output,
                    "symbol_mode": symbol_mode,
                },
            )''',
    '''                metadata={
                    "elapsed_s":      diff_res.elapsed_s,
                    "applied":        diff_res.applied,
                    "raw_output":     diff_res.raw_output,
                    "symbol_mode":    symbol_mode,
                    "surgical_trace": diff_res.surgical_trace,
                },
            )''',
)
exec_ok_patch = (
    "executive._run_fix sucesso com trace",
    '''                "surgical_hunks": surgical_hunks_payload,   # ← NOVO
            },''',
    '''                "surgical_hunks": surgical_hunks_payload,
                "surgical_trace": diff_res.surgical_trace,
            },''',
)

# ══════════════════════════════════════════════════════════════
# 3. cli.py — _print_surgical_trace + chamada
# ══════════════════════════════════════════════════════════════
# Descobrir se _print_surgical_trace já existe
cli_src = Path("engine/cli.py").read_text(encoding="utf-8")
if "_print_surgical_trace" in cli_src:
    print("  [i] _print_surgical_trace já existe em cli.py, pulando def")
    cli_def_patch = None
else:
    cli_def_patch = (
        "cli.py define _print_surgical_trace",
        'def fix(target, instruction, apply, dry_run, consult, verbose,\n',
        '''def _print_surgical_trace(trace: dict) -> None:
    Display.separator()
    Display.info("[surgical] trace:")
    Display.kv("  outcome",         str(trace.get("outcome", "?")))
    Display.kv("  instruction",     str(trace.get("instruction", ""))[:70])
    Display.kv("  matches_count",   str(trace.get("matches_count", 0)))
    resolved = trace.get("resolved")
    if resolved:
        rfile = trace.get("resolved_file", "?")
        rlines = trace.get("resolved_lines")
        line_str = f"L{rlines[0]}-{rlines[1]}" if rlines else "?"
        Display.kv("  resolved", f"{resolved} ({rfile}:{line_str})")
        Display.kv("  lines_count", str(trace.get("resolved_lines_count", "?")))
    if trace.get("surgical_max_tokens"):
        Display.kv("  max_tokens", str(trace["surgical_max_tokens"]))
    if trace.get("prompt_chars"):
        Display.kv("  prompt_chars", str(trace["prompt_chars"]))
    if trace.get("infer_error"):
        Display.kv("  infer_error", str(trace["infer_error"])[:120])
    if trace.get("syntax_error"):
        Display.kv("  syntax_error", str(trace["syntax_error"])[:120])
    if "output_ratio" in trace:
        Display.kv("  output_ratio", f"{trace['output_ratio']:.1%}")
    Display.kv("  raw_len", str(trace.get("infer_raw_len", 0)))
    preview = trace.get("infer_raw_preview") or ""
    if preview:
        Display.info("  raw (primeiros 800 chars):")
        for line in preview.splitlines()[:40]:
            print(f"    {line}")
        if len(trace.get("infer_raw_preview", "")) >= 800:
            print("    [...truncado]")
    Display.separator()


def fix(target, instruction, apply, dry_run, consult, verbose,\n''',
    )

cli_call_patch = (
    "cli.py chama _print_surgical_trace",
    '''        if not verbose and "raw_output do modelo" in err:
                continue
            for line in err.splitlines():
                Display.error(line)
        raise SystemExit(1)''',
    '''        if not verbose and "raw_output do modelo" in err:
                continue
            for line in err.splitlines():
                Display.error(line)
        if verbose and result.metadata.get("surgical_trace"):
            _print_surgical_trace(result.metadata["surgical_trace"])
        raise SystemExit(1)''',
)

# ══════════════════════════════════════════════════════════════
# Executa
# ══════════════════════════════════════════════════════════════
print("\n[diff_engine.py]")
patch_file("engine/tools/diff_engine.py", diff_engine_patches)

print("\n[executive.py]")
patch_file("engine/core/executive.py", [exec_fail_patch, exec_ok_patch])

print("\n[cli.py]")
cli_patches = [cli_call_patch]
if cli_def_patch:
    cli_patches.insert(0, cli_def_patch)
patch_file("engine/cli.py", cli_patches)

print("\n[ok] feito. Rode: python -m py_compile engine/tools/diff_engine.py engine/core/executive.py engine/cli.py")