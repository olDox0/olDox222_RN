# -*- coding: utf-8 -*-
# engine/diff/format.py
"""
Parser e formatter de hunks para o ORN Diff Engine.

Formatos suportados:

  1) LINE-HUNK (primário, treinado no LLM):
       @3
       - return a - b
       + return a + b

     - `@N` marca o hunk na linha N (1-based).
     - `-` = conteúdo esperado (âncora de verificação).
     - `+` = conteúdo novo (substituição).
     - Pure remove (só `-`) e pure add (só `+`) são suportados.
     - Blank line entre hunks é separador.

  2) SEARCH/REPLACE (fallback, doxoade/git-diff compatibility):
       [SEARCH]
       <linhas exatas>
       [REPLACE]
       <linhas novas>
       [END]

Regras de robustez (OSL-15):
  - Nunca levanta exceção em formato malformado.
  - Blocos inválidos são descartados com log, resto segue.
  - parse_any_hunks() prefere LINE-HUNK; SEARCH/REPLACE só se zero
    line-hunks foram encontrados (evita ambiguidade).

God: Thoth (parsing) + Anúbis (validação).
OSL-17: só parse/format/validate. Aplicar é responsabilidade de surgeon.py.

Uso:
    python -m engine.diff.format --test       # roda suite de testes
    python -m engine.diff.format --demo       # demo com exemplo fixo
    echo "<texto>" | python -m engine.diff.format
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Union

logger = logging.getLogger("engine.diff.format")

# --- marcadores SEARCH/REPLACE ---
_MARK_SEARCH  = "[SEARCH]"
_MARK_REPLACE = "[REPLACE]"
_MARK_END     = "[END]"
_MIN_SEARCH_LEN = 5

# --- marcadores line-hunk ---
_RE_LINE_MARK = re.compile(r"^\s*@(\d+)\s*$")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SearchReplaceBlock:
    """Bloco SEARCH/REPLACE (formato fallback)."""
    search:  str
    replace: str

    def is_noop(self) -> bool:
        return self.search == self.replace

    def is_empty(self) -> bool:
        return not self.search.strip()


@dataclass
class LineHunk:
    """
    Hunk baseado em número de linha (formato primário).

    line     : 1-based. `@3` → line=3.
    expected : linhas `-` (âncora). Pode ser vazio (pure add).
    new      : linhas `+` (substituição). Pode ser vazio (pure remove).

    Invariante: expected OU new deve ser não vazio (validate garante).
    """
    line:     int = 0
    expected: list[str] = field(default_factory=list)
    new:      list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.expected and not self.new

    def is_pure_add(self) -> bool:
        return bool(self.new) and not self.expected

    def is_pure_remove(self) -> bool:
        return bool(self.expected) and not self.new


HunkLike = Union[SearchReplaceBlock, LineHunk]


# ---------------------------------------------------------------------------
# Helpers de prefixo
# ---------------------------------------------------------------------------

def _strip_prefix(line: str, prefix: str) -> str:
    """
    Remove prefixo e no máximo 1 espaço após ele.

    Preserva indentação além do primeiro espaço:
      "-     return"  → "    return"   (4 espaços preservados)
      "- hello"       → "hello"
      "-"             → ""
      "-  "           → " "
    """
    if not line.startswith(prefix):
        return line
    rest = line[len(prefix):]
    if rest.startswith(" "):
        rest = rest[1:]
    return rest


def _add_prefix(line: str, prefix: str) -> str:
    """
    Prefixa linha. Linha vazia → só prefixo (sem espaço).

      ""           → "-"
      "hello"      → "- hello"
      "    return" → "-     return"  (prefix + space + 4 spaces)
    """
    return f"{prefix} {line}" if line else prefix


# ---------------------------------------------------------------------------
# Parser SEARCH/REPLACE (fallback)
# ---------------------------------------------------------------------------

def parse_search_replace(text: str) -> list[SearchReplaceBlock]:
    """Extrai blocos SEARCH/REPLACE. Ignora texto solto e blocos malformados."""
    if not text:
        return []

    blocks: list[SearchReplaceBlock] = []
    lines = text.splitlines()
    n = len(lines)
    i = 0
    block_idx = 0

    while i < n:
        if lines[i].strip().upper() != _MARK_SEARCH:
            i += 1
            continue

        block_idx += 1

        # coleta search
        search_lines: list[str] = []
        i += 1
        found_replace = False
        while i < n:
            stripped = lines[i].strip().upper()
            if stripped == _MARK_REPLACE:
                found_replace = True
                i += 1
                break
            if stripped == _MARK_SEARCH:
                logger.debug("[SR #%d] [SEARCH] sem [REPLACE], descartado", block_idx)
                break
            search_lines.append(lines[i])
            i += 1
        if not found_replace:
            continue

        # coleta replace
        replace_lines: list[str] = []
        found_end = False
        while i < n:
            stripped = lines[i].strip().upper()
            if stripped == _MARK_END:
                found_end = True
                i += 1
                break
            if stripped in (_MARK_SEARCH, _MARK_REPLACE):
                logger.debug("[SR #%d] [REPLACE] sem [END], descartado", block_idx)
                break
            replace_lines.append(lines[i])
            i += 1
        if not found_end:
            continue

        search = "\n".join(search_lines)
        replace = "\n".join(replace_lines)

        if not search.strip():
            logger.debug("[SR #%d] search vazio, descartado", block_idx)
            continue

        blocks.append(SearchReplaceBlock(search=search, replace=replace))

    return blocks


# ---------------------------------------------------------------------------
# Parser LINE-HUNK (primário)
# ---------------------------------------------------------------------------

def parse_line_hunks(text: str) -> list[LineHunk]:
    """
    Extrai hunks @N do texto.

    Regras:
      - '@N' (com ou sem espaços ao redor) sozinho na linha.
      - Linhas começando com '-' → expected.
      - Linhas começando com '+' → new.
      - Linha vazia (após strip) encerra o hunk atual.
      - Próximo '@M' encerra e inicia outro.
      - Texto que não casa → encerra hunk e é ignorado.
      - Hunk sem nenhuma linha -/+ é descartado.

    O parser é tolerante: ignora linhas malformadas e segue adiante.
    """
    if not text:
        return []

    hunks: list[LineHunk] = []
    lines = text.splitlines()
    n = len(lines)
    i = 0
    hunk_idx = 0

    while i < n:
        line = lines[i]
        m = _RE_LINE_MARK.match(line)
        if not m:
            # linha começando com @ mas não casando formato → warning útil
            if line.lstrip().startswith("@") and not _RE_LINE_MARK.match(line):
                logger.debug("linha @N malformada ignorada: %r", line[:60])
            i += 1
            continue

        hunk_idx += 1
        try:
            line_no = int(m.group(1))
        except (ValueError, TypeError):
            logger.debug("[LH #%d] @N inválido, descartado", hunk_idx)
            i += 1
            continue

        if line_no < 1:
            logger.debug("[LH #%d] @%d < 1, descartado", hunk_idx, line_no)
            i += 1
            continue

        hunk = LineHunk(line=line_no)
        i += 1

        # coleta -/+
        while i < n:
            raw = lines[i]
            if not raw.strip():
                # linha em branco → separador
                break
            first = raw[0] if raw else ""
            if first == "-":
                hunk.expected.append(_strip_prefix(raw, "-"))
                i += 1
                continue
            if first == "+":
                hunk.new.append(_strip_prefix(raw, "+"))
                i += 1
                continue
            if _RE_LINE_MARK.match(raw):
                # próximo @N → encerra este, próximo itera
                break
            # linha não marcada → encerra
            break

        if hunk.is_empty():
            logger.debug("[LH #%d] @%d sem -/+, descartado", hunk_idx, line_no)
            continue

        hunks.append(hunk)

    return hunks


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def format_search_replace(block: SearchReplaceBlock) -> str:
    return (
        f"{_MARK_SEARCH}\n"
        f"{block.search}\n"
        f"{_MARK_REPLACE}\n"
        f"{block.replace}\n"
        f"{_MARK_END}"
    )


def format_line_hunk(h: LineHunk) -> str:
    parts = [f"@{h.line}"]
    for ln in h.expected:
        parts.append(_add_prefix(ln, "-"))
    for ln in h.new:
        parts.append(_add_prefix(ln, "+"))
    return "\n".join(parts)


def format_line_hunks(hunks: list[LineHunk]) -> str:
    if not hunks:
        return ""
    return "\n\n".join(format_line_hunk(h) for h in hunks)


def format_any_hunks(hunks: list[HunkLike]) -> str:
    if not hunks:
        return ""
    out: list[str] = []
    for h in hunks:
        if isinstance(h, LineHunk):
            out.append(format_line_hunk(h))
        else:
            out.append(format_search_replace(h))
    return "\n\n".join(out)


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------

def validate_block(block: SearchReplaceBlock) -> tuple[bool, str]:
    if block.is_empty():
        return False, "search vazio (match universal)"
    if len(block.search.strip()) < _MIN_SEARCH_LEN:
        return False, (
            f"search muito curto ({len(block.search.strip())} chars, "
            f"mínimo {_MIN_SEARCH_LEN})"
        )
    if block.is_noop():
        return False, "search == replace (patch não altera nada)"
    for marker in (_MARK_SEARCH, _MARK_REPLACE, _MARK_END):
        if marker in block.search or marker in block.replace:
            return False, f"marcador {marker} dentro do conteúdo"
    return True, ""


def validate_line_hunk(h: LineHunk) -> tuple[bool, str]:
    if h.line < 1:
        return False, f"line inválida: {h.line} (< 1)"
    if h.is_empty():
        return False, "hunk vazio (sem - e sem +)"
    if h.is_pure_remove():
        if not any(ln.strip() for ln in h.expected):
            return False, "pure remove com apenas linhas vazias (ambíguo)"
    # pure add: permitido, mas o caller deve usar preflight para desambiguar
    return True, ""


def validate_any_hunk(h: HunkLike) -> tuple[bool, str]:
    if isinstance(h, LineHunk):
        return validate_line_hunk(h)
    return validate_block(h)


# ---------------------------------------------------------------------------
# Parser unificado
# ---------------------------------------------------------------------------

def parse_any_hunks(text: str) -> list[HunkLike]:
    """
    Prefere LINE-HUNK. Só cai em SEARCH/REPLACE se zero @N foram achados.

    Não mistura formatos — evita ambiguidade quando o modelo confunde.
    """
    line_hunks = parse_line_hunks(text)
    if line_hunks:
        return line_hunks
    return parse_search_replace(text)


# ---------------------------------------------------------------------------
# CLI / test runner
# ---------------------------------------------------------------------------

def _demo() -> None:
    """Demo com exemplo fixo (útil pra visualizar o formato)."""
    example = (
        "@3\n"
        "- return a - b\n"
        "+ return a + b\n"
        "\n"
        "@7\n"
        "- x = 10\n"
        "+ x = 20\n"
    )
    print("--- INPUT ---")
    print(example)
    hunks = parse_line_hunks(example)
    print(f"\n--- {len(hunks)} HUNK(S) ---")
    for i, h in enumerate(hunks, 1):
        ok, msg = validate_line_hunk(h)
        tag = "OK" if ok else f"FALHOU: {msg}"
        print(f"\n#{i} @{h.line}  [{tag}]")
        print(f"  expected: {h.expected!r}")
        print(f"  new:      {h.new!r}")
    print("\n--- FORMATADO ---")
    print(format_line_hunks(hunks))


def _run_tests() -> int:
    """Suite de testes. Retorna exit code (0 = tudo OK)."""
    tests: list[tuple[str, callable]] = [
        ("line-hunk: simples",              _t_lh_simple),
        ("line-hunk: multi-linha",          _t_lh_multiline),
        ("line-hunk: pure add",             _t_lh_pure_add),
        ("line-hunk: pure remove",          _t_lh_pure_remove),
        ("line-hunk: multi-hunk",           _t_lh_multi),
        ("line-hunk: round-trip",           _t_lh_roundtrip),
        ("line-hunk: indentação",           _t_lh_indent),
        ("line-hunk: @0 rejeitado",         _t_lh_zero),
        ("line-hunk: @N inline rejeitado",  _t_lh_inline),
        ("line-hunk: hunk vazio descartado",_t_lh_empty),
        ("SEARCH/REPLACE: simples",         _t_sr_simple),
        ("SEARCH/REPLACE: no-op",           _t_sr_noop),
        ("SEARCH/REPLACE: malformado",      _t_sr_malformed),
        ("parse_any: prefere line-hunk",    _t_any_prefers_lh),
        ("parse_any: fallback SR",          _t_any_falls_back),
    ]

    passed = 0
    failed = 0
    print()
    for name, fn in tests:
        try:
            fn()
            print(f"  [OK] {name}")
            passed += 1
        except AssertionError as e:
            print(f"  [X]  {name}")
            print(f"       → {e}")
            failed += 1
        except Exception as e:
            print(f"  [X]  {name}")
            print(f"       → {type(e).__name__}: {e}")
            failed += 1

    total = passed + failed
    print(f"\n{passed}/{total} passaram")
    if failed:
        print(f"{failed} falha(s) — corrija antes de avançar.")
        return 1
    return 0


# --- helpers de teste (mantidos curtos e explícitos) ---

def _t_lh_simple() -> None:
    text = "@3\n- return a - b\n+ return a + b\n"
    hunks = parse_line_hunks(text)
    assert len(hunks) == 1, f"esperado 1 hunk, achou {len(hunks)}"
    h = hunks[0]
    assert h.line == 3, f"line={h.line}, esperado 3"
    assert h.expected == ["return a - b"], f"expected={h.expected!r}"
    assert h.new == ["return a + b"], f"new={h.new!r}"


def _t_lh_multiline() -> None:
    text = (
        "@5\n"
        "- def f():\n"
        "-     return 1\n"
        "+ def f():\n"
        "+     return 2\n"
    )
    hunks = parse_line_hunks(text)
    assert len(hunks) == 1
    h = hunks[0]
    assert h.line == 5
    assert h.expected == ["def f():", "    return 1"]
    assert h.new == ["def f():", "    return 2"]


def _t_lh_pure_add() -> None:
    text = "@2\n+ print('debug')\n"
    hunks = parse_line_hunks(text)
    assert len(hunks) == 1
    h = hunks[0]
    assert h.line == 2
    assert h.expected == []
    assert h.new == ["print('debug')"]
    ok, _ = validate_line_hunk(h)
    assert ok, "pure add deve validar"


def _t_lh_pure_remove() -> None:
    text = "@4\n- print('debug')\n"
    hunks = parse_line_hunks(text)
    assert len(hunks) == 1
    h = hunks[0]
    assert h.expected == ["print('debug')"]
    assert h.new == []
    ok, _ = validate_line_hunk(h)
    assert ok


def _t_lh_multi() -> None:
    text = (
        "@1\n"
        "- a\n"
        "+ A\n"
        "\n"
        "@10\n"
        "- b\n"
        "+ B\n"
    )
    hunks = parse_line_hunks(text)
    assert len(hunks) == 2, f"esperado 2 hunks, achou {len(hunks)}"
    assert hunks[0].line == 1
    assert hunks[1].line == 10


def _t_lh_roundtrip() -> None:
    original = LineHunk(
        line=3,
        expected=["return a - b", ""],
        new=["return a + b"],
    )
    formatted = format_line_hunk(original)
    reparsed = parse_line_hunks(formatted)
    assert len(reparsed) == 1
    r = reparsed[0]
    assert r.line == original.line, f"line: {r.line} != {original.line}"
    assert r.expected == original.expected, f"expected: {r.expected!r} != {original.expected!r}"
    assert r.new == original.new, f"new: {r.new!r} != {original.new!r}"


def _t_lh_indent() -> None:
    text = (
        "@7\n"
        "-     return 1\n"
        "+     return 2\n"
    )
    hunks = parse_line_hunks(text)
    assert len(hunks) == 1
    h = hunks[0]
    # 4 espaços preservados após o prefixo
    assert h.expected == ["    return 1"], f"got {h.expected!r}"
    assert h.new == ["    return 2"], f"got {h.new!r}"


def _t_lh_zero() -> None:
    text = "@0\n- a\n+ b\n"
    hunks = parse_line_hunks(text)
    assert len(hunks) == 0, f"@0 deve ser rejeitado, achou {len(hunks)}"


def _t_lh_inline() -> None:
    # @N inline (não sozinho) não deve ser parseado como hunk
    text = "@3 return a + b\n- old\n+ new\n"
    hunks = parse_line_hunks(text)
    # A linha @3 inline é ignorada → o hunk nunca inicia
    assert len(hunks) == 0, f"@N inline deve ser ignorado, achou {len(hunks)}"


def _t_lh_empty() -> None:
    text = "@5\n\n- old\n+ new\n"
    # @5 sozinho, seguido de blank → hunk vazio, descartado
    hunks = parse_line_hunks(text)
    assert len(hunks) == 0, f"hunk vazio deve ser descartado, achou {len(hunks)}"


def _t_sr_simple() -> None:
    text = (
        "[SEARCH]\n"
        "def somar(a, b):\n"
        "    return a - b\n"
        "[REPLACE]\n"
        "def somar(a, b):\n"
        "    return a + b\n"
        "[END]\n"
    )
    blocks = parse_search_replace(text)
    assert len(blocks) == 1
    b = blocks[0]
    assert "return a - b" in b.search
    assert "return a + b" in b.replace


def _t_sr_noop() -> None:
    b = SearchReplaceBlock(search="x = 1", replace="x = 1")
    ok, msg = validate_block(b)
    assert not ok, "no-op deve falhar"
    assert "não altera" in msg or "==" in msg


def _t_sr_malformed() -> None:
    text = "[SEARCH]\ndef f():\n    pass\n[REPLACE]\ndef f():\n    return 1\n"
    # Sem [END] → descartado
    blocks = parse_search_replace(text)
    assert len(blocks) == 0, f"sem END deve ser descartado, achou {len(blocks)}"


def _t_any_prefers_lh() -> None:
    text = "@3\n- a\n+ b\n"
    hunks = parse_any_hunks(text)
    assert len(hunks) == 1
    assert isinstance(hunks[0], LineHunk)


def _t_any_falls_back() -> None:
    text = (
        "[SEARCH]\n"
        "def f():\n"
        "    return 1\n"
        "[REPLACE]\n"
        "def f():\n"
        "    return 2\n"
        "[END]\n"
    )
    hunks = parse_any_hunks(text)
    assert len(hunks) == 1
    assert isinstance(hunks[0], SearchReplaceBlock)


if __name__ == "__main__":
    import sys

    if "--test" in sys.argv:
        raise SystemExit(_run_tests())
    elif "--demo" in sys.argv:
        _demo()
    elif len(sys.argv) > 1:
        text = "\n".join(sys.argv[1:])
        hunks = parse_any_hunks(text)
        print(f"Encontrados {len(hunks)} hunk(s):")
        for i, h in enumerate(hunks, 1):
            ok, msg = validate_any_hunk(h)
            tag = "OK" if ok else msg
            print(f"  #{i} [{type(h).__name__}] {tag}")
    else:
        text = sys.stdin.read()
        hunks = parse_any_hunks(text)
        print(format_any_hunks(hunks))
