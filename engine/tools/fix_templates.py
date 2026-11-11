# -*- coding: utf-8 -*-
"""Templates determinísticos para `orn fix --symbol`.

Fase 5.6 — antes do modelo, tenta transformação via AST/string.
Se bate, evita 100% da inferência (rápido e determinístico).

God: Thoth (linguagem e lógica).
"""
from __future__ import annotations

import ast
import re
import textwrap
import unicodedata
from dataclasses import dataclass


@dataclass
class TemplateMatch:
    name: str
    new_code: str
    description: str


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )


def _reindent(code: str, indent_str: str) -> str:
    if not indent_str:
        return code
    return "\n".join(
        (indent_str + ln if ln.strip() else ln)
        for ln in code.splitlines()
    )


def _common_indent(snippet: str) -> str:
    first = next((ln for ln in snippet.splitlines() if ln.strip()), "")
    return " " * (len(first) - len(first.lstrip()))


# ──────────────────────────────────────────────────────────
# Template 1: docstring
# ──────────────────────────────────────────────────────────
def _gen_docstring(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
        lines = [f'"""{node.name}.']
        if args:
            lines.append("")
            lines.append("Args:")
            for a in args:
                lines.append(f"    {a}: descrição.")
        if node.returns is not None:
            lines.append("")
            lines.append("Returns:")
            lines.append("    descrição.")
        lines.append('"""')
        return "\n".join(lines)
    if isinstance(node, ast.ClassDef):
        return f'"""{node.name}."""'
    return '""""""'


def _template_docstring(
    snippet: str, symbol_name: str, symbol_kind: str,
) -> TemplateMatch | None:
    dedented = textwrap.dedent(snippet)
    try:
        tree = ast.parse(dedented)
    except SyntaxError:
        return None
    if not tree.body:
        return None
    node = tree.body[0]
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return None
    if ast.get_docstring(node):
        return None

    doc = _gen_docstring(node)
    lines = dedented.splitlines()
    body_start = node.body[0].lineno - 1 if node.body else node.lineno
    base_indent = " " * (node.col_offset + 4)
    doc_lines = [
        f"{base_indent}{ln}" if ln else ""
        for ln in doc.splitlines()
    ]
    new_lines = lines[:body_start] + doc_lines + lines[body_start:]
    new_code = "\n".join(new_lines)

    indent = _common_indent(snippet)
    if indent:
        new_code = _reindent(new_code, indent)

    try:
        ast.parse(textwrap.dedent(new_code))
    except SyntaxError:
        return None

    return TemplateMatch(
        name="docstring",
        new_code=new_code,
        description=f"docstring adicionado em {symbol_name}",
    )


# ──────────────────────────────────────────────────────────
# Template 2: comentário no topo
# ──────────────────────────────────────────────────────────
def _extract_comment_text(
    instruction: str, snippet: str, symbol_name: str,
) -> str:
    # 1. Texto entre aspas na instrução
    m = re.search(r"['\"]([^'\"]+)['\"]", instruction)
    if m:
        return m.group(1).strip()
    # 2. Primeira linha da docstring existente
    try:
        tree = ast.parse(textwrap.dedent(snippet))
        if tree.body and isinstance(
            tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            doc = ast.get_docstring(tree.body[0])
            if doc:
                first = doc.strip().splitlines()[0]
                if len(first) > 60:
                    first = first[:57] + "..."
                return first
    except SyntaxError:
        pass
    # 3. Fallback
    return f"TODO: revisar {symbol_name}"


def _template_top_comment(
    snippet: str, symbol_name: str, instruction: str,
) -> TemplateMatch | None:
    lines = snippet.splitlines()
    if not lines:
        return None

    first_idx = 0
    while first_idx < len(lines) and not lines[first_idx].strip():
        first_idx += 1
    if first_idx >= len(lines):
        return None

    first = lines[first_idx]
    indent = " " * (len(first) - len(first.lstrip()))
    text = _extract_comment_text(instruction, snippet, symbol_name)
    comment = f"{indent}# {text}"

    if any(comment.strip() in ln for ln in lines[: first_idx + 3]):
        return None

    new_lines = lines[:first_idx] + [comment] + lines[first_idx:]
    new_code = "\n".join(new_lines)

    try:
        ast.parse(textwrap.dedent(new_code))
    except SyntaxError:
        return None

    return TemplateMatch(
        name="top_comment",
        new_code=new_code,
        description=f"comentário adicionado acima de {symbol_name}",
    )


# ──────────────────────────────────────────────────────────
# Template 3: rename (string-based, preserva format)
# ──────────────────────────────────────────────────────────
_RENAME_RE = re.compile(
    r"(?:renomei[ae]|rename|renomear)"
    r"(?:\s+(?:a|o|função|funcao|método|metodo|classe|class|def))?"
    r"\s+['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?"
    r"\s+(?:para|pra|to)"
    r"\s+['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?",
    re.IGNORECASE,
)


def _template_rename(
    snippet: str, symbol_name: str, instruction: str,
) -> TemplateMatch | None:
    m = _RENAME_RE.search(_strip_accents(instruction))
    if not m:
        return None
    old_name, new_name = m.group(1), m.group(2)
    if old_name == new_name:
        return None

    word_re = re.compile(rf"\b{re.escape(old_name)}\b")
    new_lines = []
    changed = False
    for line in snippet.splitlines():
        new_line = word_re.sub(new_name, line)
        if new_line != line:
            changed = True
        new_lines.append(new_line)

    if not changed:
        return None

    new_code = "\n".join(new_lines)
    try:
        ast.parse(textwrap.dedent(new_code))
    except SyntaxError:
        return None

    return TemplateMatch(
        name="rename",
        new_code=new_code,
        description=f"renomeado {old_name} → {new_name}",
    )


# ──────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────
def apply_template(
    instruction: str,
    snippet: str,
    symbol_name: str,
    symbol_kind: str,
    start_line: int,
) -> TemplateMatch | None:
    """Tenta transformação determinística. None se não bater."""
    if not instruction or not snippet:
        return None

    low = _strip_accents(instruction.lower())

    # Docstring
    if ("docstring" in low or "document" in low) and any(
        kw in low for kw in (
            "adicione", "adicionar", "crie", "criar",
            "insira", "inclua", "coloque",
        )
    ):
        match = _template_docstring(snippet, symbol_name, symbol_kind)
        if match:
            return match

    # Comentário no topo
    if "comentario" in low or "comment" in low:
        if any(kw in low for kw in (
            "topo", "inicio", "cima", "acima", "antes",
        )):
            match = _template_top_comment(
                snippet, symbol_name, instruction,
            )
            if match:
                return match

    # Rename
    if "renome" in low or "rename" in low:
        match = _template_rename(snippet, symbol_name, instruction)
        if match:
            return match

    return None


# ──────────────────────────────────────────────────────────
# Testes
# ──────────────────────────────────────────────────────────
_NO_DOC = '''def _fmt_ms(value: float) -> str:
    if value >= 1000:
        return f"{value / 1000.0:.3f}s"
    return f"{value:.3f}ms"
'''

_WITH_DOC = '''def _fmt_ms(value: float) -> str:
    """Formata ms."""
    if value >= 1000:
        return f"{value / 1000.0:.3f}s"
    return f"{value:.3f}ms"
'''

_METHOD = '''    def foo(self):
        return self.x
'''


def _run_tests() -> int:
    passed = failed = 0

    def check(name, cond, detail=""):
        nonlocal passed, failed
        if cond:
            print(f"  [OK] {name}")
            passed += 1
        else:
            print(f"  [X]  {name}" + (f" — {detail}" if detail else ""))
            failed += 1

    # Docstring
    m = apply_template(
        "adicione docstring na função _fmt_ms",
        _NO_DOC, "_fmt_ms", "function", 55,
    )
    check("docstring: bate", m is not None and m.name == "docstring")
    if m:
        try:
            ast.parse(m.new_code)
            check("docstring: sintaxe válida", True)
        except SyntaxError:
            check("docstring: sintaxe válida", False)
        check("docstring: contém Args", "Args:" in m.new_code)

    # Docstring: já tem
    m = apply_template(
        "adicione docstring", _WITH_DOC, "_fmt_ms", "function", 55,
    )
    check("docstring: já tem → None", m is None)

    # Top comment
    m = apply_template(
        "adicione comentário no topo",
        _NO_DOC, "_fmt_ms", "function", 55,
    )
    check("top_comment: bate", m is not None and m.name == "top_comment")
    if m:
        check("top_comment: contém #", "#" in m.new_code)
        try:
            ast.parse(m.new_code)
            check("top_comment: sintaxe válida", True)
        except SyntaxError:
            check("top_comment: sintaxe válida", False)

    # Top comment: usa docstring existente
    m = apply_template(
        "adicione comentário no topo",
        _WITH_DOC, "_fmt_ms", "function", 55,
    )
    check("top_comment: usa docstring", m is not None and "Formata ms" in m.new_code)

    # Top comment: method indentado
    m = apply_template(
        "adicione comentário no topo",
        _METHOD, "foo", "method", 10,
    )
    check("method: bate", m is not None)
    if m:
        check("method: preserva indent", "    # " in m.new_code)
        try:
            ast.parse(textwrap.dedent(m.new_code))
            check("method: sintaxe válida", True)
        except SyntaxError:
            check("method: sintaxe válida", False)

    # Rename
    m = apply_template(
        "renomeie _fmt_ms para _format_ms",
        _NO_DOC, "_fmt_ms", "function", 55,
    )
    check("rename: bate", m is not None and m.name == "rename")
    if m:
        check("rename: novo nome no def", "def _format_ms" in m.new_code)
        check("rename: old name sumiu", "def _fmt_ms" not in m.new_code)
        check("rename: preserva formatting",
              '"{value / 1000.0:.3f}s"' in m.new_code)

    # Rename: não casa palavra parcial
    fixture_partial = '''def _fmt_ms(value):
    _fmt_ms_extra = value
    return _fmt_ms
'''
    m = apply_template(
        "renomeie _fmt_ms para _format_ms",
        fixture_partial, "_fmt_ms", "function", 1,
    )
    if m:
        check("rename: word boundary",
              "_fmt_ms_extra" in m.new_code)  # intacto
        check("rename: chamada renomeada",
              "return _format_ms" in m.new_code)

    # Vago → None
    m = apply_template(
        "melhore essa função", _NO_DOC, "_fmt_ms", "function", 55,
    )
    check("vago: None", m is None)

    print()
    if failed == 0:
        print(f"  {passed} teste(s) OK")
        return 0
    print(f"  {passed}/{passed+failed} passaram — {failed} falha(s)")
    return 1


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_run_tests())
    print("Uso: python -m engine.tools.fix_templates --test")
