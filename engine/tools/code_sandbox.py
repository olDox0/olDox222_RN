# -*- coding: utf-8 -*-
"""Sandbox local para staging e diagnóstico de código (stdlib only)."""

from __future__ import annotations

import ast
import builtins
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
        if isinstance(node, ast.ExceptHandler) and isinstance(node.type, ast.Name) and node.type.id == "Exception":
            issues.append(f"L{node.lineno}: except Exception genérico; prefira exceções específicas.")
        if isinstance(node, ast.ImportFrom) and any(n.name == "*" for n in node.names):
            issues.append(f"L{node.lineno}: import * não permitido.")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            issues.append(f"L{node.lineno}: uso de {node.func.id} não permitido.")
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            if isinstance(node.right, ast.Constant) and node.right.value == 0:
                issues.append(f"L{node.lineno}: possível divisão/módulo por zero.")

    issues.extend(_detect_incomplete_blocks(tree))
    issues.extend(_detect_mutable_defaults(tree))
    issues.extend(_detect_probable_undefined_names(tree))

    return issues


def _detect_incomplete_blocks(tree: ast.AST) -> list[str]:
    issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = [stmt for stmt in node.body if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Constant) or not isinstance(stmt.value.value, str)]
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                issues.append(f"L{node.lineno}: função '{node.name}' está incompleta (apenas pass).")
        if isinstance(node, ast.ClassDef):
            body = [stmt for stmt in node.body if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Constant) or not isinstance(stmt.value.value, str)]
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                issues.append(f"L{node.lineno}: classe '{node.name}' está incompleta (apenas pass).")
    return issues


def _detect_mutable_defaults(tree: ast.AST) -> list[str]:
    issues: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for default in node.args.defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                issues.append(f"L{default.lineno}: argumento com default mutável em '{node.name}'.")
        for default in node.args.kw_defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                issues.append(f"L{default.lineno}: kw-default mutável em '{node.name}'.")
    return issues


def _detect_probable_undefined_names(tree: ast.AST) -> list[str]:
    """Heurística simples para detectar nomes usados sem definição local/import."""
    builtins_set = set(dir(builtins))
    declared: set[str] = set()
    used: dict[str, int] = {}

    class _Visitor(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                declared.add(alias.asname or alias.name.split(".")[0])
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            for alias in node.names:
                if alias.name == "*":
                    continue
                declared.add(alias.asname or alias.name)
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            declared.add(node.name)
            for arg in [*node.args.args, *node.args.kwonlyargs]:
                declared.add(arg.arg)
            if node.args.vararg:
                declared.add(node.args.vararg.arg)
            if node.args.kwarg:
                declared.add(node.args.kwarg.arg)
            self.generic_visit(node)

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            declared.add(node.name)
            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign) -> None:
            for t in node.targets:
                for name in _extract_assigned_names(t):
                    declared.add(name)
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            for name in _extract_assigned_names(node.target):
                declared.add(name)
            self.generic_visit(node)

        def visit_For(self, node: ast.For) -> None:
            for name in _extract_assigned_names(node.target):
                declared.add(name)
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, ast.Load):
                used.setdefault(node.id, node.lineno)
            self.generic_visit(node)

    _Visitor().visit(tree)

    issues: list[str] = []
    skip_names = {"self", "cls", "__name__"}
    for name, lineno in used.items():
        if name in declared or name in builtins_set or name in skip_names:
            continue
        issues.append(f"L{lineno}: nome possivelmente indefinido: '{name}'.")
        if len(issues) >= 8:
            break
    return issues


def _extract_assigned_names(target: ast.AST) -> list[str]:
    names: list[str] = []
    if isinstance(target, ast.Name):
        names.append(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            names.extend(_extract_assigned_names(elt))
    return names


def diagnose_python_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return lint_python_text(text)
