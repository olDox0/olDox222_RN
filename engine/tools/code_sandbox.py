# -*- coding: utf-8 -*-
"""Sandbox local para staging e diagnóstico de código (stdlib only)."""

from __future__ import annotations

import ast
import hashlib
import time
from pathlib import Path


def safe_codegen_dir() -> Path:
    root = Path(".orn") / "sandbox_codegen"
    root.mkdir(parents=True, exist_ok=True)
    return root


def stage_code(code: str, stem: str = "candidate") -> Path:
    digest = hashlib.sha1(code.encode("utf-8", errors="ignore")).hexdigest()[:10]
    ts = int(time.time() * 1000)
    path = safe_codegen_dir() / f"{stem}_{ts}_{digest}.py"
    path.write_text(code, encoding="utf-8")
    return path


def lint_python_text(text: str) -> list[str]:
    issues: list[str] = []
    for ln, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw:
            issues.append(f"L{ln}: evitar TAB; use espaços.")
        if raw.rstrip() != raw:
            issues.append(f"L{ln}: trailing whitespace.")
        if len(raw) > 120:
            issues.append(f"L{ln}: linha acima de 120 chars ({len(raw)}).")

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        issues.append(f"L{exc.lineno}: SyntaxError: {exc.msg}")
        return issues

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append(f"L{node.lineno}: bare except detectado.")
        if isinstance(node, ast.ImportFrom) and any(n.name == "*" for n in node.names):
            issues.append(f"L{node.lineno}: import * não permitido.")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            issues.append(f"L{node.lineno}: uso de {node.func.id} não permitido.")

    return issues


def diagnose_python_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return lint_python_text(text)
