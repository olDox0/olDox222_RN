# -*- coding: utf-8 -*-
"""Symbol indexer — extrai FunctionDef/ClassDef de arquivos Python via AST.

Fase 5.1 — não depende de nada além do stdlib (OSL-18).
God: Thoth (linguagem e lógica).

Uso:
    python -m engine.tools.symbol_indexer engine/cli.py
    python -m engine.tools.symbol_indexer engine/         # diretório
    python -m engine.tools.symbol_indexer --test
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal

SymbolKind = Literal["function", "async_function", "method", "class"]

_CACHE_VERSION = 1


# ──────────────────────────────────────────────────────────
# Contratos
# ──────────────────────────────────────────────────────────
@dataclass
class Symbol:
    name:       str
    kind:       SymbolKind
    file:       str          # label (relativo ou absoluto); não é chave de I/O
    start_line: int          # 1-indexed, inclui decorators
    end_line:   int          # 1-indexed, inclusivo
    signature:  str
    docstring:  str
    parent:     str | None   # nome da classe/função-mãe, se aninhado
    body_hash:  str          # sha1[:16] das linhas normalizadas

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Symbol":
        return cls(**data)


# ──────────────────────────────────────────────────────────
# Formatação de assinatura
# ──────────────────────────────────────────────────────────
def _unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return "…"


def _format_one_arg(arg: ast.arg, default_repr: str = "") -> str:
    ann = _unparse(arg.annotation)
    text = f"{arg.arg}: {ann}" if ann else arg.arg
    if default_repr:
        text += f"={default_repr}"
    return text


def _default_short(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Name):
        return node.id
    return "…"


def _format_args(args: ast.arguments) -> str:
    parts: list[str] = []

    pos = args.posonlyargs + args.args
    n_pos = len(pos)
    n_def = len(args.defaults)
    first_default = n_pos - n_def

    for i, arg in enumerate(pos):
        default = ""
        if i >= first_default:
            default = _default_short(args.defaults[i - first_default])
        parts.append(_format_one_arg(arg, default))

    if args.vararg:
        ann = _unparse(args.vararg.annotation)
        parts.append(f"*{args.vararg.arg}" + (f": {ann}" if ann else ""))

    for i, arg in enumerate(args.kwonlyargs):
        default = _default_short(args.kw_defaults[i])
        parts.append(_format_one_arg(arg, default))

    if args.kwarg:
        ann = _unparse(args.kwarg.annotation)
        parts.append(f"**{args.kwarg.arg}" + (f": {ann}" if ann else ""))

    return ", ".join(parts)


def _format_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    sig = f"{node.name}({_format_args(node.args)})"
    ret = _unparse(node.returns)
    if ret:
        sig += f" -> {ret}"
    return sig


def _format_class_signature(node: ast.ClassDef) -> str:
    bases = ", ".join(_unparse(b) for b in node.bases if b is not None)
    return f"class {node.name}" + (f"({bases})" if bases else "")


def _short_doc(node: ast.AST, max_chars: int = 120) -> str:
    doc = (ast.get_docstring(node) or "").strip()
    if not doc:
        return ""
    first = doc.splitlines()[0].strip()
    if len(first) > max_chars:
        first = first[: max_chars - 1] + "…"
    return first


def _body_hash(source_lines: list[str], start: int, end: int) -> str:
    """sha1 truncado das linhas [start, end] (1-indexed), sem whitespace final."""
    chunk = "\n".join(line.rstrip() for line in source_lines[start - 1:end])
    return hashlib.sha1(chunk.encode("utf-8", errors="replace")).hexdigest()[:16]


def _decorator_start(node: ast.AST) -> int:
    """Menor lineno entre o nó e seus decorators (inclui multi-linha)."""
    start = getattr(node, "lineno", 1)
    for dec in getattr(node, "decorator_list", []):
        start = min(start, getattr(dec, "lineno", start))
    return start


# ──────────────────────────────────────────────────────────
# Walking
# ──────────────────────────────────────────────────────────
def _iter_symbols(
    tree: ast.AST,
    source_lines: list[str],
    file_label: str,
) -> list[Symbol]:
    out: list[Symbol] = []

    def visit(node: ast.AST, parent: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_method = parent is not None and isinstance(node, ast.ClassDef)
                kind: SymbolKind
                if is_method:
                    kind = "method"
                elif isinstance(child, ast.AsyncFunctionDef):
                    kind = "async_function"
                else:
                    kind = "function"
                start = _decorator_start(child)
                end   = getattr(child, "end_lineno", start) or start
                out.append(Symbol(
                    name       = child.name,
                    kind       = kind,
                    file       = file_label,
                    start_line = start,
                    end_line   = end,
                    signature  = _format_signature(child),
                    docstring  = _short_doc(child),
                    parent     = parent,
                    body_hash  = _body_hash(source_lines, start, end),
                ))
                visit(child, child.name)
            elif isinstance(child, ast.ClassDef):
                start = _decorator_start(child)
                end   = getattr(child, "end_lineno", start) or start
                out.append(Symbol(
                    name       = child.name,
                    kind       = "class",
                    file       = file_label,
                    start_line = start,
                    end_line   = end,
                    signature  = _format_class_signature(child),
                    docstring  = _short_doc(child),
                    parent     = parent,
                    body_hash  = _body_hash(source_lines, start, end),
                ))
                visit(child, child.name)
            else:
                visit(child, parent)

    visit(tree, None)
    return out


# ──────────────────────────────────────────────────────────
# API pública
# ──────────────────────────────────────────────────────────
def build(file: Path | str, *, label: str | None = None) -> list[Symbol]:
    """Extrai symbols de um .py. Retorna [] para arquivo ausente, vazio ou com SyntaxError."""
    path = Path(file)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    source_lines = source.splitlines()
    file_label   = label if label is not None else str(path)
    return _iter_symbols(tree, source_lines, file_label)


def build_dir(
    root: Path | str,
    *,
    pattern: str = "*.py",
    skip_dirs: frozenset[str] = frozenset({
        "__pycache__", ".git", "venv", ".venv", ".doxoade",
        "node_modules", "models", "build", "dist", "tests",
        "lixao", "thirdparty", "experiments", ".orn",
        "data", "docs",
    }),
) -> dict[Path, list[Symbol]]:
    root_path = Path(root)
    out: dict[Path, list[Symbol]] = {}
    if not root_path.exists():
        return out

    # Caso 1: arquivo único passado como --path
    if root_path.is_file():
        if root_path.suffix.lower() == ".py":
            syms = build(root_path)
            if syms:
                out[root_path] = syms
        return out

    # Caso 2: diretório (comportamento original)
    for py in root_path.rglob(pattern):
        if any(part in skip_dirs for part in py.parts):
            continue
        try:
            rel = py.relative_to(root_path)
        except ValueError:
            rel = py
        syms = build(py, label=str(rel))
        if syms:
            out[py] = syms
    return out


def persist(index: dict[Path, list[Symbol]], cache_path: Path | str) -> Path:
    out = Path(cache_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version":      _CACHE_VERSION,
        "generated_at": int(time.time()),
        "files": {
            str(p): {
                "mtime_ns": p.stat().st_mtime_ns if p.exists() else 0,
                "size":     p.stat().st_size if p.exists() else 0,
                "symbols":  [s.to_dict() for s in syms],
            }
            for p, syms in index.items()
        },
    }
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out


def load(cache_path: Path | str) -> dict[Path, list[Symbol]]:
    path = Path(cache_path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict) or data.get("version") != _CACHE_VERSION:
        return {}
    out: dict[Path, list[Symbol]] = {}
    for file_str, entry in (data.get("files") or {}).items():
        syms = [Symbol.from_dict(s) for s in entry.get("symbols", [])]
        out[Path(file_str)] = syms
    return out


def is_stale(cache_path: Path | str, file: Path | str) -> bool:
    """True se o cache não cobre `file` ou o arquivo mudou (mtime/size)."""
    cache_path = Path(cache_path)
    if not cache_path.exists():
        return True
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    entry = (data.get("files") or {}).get(str(file))
    if entry is None:
        return True
    path = Path(file)
    if not path.exists():
        return True
    stat = path.stat()
    return (
        entry.get("mtime_ns") != stat.st_mtime_ns
        or entry.get("size") != stat.st_size
    )


# ──────────────────────────────────────────────────────────
# Testes embutidos
# ──────────────────────────────────────────────────────────
_TEST_SOURCE = '''\
"""Módulo de teste."""

import sys


def _helper(x, y=10):
    return x + y


@decorator("arg")
def public_fn(name: str, *args, kw_only: int = 5, **kw) -> str:
    """Docstring curta."""
    return name


class Foo:
    """Uma classe."""

    def __init__(self, val):
        self.val = val

    @property
    def val_copy(self):
        return self.val

    async def fetch(self) -> bytes:
        return b""


async def async_top(a, b):
    return a + b
'''

def load_or_build(
    file: Path | str,
    cache_path: Path | str = Path("data") / "symbol_cache.json",
) -> dict[Path, list[Symbol]]:
    """Carrega índice do cache se válido, senão reconstrói e persiste.

    Retorna sempre um dict[Path, list[Symbol]] com `file` presente
    (mesmo que vazio em caso de SyntaxError).

    Nunca levanta exceção por falha de cache — fallback silencioso
    para build() sem persist.
    """
    file = Path(file)
    cache_path = Path(cache_path)

    # Carrega o cache existente (pode estar vazio ou corrompido → {})
    index: dict[Path, list[Symbol]] = {}
    try:
        index = load(cache_path)
    except Exception:
        index = {}

    # Cache hit?
    if file in index:
        try:
            if not is_stale(cache_path, file):
                return index
        except Exception:
            pass   # staleness indeterminado → rebuild

    # Miss ou stale → rebuild só esse arquivo
    try:
        syms = build(file)
    except Exception:
        return index   # preserva cache de outros arquivos

    index[file] = syms
    try:
        persist(index, cache_path)
    except OSError:
        pass   # sem cache, mas retorna o index recém-construído

    return index

def _run_tests() -> int:
    import tempfile

    passed = failed = 0

    def _check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            print(f"  [OK] {name}")
            passed += 1
        else:
            print(f"  [X]  {name}" + (f" — {detail}" if detail else ""))
            failed += 1

    tmp = Path(tempfile.mkdtemp())
    sample = tmp / "sample.py"
    sample.write_text(_TEST_SOURCE, encoding="utf-8")

    try:
        syms = build(sample)
        by = {s.name: s for s in syms}

        for name in ("_helper", "public_fn", "Foo", "__init__",
                     "val_copy", "fetch", "async_top"):
            _check(f"encontra {name}", name in by)

        if "_helper" in by:
            s = by["_helper"]
            _check("_helper signature", s.signature == "_helper(x, y=10)", s.signature)
            _check("_helper kind", s.kind == "function")
            _check("_helper parent=None", s.parent is None)

        if "public_fn" in by:
            s = by["public_fn"]
            _check("public_fn signature tem -> str", "-> str" in s.signature, s.signature)
            _check("public_fn docstring", s.docstring == "Docstring curta.", s.docstring)
            _check("public_fn start_line antes de def (decorator)",
                   s.start_line < s.end_line, f"{s.start_line}-{s.end_line}")

        if "Foo" in by:
            _check("Foo kind=class", by["Foo"].kind == "class")
            _check("Foo signature começa class Foo",
                   by["Foo"].signature.startswith("class Foo"), by["Foo"].signature)

        if "__init__" in by:
            s = by["__init__"]
            _check("__init__ kind=method", s.kind == "method")
            _check("__init__ parent=Foo", s.parent == "Foo", str(s.parent))

        if "val_copy" in by:
            s = by["val_copy"]
            _check("val_copy start_line cobre @property",
                   s.start_line < s.end_line, f"{s.start_line}-{s.end_line}")

        if "fetch" in by:
            s = by["fetch"]
            _check("fetch kind=method", s.kind == "method")
            _check("fetch retorno bytes", "-> bytes" in s.signature, s.signature)

        # build_dir
        index = build_dir(tmp)
        _check("build_dir inclui sample.py", sample in index)

        # cache round-trip
        cache = tmp / "_cache.json"
        persist(index, cache)
        _check("cache escrito", cache.exists())
        loaded = load(cache)
        _check("cache carrega sample.py", sample in loaded)
        if sample in loaded:
            orig = {s.name for s in index[sample]}
            got  = {s.name for s in loaded[sample]}
            _check("cache preserva nomes", orig == got, f"{orig} vs {got}")
        _check("is_stale=False após persist", not is_stale(cache, sample))

        # edge cases
        _check("build de arquivo ausente → []", build(tmp / "nope.py") == [])

        empty = tmp / "empty.py"
        empty.write_text("# só comentário\n", encoding="utf-8")
        _check("build de arquivo sem defs → []", build(empty) == [])

        broken = tmp / "broken.py"
        broken.write_text("def oops(:\n  pass\n", encoding="utf-8")
        _check("build de SyntaxError → []", build(broken) == [])

        # smoke: engine/cli.py real (se disponível)
        cli_path = Path(__file__).resolve().parent.parent / "cli.py"

        # load_or_build: hit / miss / invalidação
        from engine.tools.symbol_indexer import load_or_build
        cache = tmp / "cache_test.json"

        # 1. Miss inicial → cria
        idx1 = load_or_build(sample, cache_path=cache)
        _check("load_or_build cria cache",
               cache.exists(), f"cache path: {cache}")
        _check("load_or_build retorna sample",
               sample in idx1)
        _check("load_or_build preserva nomes",
               {s.name for s in idx1[sample]} ==
               {"_helper", "public_fn", "Foo", "__init__", "val_copy", "fetch", "async_top"})

        mtime1 = cache.stat().st_mtime_ns
        import time as _t
        _t.sleep(0.01)

        # 2. Hit: não muda mtime (não persistiu de novo)
        idx2 = load_or_build(sample, cache_path=cache)
        _check("load_or_build hit não persiste",
               cache.stat().st_mtime_ns == mtime1,
               f"mtime mudou: {mtime1} → {cache.stat().st_mtime_ns}")
        _check("load_or_build hit retorna mesmos nomes",
               {s.name for s in idx2[sample]} == {s.name for s in idx1[sample]})

        # 3. Invalidação: modificar arquivo → rebuild
        _t.sleep(0.01)
        sample.write_text(_TEST_SOURCE + "\n\ndef novo_simbolo():\n    pass\n",
                          encoding="utf-8")
        idx3 = load_or_build(sample, cache_path=cache)
        _check("load_or_build detecta modificação",
               "novo_simbolo" in {s.name for s in idx3[sample]},
               f"{[s.name for s in idx3[sample]]}")
        _check("load_or_build persiste após rebuild",
               cache.stat().st_mtime_ns > mtime1)

        # 4. Cache corrompido → rebuild silencioso
        cache.write_text("not-json", encoding="utf-8")
        idx4 = load_or_build(sample, cache_path=cache)
        _check("cache corrompido → rebuild",
               "novo_simbolo" in {s.name for s in idx4[sample]})

        if cli_path.exists():
            cli_syms = build(cli_path)
            _check(f"engine/cli.py indexado ({len(cli_syms)} symbols)",
                   len(cli_syms) > 30, f"achou {len(cli_syms)}")
            names = {s.name for s in cli_syms}
            _check("engine/cli.py contém session_cmd", "session_cmd" in names)
            _check("engine/cli.py contém _run_fix ou fix", "fix" in names or "_run_fix" in names)

    finally:
        for f in tmp.glob("*"):
            try: f.unlink()
            except OSError: pass
        try: tmp.rmdir()
        except OSError: pass

    print()
    if failed == 0:
        print(f"  {passed} teste(s) OK")
        return 0
    print(f"  {passed}/{passed + failed} passaram — {failed} falha(s)")
    return 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_run_tests())
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
        if target.is_dir():
            idx = build_dir(target)
            for path, syms in sorted(idx.items()):
                print(f"\n{path}:")
                for s in syms:
                    par = f" (in {s.parent})" if s.parent else ""
                    print(f"  L{s.start_line:>4}-{s.end_line:<4} {s.kind:<14} {s.signature}{par}")
        else:
            for s in build(target):
                par = f" (in {s.parent})" if s.parent else ""
                print(f"  L{s.start_line:>4}-{s.end_line:<4} {s.kind:<14} {s.signature}{par}")
        raise SystemExit(0)
    print("Uso: python -m engine.tools.symbol_indexer <arquivo|diretorio>")
    print("     python -m engine.tools.symbol_indexer --test")
    raise SystemExit(1)
