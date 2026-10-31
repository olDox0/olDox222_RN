# -*- coding: utf-8 -*-
# engine/tools/diff_engine.py
"""
Diff engine — edições cirúrgicas.
Usa Few-Shot (exemplo) para forçar o Qwen a copiar o formato @N.
"""

from __future__ import annotations

import os
import time
import re
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class DiffHunk:
    line: int
    removed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)

@dataclass
class DiffResult:
    success: bool
    raw_output: str = ""
    hunks: list[DiffHunk] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0
    applied: bool = False

def build_prompt(file_content: str, instruction: str) -> str:
    """Prompt com exemplo explícito (Few-Shot) para o Qwen 0.5B copiar."""
    system = (
        "Você é um assistente de edição de código. Responda em português. "
        "Use o formato @N seguido de linhas com - (antigo) e + (novo).\n"
        "Exemplo:\n"
        "@1\n"
        "- def soma(a, b): return a + b\n"
        "+ def soma(a, b): return a - b"
    )
    return (
        f"<|im_start|>system\n{system}<|im_end|>\n"
        f"<|im_start|>user\nCódigo:\n```python\n{file_content.strip()}\n```\n\n"
        f"Tarefa: {instruction}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

def parse_diff(text: str) -> list[DiffHunk]:
    hunks: list[DiffHunk] = []
    current: DiffHunk | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if line.startswith("@"):
            try:
                n = int(line[1:].strip().split()[0])
            except (ValueError, IndexError):
                continue
            if current is not None and (current.removed or current.added):
                hunks.append(current)
            current = DiffHunk(line=n)
        elif line.startswith("- ") and current is not None:
            current.removed.append(line[2:])
        elif line.startswith("+ ") and current is not None:
            current.added.append(line[2:])
    if current is not None and (current.removed or current.added):
        hunks.append(current)
    return hunks

def apply_hunks(lines: list[str], hunks: list[DiffHunk]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    for hunk in sorted(hunks, key=lambda h: h.line, reverse=True):
        idx = hunk.line - 1
        if idx < 0 or idx >= len(lines):
            errors.append(f"@{hunk.line}: fora do arquivo")
            continue
        n_removed = len(hunk.removed)
        if n_removed > 0 and not hunk.added:
            lines = lines[:idx] + hunk.removed + lines[idx + n_removed:]
            continue
        actual = lines[idx:idx + n_removed] if n_removed > 0 else []
        if n_removed > 0 and [l.rstrip() for l in actual] != [l.rstrip() for l in hunk.removed]:
            errors.append(f"@{hunk.line}: conteúdo não bate")
            continue
        lines = lines[:idx] + hunk.added + lines[idx + n_removed:]
    return lines, errors

def _line_ending(content: str) -> tuple[str, bool]:
    has_trailing = content.endswith(("\n", "\r\n"))
    return ("\r\n" if "\r\n" in content else "\n"), has_trailing

def generate_and_apply(
    file_path: Path | str,
    instruction: str,
    *,
    apply: bool = False,
    verify: bool = False,
    max_tokens: int = 128,
    temperature: float = 0.2, # <-- Assinatura corrigida aqui
    model_alias: str | None = None,
) -> DiffResult:
    t0 = time.monotonic()
    path = Path(file_path)

    if not path.exists():
        return DiffResult(success=False, errors=[f"arquivo não existe: {path}"])

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return DiffResult(success=False, errors=[f"leitura falhou: {exc}"])

    if model_alias:
        os.environ["ORN_MODEL_ALIAS"] = model_alias
    from engine.core.llm_bridge import BridgeConfig, SiCDoxBridge

    bridge = SiCDoxBridge(BridgeConfig()) 
    try:
        bridge._ensure_loaded()
        prompt = build_prompt(content, instruction)
        
        resp = bridge._llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=0.8,
            top_k=25,
            repeat_penalty=1.15,
            min_p=0.05,
            stop=["<|im_end|>"],  # <-- REMOVIDO \n\n e ```
            echo=False,
        )
        raw = str(resp["choices"][0]["text"]).strip()
        
        if "```" in raw:
            match = re.search(r"```(?:python)?\n?(.*?)```", raw, re.DOTALL)
            if match: raw = match.group(1).strip()
            else: raw = raw.split("```")[0].strip()

    except Exception as exc:
        return DiffResult(success=False, errors=[f"inferência falhou: {exc}"], elapsed_s=round(time.monotonic() - t0, 2))
    finally:
        try: bridge.shutdown()
        except Exception: pass

    hunks = parse_diff(raw)
    
    if not hunks:
        return DiffResult(
            success=False, 
            raw_output=f"DEBUG REPR:\n{repr(raw)}",
            errors=["Modelo não gerou um @N válido."],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    line_ending, has_trailing = _line_ending(content)
    lines = content.splitlines()
    new_lines, errors = apply_hunks(lines, hunks)

    applied = False
    if apply and not errors and new_lines != lines:
        new_content = line_ending.join(new_lines)
        if has_trailing: new_content += line_ending
        
        try:
            backup_content = path.read_text(encoding="utf-8", errors="replace")
            path.write_text(new_content, encoding="utf-8")
            applied = True
            
            if verify:
                from engine.tools.sandbox import run_in_sandbox
                sb_res = run_in_sandbox(new_content, timeout_s=5)
                if not sb_res.success:
                    errors.append(f"Sandbox falhou: {sb_res.stderr.strip()}")
                    path.write_text(backup_content, encoding="utf-8")
                    applied = False
                    errors.append("Rollback executado: arquivo original restaurado.")
                    
        except OSError as exc:
            errors.append(f"escrita falhou: {exc}")

    return DiffResult(
        success=not errors,
        raw_output=raw,
        hunks=hunks,
        errors=errors,
        elapsed_s=round(time.monotonic() - t0, 2),
        applied=applied,
    )
