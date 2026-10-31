# -*- coding: utf-8 -*-
# engine/training/diff_gen.py
"""
Gerador de dataset diff (@N - old + new) com 10+ tipos de mutação.

Cada mutação é validada com ast.parse — se quebra sintaxe, é descartada.
Isso evita dataset com código inválido (o bug do v9: 17 amostras, poucas
válidas, modelo memorizou formato mas não task).

God: Demeter (colheita) + Anúbis (validação).
OSL-15: linha malformada → skip, nunca derruba o build.
OSL-17: só gera dataset diff; treino fica em train.py.
"""

from __future__ import annotations

import ast
import hashlib
import json
import random
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

TRAINING_SYSTEM_PROMPT = (
    "Você é um assistente de edição de código. Responda em português. "
    "Use o formato @N seguido de linhas com - (antigo) e + (novo). "
    "Exemplo:\n@3\n- def f(x): return x - 1\n+ def f(x): return x + 1"
)

# ---------------------------------------------------------------------------
# Mutações: (regex, replacement, descrição)
# Regex usa lookarounds pra evitar match parcial dentro de strings/operadores
# ---------------------------------------------------------------------------

_MUTATIONS: list[tuple[str, str, str]] = [
    # Aritméticos
    (r'(?<![=!<>+\-*/%&|^]) \+ (?![=])', ' - ', "Troque + por -"),
    (r'(?<![=!<>+\-*/%&|^]) - (?![=>])', ' + ', "Troque - por +"),
    (r'(?<![*/]) \* (?![*/=])', ' / ', "Troque * por /"),
    (r'(?<![*/]) / (?![*/=])', ' * ', "Troque / por *"),
    (r' \+= ', ' -= ', "Troque += por -="),
    (r' -= ', ' += ', "Troque -= por +="),

    # Comparadores
    (r' == ', ' != ', "Troque == por !="),
    (r' != ', ' == ', "Troque != por =="),
    (r'(?<![<>=!]) < (?![=<])', ' > ', "Troque < por >"),
    (r'(?<![<>=!]) > (?![=>])', ' < ', "Troque > por <"),
    (r' >= ', ' <= ', "Troque >= por <="),
    (r' <= ', ' >= ', "Troque <= por >="),

    # Booleanos
    (r'\band\b', 'or', "Troque 'and' por 'or'"),
    (r'\bor\b', 'and', "Troque 'or' por 'and'"),
    (r'\bTrue\b', 'False', "Troque True por False"),
    (r'\bFalse\b', 'True', "Troque False por True"),

    # Retornos
    (r'\breturn None\b', 'return 0', "Troque return None por return 0"),
    (r'\breturn True\b', 'return False', "Troque return True por return False"),
    (r'\breturn False\b', 'return True', "Troque return False por return True"),

    # Negação de if
    (r'\bif not \b', 'if ', "Troque 'if not' por 'if'"),
    # Cuidado: só aplica em ifs que não têm 'not'
    (r'\bif (?=(?!not\b))', 'if not ', "Troque 'if' por 'if not'"),

    # Range
    (r'range\((\w+)\)', r'range(\1 + 1)', "Range(n) → range(n+1)"),
    (r'range\((\w+) \+ 1\)', r'range(\1)', "Range(n+1) → range(n)"),

    # Membership / identity
    (r'\bnot in\b', 'in', "Troque 'not in' por 'in'"),
    (r'\bis not None\b', 'is None', "Troque 'is not None' por 'is None'"),
    (r'\bis None\b', 'is not None', "Troque 'is None' por 'is not None'"),

    # Módulo
    (r' % 2 == 0\b', ' % 2 == 1', "Troque '% 2 == 0' por '% 2 == 1'"),
    (r' % 2 == 1\b', ' % 2 == 0', "Troque '% 2 == 1' por '% 2 == 0'"),
]

# Paths default (relativo à raiz do projeto)
_DEFAULT_PATHS = [
    "engine/",
    "lixao/recycle/",
    "install.py",
    "merge_lora_numpy_gguf.py",
]

_SKIP_DIRS = {"__pycache__", ".git", "venv", ".doxoade", "thirdparty",
              "models", "node_modules"}

_CONTEXT_WINDOW = 8

@dataclass
class Mutation:
    line: int          # 1-indexed
    original: str
    mutated: str
    description: str


@dataclass
class DiffSample:
    messages: list[dict]
    source_file: str
    line: int

    def to_jsonl(self) -> str:
        return json.dumps({"messages": self.messages}, ensure_ascii=False)


def _iter_files(paths: Iterable[str | Path]) -> Iterable[Path]:
    for p in paths:
        path = Path(p)
        if path.is_file():
            if path.suffix.lower() == ".py":
                yield path
            continue
        if not path.is_dir():
            continue
        for py in path.rglob("*.py"):
            if any(skip in py.parts for skip in _SKIP_DIRS):
                continue
            yield py


def _mutate_line(line: str, regex: re.Pattern, replacement: str) -> str | None:
    """Skipa linhas com concatenação de string (evita TypeError runtime)."""
    if ('"' in line or "'" in line) and ('+' in replacement or '-' in replacement):
        if re.search(r'[+\-]\s*["\']', line) or re.search(r'["\']\s*[+\-]', line):
            return None
        if 'f"' in line or "f'" in line:
            return None
    new = regex.sub(replacement, line, count=1)
    if new == line:
        return None
    return new


def _validate_full_file(lines: list[str], line_idx: int, new_line: str) -> bool:
    """Substitui a linha e verifica se o arquivo inteiro ainda parseia."""
    test_lines = lines.copy()
    test_lines[line_idx] = new_line
    try:
        ast.parse("\n".join(test_lines))
        return True
    except SyntaxError:
        return False


def _extract_mutations(
    content: str,
    file_path: Path,
    max_per_file: int,
    rng: random.Random,
) -> list[Mutation]:
    """Extrai até max_per_file mutações válidas do arquivo."""
    lines = content.splitlines()
    candidates: list[Mutation] = []

    for line_idx, line in enumerate(lines):
        if not line.strip() or line.strip().startswith("#"):
            continue
        for regex_str, replacement, desc in _MUTATIONS:
            regex = re.compile(regex_str)
            new_line = _mutate_line(line, regex, replacement)
            if new_line is None:
                continue
            if not _validate_full_file(lines, line_idx, new_line):
                continue
            candidates.append(Mutation(
                line=line_idx + 1,
                original=line,
                mutated=new_line,
                description=desc,
            ))
            break  # 1 mutação por linha (evita multiplas no mesmo @N)

    if len(candidates) <= max_per_file:
        return candidates
    return rng.sample(candidates, max_per_file)


def _make_sample(
    content: str,
    mut: "Mutation",
    file_path: str,
) -> "DiffSample":
    """Janela de ±8 linhas ao redor do alvo."""
    all_lines = content.splitlines()
    target_idx = mut.line - 1

    start = max(0, target_idx - _CONTEXT_WINDOW)
    end   = min(len(all_lines), target_idx + _CONTEXT_WINDOW + 1)

    window_lines = all_lines[start:end]
    context_str  = "\n".join(window_lines)
    new_line_num = target_idx - start + 1

    user = (
        f"Código:\n```python\n{context_str}\n```\n\n"
        f"Tarefa: {mut.description} na linha {new_line_num}."
    )
    assistant = (
        f"@{new_line_num}\n"
        f"- {mut.original}\n"
        f"+ {mut.mutated}"
    )
    return DiffSample(
        messages=[
            {"role": "system", "content": TRAINING_SYSTEM_PROMPT},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        source_file=file_path,
        line=new_line_num,
    )


# ---------------------------------------------------------------------------
# Builder público
# ---------------------------------------------------------------------------

@dataclass
class DiffDatasetResult:
    name: str
    output_dir: Path
    samples: list[DiffSample]
    per_file: list[dict] = field(default_factory=list)
    files_scanned: int = 0
    files_with_mut: int = 0
    mutations_gen: int = 0
    mutations_valid: int = 0


def build_diff_dataset(
    name: str,
    sources: list[str | Path] | None = None,
    *,
    max_per_file: int = 15,
    split_ratio: float = 0.9,
    out_root: Path | str = Path("data") / "processed",
    out_dir: Path | str | None = None,
    seed: int = 42,
) -> dict:
    if out_dir is not None:
        out_root = out_dir
    """Consolida diffs de múltiplos arquivos num dataset pronto pra treino."""
    rng = random.Random(seed)
    paths = sources or _DEFAULT_PATHS
    out_dir = Path(out_root) / name
    out_dir.mkdir(parents=True, exist_ok=True)

    samples: list[DiffSample] = []
    per_file: list[dict] = []
    files_scanned = 0
    files_with_mut = 0
    mutations_gen = 0
    mutations_valid = 0

    for file_path in _iter_files(paths):
        files_scanned += 1
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        mutations = _extract_mutations(content, file_path, max_per_file, rng)
        if not mutations:
            continue

        files_with_mut += 1
        mutations_gen += max_per_file  # tentativas
        mutations_valid += len(mutations)

        for m in mutations:
            samples.append(_make_sample(content, m, str(file_path)))

        per_file.append({
            "file": str(file_path),
            "mutations_generated": max_per_file,
            "mutations_validated": len(mutations),
        })

    # Split
    shuffled = samples.copy()
    rng.shuffle(shuffled)
    n_train = max(1, int(len(shuffled) * split_ratio))
    train = shuffled[:n_train]
    val = shuffled[n_train:]

    # Escrita
    _write_split(out_dir / "train.jsonl", train)
    _write_split(out_dir / "val.jsonl", val)

    # Manifest
    manifest = {
        "name": name,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "sources": [str(p) for p in paths],
        "stats": {
            "total": len(samples),
            "train": len(train),
            "val": len(val),
            "files_scanned": files_scanned,
            "files_with_mutations": files_with_mut,
            "mutations_generated": mutations_gen,
            "mutations_validated": mutations_valid,
        },
        "per_file": per_file,
        "files": {
            "train_jsonl": str(out_dir / "train.jsonl"),
            "val_jsonl": str(out_dir / "val.jsonl"),
        },
        "sufficient": len(samples) >= 100,
        "warning": None if len(samples) >= 100
                   else f"dataset com {len(samples)} amostra(s) (<100)",
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return manifest


def _write_split(path: Path, samples: list[DiffSample]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for s in samples:
            fh.write(s.to_jsonl() + "\n")
