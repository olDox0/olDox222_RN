# -*- coding: utf-8 -*-
# engine/tools/code_mutator.py
"""
Gerador de mutações programáticas a partir de código Python válido.

Cada mutação produz:
  - instruction_pt: instrução em português
  - line: número da linha alvo (1-based)
  - expected: linhas originais (o que existe)
  - new: linhas novas (o que deve ficar no lugar)
  - before_source: arquivo inteiro antes
  - after_source: arquivo inteiro depois

Nenhuma chamada LLM. Puro AST + manipulação de linha.

Mutações v1:
  add_to_sub       → a + b       vira  a - b
  sub_to_add       → a - b       vira  a + b
  flip_comparison  → a > b       vira  a <= b (e pares)
  remove_print     → apaga print(...) sozinho na linha
  change_int_const → x = 5       vira  x = 10

God: Demeter (pipeline) + Thoth (AST).
OSL-2:  cada mutação é O(n) no tamanho do arquivo.
OSL-15: arquivo malformado → lista vazia (nunca exceção).
OSL-17: só gera mutações. Não valida (validação é responsabilidade do
        diff_dataset via PatchSurgeon).
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("engine.tools.code_mutator")

# Skip arquivos maiores que isso (prompt do treino fica gigante)
MAX_FILE_LINES = 100

# Constante usada em change_int_const
_INT_DELTA = 5


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class Mutation:
    kind:          str
    instruction_pt: str
    line:          int          # 1-based, no arquivo inteiro
    expected:      list[str]
    new:           list[str]
    before_source: str          # arquivo inteiro antes
    after_source:  str          # arquivo inteiro depois


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _splitlines_keep_trailing(source: str) -> tuple[list[str], bool]:
    """Retorna (linhas_sem_quebra, tinha_newline_final)."""
    lines = source.splitlines()
    had_nl = source.endswith("\n")
    return lines, had_nl


def _rejoin_lines(lines: list[str], had_nl: bool) -> str:
    result = "\n".join(lines)
    if had_nl:
        result += "\n"
    return result


def _replace_line(source: str, line_idx_0based: int, new_line: str) -> str:
    """Retorna source com a linha substituída por new_line."""
    lines, had_nl = _splitlines_keep_trailing(source)
    if line_idx_0based < 0 or line_idx_0based >= len(lines):
        return source
    lines[line_idx_0based] = new_line
    return _rejoin_lines(lines, had_nl)


def _delete_line(source: str, line_idx_0based: int) -> str:
    """Retorna source sem a linha (0-based)."""
    lines, had_nl = _splitlines_keep_trailing(source)
    if line_idx_0based < 0 or line_idx_0based >= len(lines):
        return source
    del lines[line_idx_0based]
    return _rejoin_lines(lines, had_nl)


def _find_op_segment(line: str, left_end: int, right_start: int) -> str | None:
    """Extrai o pedaço da linha entre operandos (contém o operador)."""
    if left_end is None or right_start is None:
        return None
    if left_end < 0 or right_start > len(line) or left_end >= right_start:
        return None
    return line[left_end:right_start]


# ---------------------------------------------------------------------------
# Mutações
# ---------------------------------------------------------------------------

def _mutate_binop(source: str, kind: str) -> list[Mutation]:
    """
    Troca Add <-> Sub em BinOp de UMA linha.

    kind: 'add_to_sub' ou 'sub_to_add'
    """
    lines, _ = _splitlines_keep_trailing(source)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    op_type = ast.Add if kind == "add_to_sub" else ast.Sub
    old_sym = "+" if kind == "add_to_sub" else "-"
    new_sym = "-" if kind == "add_to_sub" else "+"

    out: list[Mutation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp):
            continue
        if not isinstance(node.op, op_type):
            continue
        if getattr(node, "lineno", None) != getattr(node, "end_lineno", None):
            continue
        if not (hasattr(node.left, "end_col_offset")
                and hasattr(node.right, "col_offset")):
            continue

        line_idx = node.lineno - 1
        if line_idx < 0 or line_idx >= len(lines):
            continue

        old_line = lines[line_idx]
        segment = _find_op_segment(old_line, node.left.end_col_offset, node.right.col_offset)
        if segment is None or old_sym not in segment:
            continue

        new_segment = segment.replace(old_sym, new_sym, 1)
        new_line = old_line[:node.left.end_col_offset] + new_segment + old_line[node.right.col_offset:]
        if new_line == old_line:
            continue

        after = _replace_line(source, line_idx, new_line)

        verb = "Troque o operador + por -" if kind == "add_to_sub" else "Troque o operador - por +"
        out.append(Mutation(
            kind=kind,
            instruction_pt=f"{verb} na linha {node.lineno}.",
            line=node.lineno,
            expected=[old_line],
            new=[new_line],
            before_source=source,
            after_source=after,
        ))
    return out


_COMPARISON_FLIP: dict[type, tuple[str, str]] = {
    ast.Eq:    ("==", "!="),
    ast.NotEq: ("!=", "=="),
    ast.Lt:    ("<", ">="),
    ast.LtE:   ("<=", ">"),
    ast.Gt:    (">", "<="),
    ast.GtE:   (">=", "<"),
}


def _mutate_flip_comparison(source: str) -> list[Mutation]:
    lines, _ = _splitlines_keep_trailing(source)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    out: list[Mutation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if getattr(node, "lineno", None) != getattr(node, "end_lineno", None):
            continue
        if len(node.ops) != 1 or len(node.comparators) != 1:
            continue
        op = node.ops[0]
        if type(op) not in _COMPARISON_FLIP:
            continue
        old_sym, new_sym = _COMPARISON_FLIP[type(op)]
        if not (hasattr(node.left, "end_col_offset")
                and hasattr(node.comparators[0], "col_offset")):
            continue

        line_idx = node.lineno - 1
        if line_idx < 0 or line_idx >= len(lines):
            continue

        old_line = lines[line_idx]
        segment = _find_op_segment(
            old_line, node.left.end_col_offset, node.comparators[0].col_offset
        )
        if segment is None or old_sym not in segment:
            continue

        new_segment = segment.replace(old_sym, new_sym, 1)
        new_line = old_line[:node.left.end_col_offset] + new_segment + old_line[node.comparators[0].col_offset:]
        if new_line == old_line:
            continue

        after = _replace_line(source, line_idx, new_line)
        out.append(Mutation(
            kind="flip_comparison",
            instruction_pt=(
                f"Inverta a comparação '{old_sym}' para '{new_sym}' "
                f"na linha {node.lineno}."
            ),
            line=node.lineno,
            expected=[old_line],
            new=[new_line],
            before_source=source,
            after_source=after,
        ))
    return out


def _mutate_remove_print(source: str) -> list[Mutation]:
    lines, _ = _splitlines_keep_trailing(source)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    out: list[Mutation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        is_print = (
            (isinstance(func, ast.Name) and func.id == "print")
            or (isinstance(func, ast.Attribute) and func.attr == "print")
        )
        if not is_print:
            continue
        if getattr(node, "lineno", None) != getattr(node, "end_lineno", None):
            continue

        line_idx = node.lineno - 1
        if line_idx < 0 or line_idx >= len(lines):
            continue
        old_line = lines[line_idx]
        if not old_line.strip().startswith(("print(", "print (")):
            # Não é o começo da linha (ex: `x = print(...)`); não removemos
            continue

        after = _delete_line(source, line_idx)
        out.append(Mutation(
            kind="remove_print",
            instruction_pt=f"Remova o print de debug na linha {node.lineno}.",
            line=node.lineno,
            expected=[old_line],
            new=[],
            before_source=source,
            after_source=after,
        ))
    return out


def _mutate_change_int_const(source: str) -> list[Mutation]:
    lines, _ = _splitlines_keep_trailing(source)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    out: list[Mutation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if getattr(node, "lineno", None) != getattr(node, "end_lineno", None):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        if not (isinstance(value, ast.Constant) and isinstance(value.value, int)
                and not isinstance(value.value, bool)):
            continue

        old_val = value.value
        new_val = old_val + _INT_DELTA
        if new_val == old_val:
            continue

        line_idx = node.lineno - 1
        if line_idx < 0 or line_idx >= len(lines):
            continue
        old_line = lines[line_idx]

        # Substituição literal: o valor deve aparecer como token isolado
        # (cuidado pra não substituir dentro de strings ou nomes)
        # Estratégia conservadora: usar col_offset do Constant
        if not hasattr(value, "col_offset") or not hasattr(value, "end_col_offset"):
            continue
        old_str = str(old_val)
        if old_line[value.col_offset:value.end_col_offset] != old_str:
            continue  # não bate exato (ex: 0x05), pula

        new_line = (
            old_line[:value.col_offset]
            + str(new_val)
            + old_line[value.end_col_offset:]
        )
        if new_line == old_line:
            continue

        after = _replace_line(source, line_idx, new_line)
        out.append(Mutation(
            kind="change_int_const",
            instruction_pt=(
                f"Mude o valor de {target.id} de {old_val} para {new_val} "
                f"na linha {node.lineno}."
            ),
            line=node.lineno,
            expected=[old_line],
            new=[new_line],
            before_source=source,
            after_source=after,
        ))
    return out


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def mutate_source(source: str) -> list[Mutation]:
    """
    Aplica todas as mutações possíveis. Retorna lista (pode ser vazia).

    Filtros aplicados:
      - Arquivo compila antes da mutação.
      - Cada mutação produz código que compila após.
      - Arquivo não tem mais de MAX_FILE_LINES linhas.
    """
    if not source or not source.strip():
        return []

    lines = source.splitlines()
    if len(lines) > MAX_FILE_LINES:
        return []

    try:
        compile(source, "<source>", "exec")
    except SyntaxError:
        return []

    all_mutations: list[Mutation] = []
    all_mutations.extend(_mutate_binop(source, "add_to_sub"))
    all_mutations.extend(_mutate_binop(source, "sub_to_add"))
    all_mutations.extend(_mutate_flip_comparison(source))
    all_mutations.extend(_mutate_remove_print(source))
    all_mutations.extend(_mutate_change_int_const(source))

    # Filtro final: after compila
    valid: list[Mutation] = []
    for m in all_mutations:
        try:
            compile(m.after_source, "<after>", "exec")
        except SyntaxError:
            continue
        valid.append(m)
    return valid
