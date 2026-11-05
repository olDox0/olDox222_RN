# -*- coding: utf-8 -*-
# engine/training/dataset.py
"""
DatasetBuilder — consolida, deduplica e formata datasets de treino.

Formatos de entrada suportados (detecção automática linha-a-linha):
  - {"text": "..."}                             -> instrução + código
  - {"messages": [{"role": "...", ...}]}        -> ChatML OpenAI
  - {"instruction": "...", "output": "..."}     -> Alpaca
  - {"prompt": "...", "response": "..."}        -> prompt-response
  - texto puro com "# Tarefa[ PT]:"             -> blocos separados por \n\n

Formatos de saída:
  - <split>.jsonl  -> {"messages": [...]}       (PEFT/QLoRA)
  - <split>.txt    -> ChatML <|im_start|>...    (llama-finetune)

God: Demeter (pipeline) + Hades (persistência).
OSL-2:  dedup O(n) via set de hashes.
OSL-6:  list retornada é cópia.
OSL-7:  inspect()/preview() retornam dict/list, erro explícito se ausente.
OSL-15: linha malformada -> warning + skip, nunca derruba o build.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

_PROCESSED_DIR = Path("data") / "processed"
_MIN_SUFFICIENT  = 100   # amostras únicas mínimas para treino útil
_MAX_SEQ_CHARS   = 4000  # corta amostras gigantes (proteção de memória)


# ---------------------------------------------------------------------------
# Sample — amostra normalizada
# ---------------------------------------------------------------------------

@dataclass
class Sample:
    messages: list[dict] = field(default_factory=list)
    source:   str = ""
    lang:     str = ""
    tags:     list[str] = field(default_factory=list)
    raw_hash: str = ""

    def to_messages_line(self) -> str:
        return json.dumps({"messages": self.messages}, ensure_ascii=False)

    def to_chatml_text(self) -> str:
        parts = []
        for m in self.messages:
            parts.append(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n")
        parts.append("<|im_start|>assistant\n")
        return "".join(parts)

    def content_length(self) -> int:
        return sum(len(m.get("content", "")) for m in self.messages)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


# ---------------------------------------------------------------------------
# Parsers — cada um retorna list[Sample] (0..N), pra cobrir bilíngue.
# ---------------------------------------------------------------------------

_RE_TASK_PT = re.compile(r"^#\s*(?:Tarefa|Task|Instrução|PT)\s*:\s*(.*)", re.IGNORECASE)
_RE_TASK_EN = re.compile(r"^#\s*(?:Task|EN)\s*:\s*(.*)", re.IGNORECASE)
_RE_TASK_ANY = re.compile(r"^#\s*(?:Tarefa|Task|Instrução)\s*:\s*(.*)", re.IGNORECASE)


def _split_task_block(text: str) -> tuple[str, str, str]:
    """
    Extrai (instrucao_pt, instrucao_en, codigo) de um bloco.
    Retorna ("", "", "") se o bloco não segue o padrão.
    """
    lines = text.splitlines()
    instr_pt = ""
    instr_en = ""
    code_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            code_start = i + 1
            continue
        m_pt = _RE_TASK_PT.match(stripped)
        if m_pt:
            instr_pt = m_pt.group(1).strip()
            continue
        m_en = _RE_TASK_EN.match(stripped)
        if m_en:
            instr_en = m_en.group(1).strip()
            continue
        m_any = _RE_TASK_ANY.match(stripped)
        if m_any and not instr_pt:
            instr_pt = m_any.group(1).strip()
            continue
        # primeira linha não-comentário: começa o código
        code_start = i
        break

    code = "\n".join(lines[code_start:]).strip()
    return instr_pt, instr_en, code


def _parse_task_text(text: str, source: str) -> list[Sample]:
    """Parser para {"text": "# Tarefa[ PT]: ..."}; gera 1 amostra por instrução."""
    if not text or not text.strip():
        return []

    instr_pt, instr_en, code = _split_task_block(text)
    if not code.strip():
        return []
    if not instr_pt and not instr_en:
        # Não é padrão de tarefa. Trata como texto genérico (lang detection).
        return [Sample(
            messages=[
                {"role": "user", "content": text[:_MAX_SEQ_CHARS]},
                {"role": "assistant", "content": "(ok)"},
            ],
            source=source, lang="generic",
            raw_hash=_sha256(text),
        )]

    out: list[Sample] = []
    if instr_pt:
        out.append(Sample(
            messages=[
                {"role": "user", "content": instr_pt},
                {"role": "assistant", "content": code},
            ],
            source=source, lang="pt",
            raw_hash=_sha256(f"pt::{instr_pt}::{code}"),
        ))
    if instr_en:
        out.append(Sample(
            messages=[
                {"role": "user", "content": instr_en},
                {"role": "assistant", "content": code},
            ],
            source=source, lang="en",
            raw_hash=_sha256(f"en::{instr_en}::{code}"),
        ))
    return out


def _parse_messages(obj: dict, source: str) -> list[Sample]:
    msgs = obj.get("messages")
    if not isinstance(msgs, list) or not msgs:
        return []
    cleaned = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role", "")).strip()
        content = str(m.get("content", ""))
        if role in ("system", "user", "assistant") and content:
            cleaned.append({"role": role, "content": content[:_MAX_SEQ_CHARS]})
    if len(cleaned) < 2:
        return []
    text = json.dumps(cleaned, ensure_ascii=False)
    return [Sample(messages=cleaned, source=source, lang="", raw_hash=_sha256(text))]


def _parse_instruction_output(obj: dict, source: str) -> list[Sample]:
    instr = obj.get("instruction") or obj.get("prompt") or obj.get("input")
    out   = obj.get("output") or obj.get("response")
    if not instr or not out:
        return []
    instr = str(instr).strip()[:_MAX_SEQ_CHARS]
    out   = str(out).strip()[:_MAX_SEQ_CHARS]
    if not instr or not out:
        return []
    text = f"{instr}\n{out}"
    return [Sample(
        messages=[
            {"role": "user", "content": instr},
            {"role": "assistant", "content": out},
        ],
        source=source, lang="", raw_hash=_sha256(text),
    )]


def _parse_line(line: str, source: str) -> list[Sample]:
    """Detecta formato da linha e despacha. Nunca levanta exceção."""
    line = line.strip()
    if not line:
        return []
    if not line.startswith("{"):
        # texto puro (bloco de tarefa)
        return _parse_task_text(line, source)
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return []
    if not isinstance(obj, dict):
        return []
    if "text" in obj and isinstance(obj["text"], str):
        return _parse_task_text(obj["text"], source)
    if "messages" in obj:
        return _parse_messages(obj, source)
    if any(k in obj for k in ("instruction", "prompt", "input")):
        return _parse_instruction_output(obj, source)
    return []


def _parse_txt_blocks(text: str, source: str) -> list[Sample]:
    blocks = re.split(r"\n(?=#\s*(?:Tarefa|Task|Instrução|PT|EN)\s*:)", text, flags=re.IGNORECASE)
    out: list[Sample] = []
    for block in blocks:
        if not block.strip(): continue
        out.extend(_parse_task_text(block, source))
    return out


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------

def _normalize_for_hash(text: str) -> str:
    """Normaliza para dedup: colapsa espaços, remove trailing, case-sensitive."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _dedup(samples: list[Sample], strict: bool = False) -> tuple[list[Sample], int]:
    """
    Remove duplicatas por hash. Se strict=True, aplica normalização
    de whitespace antes do hash (pega variantes de formatação).
    Retorna (samples_únicos, n_removidas).
    """
    seen: set[str] = set()
    out: list[Sample] = []
    removed = 0
    for s in samples:
        key = "|".join(f"{m['role']}::{m['content']}" for m in s.messages)
        if strict:
            key = _normalize_for_hash(key)
        h = _sha256(key)
        if h in seen:
            removed += 1
            continue
        seen.add(h)
        out.append(s)
    return out, removed


# ---------------------------------------------------------------------------
# Task-type heuristic (para stats)
# ---------------------------------------------------------------------------

_RE_DEF   = re.compile(r"^\s*def\s+\w+", re.MULTILINE)
_RE_CLASS = re.compile(r"^\s*class\s+\w+", re.MULTILINE)


def _classify_task(sample: Sample) -> str:
    content = "\n".join(m.get("content", "") for m in sample.messages)
    if _RE_CLASS.search(content):
        return "class_def"
    if _RE_DEF.search(content):
        return "function_def"
    return "other"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

@dataclass
class DatasetManifest:
    name: str
    created_at: str
    sources: list[dict]
    config: dict
    stats: dict
    files: dict
    sufficient: bool
    warning: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DatasetManifest":
        return cls(**d)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class DatasetBuilder:
    def __init__(self, name: str, out_dir: Path | str = _PROCESSED_DIR) -> None:
        self.name = name
        self.out_dir = Path(out_dir) / name

    # --- load -------------------------------------------------------------

    def _load_one(self, path: Path) -> list[Sample]:
        if not path.exists():
            return []
        if path.suffix.lower() == ".txt":
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return []
            return _parse_txt_blocks(text, source=path.name)
        # .jsonl
        out: list[Sample] = []
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    out.extend(_parse_line(line, source=path.name))
        except OSError:
            pass
        return out

    def load_sources(self, sources: Iterable[Path | str]) -> list[Sample]:
        all_samples: list[Sample] = []
        for src in sources:
            path = Path(src)
            loaded = self._load_one(path)
            all_samples.extend(loaded)
        return all_samples

    # --- build ------------------------------------------------------------

    def build(
        self,
        sources: Iterable[Path | str],
        *,
        dedup: str = "hash",
        strict: bool = False,
        split: float = 0.9,
        by: str = "line",  # "line" | "source"
    ) -> DatasetManifest:
        src_list = [Path(s) for s in sources]
        raw_samples = self.load_sources(src_list)

        # contagem por fonte antes do dedup
        per_source_before: dict[str, int] = {}
        for s in raw_samples:
            per_source_before[s.source] = per_source_before.get(s.source, 0) + 1

        # dedup
        removed = 0
        if dedup == "hash":
            unique, removed = _dedup(raw_samples, strict=strict)
        else:
            unique = raw_samples

        # contagem por fonte depois do dedup
        per_source_after: dict[str, int] = {}
        for s in unique:
            per_source_after[s.source] = per_source_after.get(s.source, 0) + 1

        # split
        train, val = self._split(unique, ratio=split, by=by)

        # stats
        stats = self._compute_stats(train + val)

        # manifest
        manifest = DatasetManifest(
            name=self.name,
            created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            sources=[
                {
                    "path": str(p),
                    "samples_in": per_source_before.get(p.name, 0),
                    "samples_kept": per_source_after.get(p.name, 0),
                    "samples_dup": per_source_before.get(p.name, 0) - per_source_after.get(p.name, 0),
                }
                for p in src_list
            ],
            config={
                "dedup":  dedup,
                "strict": strict,
                "split":  split,
                "by":     by,
            },
            stats=stats,
            files={},
            sufficient=stats["unique"] >= _MIN_SUFFICIENT,
            warning=(
                None if stats["unique"] >= _MIN_SUFFICIENT
                else f"dataset com {stats['unique']} amostra(s) única(s) "
                     f"(<{_MIN_SUFFICIENT}) — treino provavelmente não generaliza"
            ),
        )

        # escrita
        self._write(manifest, train, val)
        return manifest

    def _split(
        self, samples: list[Sample], ratio: float, by: str,
    ) -> tuple[list[Sample], list[Sample]]:
        if not samples:
            return [], []
        if by == "source":
            sources = sorted({s.source for s in samples})
            cut = max(1, int(len(sources) * ratio))
            train_src = set(sources[:cut])
            train = [s for s in samples if s.source in train_src]
            val   = [s for s in samples if s.source not in train_src]
            return train, val
        # line split com shuffle determinístico (T2.1)
        # Random(42) -> reproduzível; shuffle mistura triviais e complexos
        import random
        shuffled = list(samples)
        random.Random(42).shuffle(shuffled)
        n_train = max(1, int(len(shuffled) * ratio))
        return shuffled[:n_train], shuffled[n_train:]

    def _compute_stats(self, samples: list[Sample]) -> dict:
        by_lang: dict[str, int] = {}
        by_source: dict[str, int] = {}
        by_task:   dict[str, int] = {}
        total_chars = 0
        for s in samples:
            by_lang[s.lang or "unknown"] = by_lang.get(s.lang or "unknown", 0) + 1
            by_source[s.source] = by_source.get(s.source, 0) + 1
            t = _classify_task(s)
            by_task[t] = by_task.get(t, 0) + 1
            total_chars += s.content_length()
        avg_chars = round(total_chars / len(samples), 1) if samples else 0
        return {
            "total":      len(samples),
            "unique":     len(samples),
            "by_lang":    by_lang,
            "by_source":  by_source,
            "by_task":    by_task,
            "avg_chars":  avg_chars,
        }

    def _write(self, manifest: DatasetManifest,
               train: list[Sample], val: list[Sample]) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        files: dict[str, str] = {}

        # JSONL (messages)
        for name, split in (("train", train), ("val", val)):
            p = self.out_dir / f"{name}.jsonl"
            with p.open("w", encoding="utf-8", newline="\n") as fh:
                for s in split:
                    fh.write(s.to_messages_line() + "\n")
            files[f"{name}_jsonl"] = str(p)

        # TXT (ChatML)
        for name, split in (("train", train), ("val", val)):
            p = self.out_dir / f"{name}.txt"
            with p.open("w", encoding="utf-8", newline="\n") as fh:
                for s in split:
                    fh.write(s.to_chatml_text())
                    fh.write("\n")  # separador de amostra
            files[f"{name}_txt"] = str(p)

        # tamanhos
        sizes = {}
        for k, v in files.items():
            try:
                sizes[k] = round(Path(v).stat().st_size / (1024 * 1024), 2)
            except OSError:
                sizes[k] = 0.0

        manifest.files = files
        manifest.stats["train"] = len(train)
        manifest.stats["val"]   = len(val)
        manifest.stats["sizes_mb"] = sizes

        mpath = self.out_dir / "manifest.json"
        mpath.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # --- leitura ----------------------------------------------------------

    @staticmethod
    def list_processed(out_dir: Path | str = _PROCESSED_DIR) -> list[str]:
        root = Path(out_dir)
        if not root.exists():
            return []
        return sorted(
            p.name for p in root.iterdir()
            if p.is_dir() and (p / "manifest.json").exists()
        )

    @staticmethod
    def _load_manifest(name: str, out_dir: Path | str = _PROCESSED_DIR) -> dict:
        path = Path(out_dir) / name / "manifest.json"
        if not path.exists():
            raise FileNotFoundError(f"dataset não encontrado: {name}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"manifest ilegível: {path}: {exc}") from exc

    @classmethod
    def inspect(cls, name: str, out_dir: Path | str = _PROCESSED_DIR) -> dict:
        return cls._load_manifest(name, out_dir)

    @classmethod
    def preview(cls, name: str, n: int = 3,
                out_dir: Path | str = _PROCESSED_DIR) -> list[str]:
        manifest = cls._load_manifest(name, out_dir)
        train_path = Path(manifest.get("files", {}).get("train_jsonl", ""))
        if not train_path.exists():
            return []
        out: list[str] = []
        try:
            with train_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if len(out) >= n:
                        break
                    obj = json.loads(line)
                    msgs = obj.get("messages", [])
                    rendered = "\n".join(
                        f"[{m['role']}] {m['content']}" for m in msgs
                    )
                    out.append(rendered)
        except OSError:
            return out
        return out

    @classmethod
    def stats(cls, name: str, out_dir: Path | str = _PROCESSED_DIR) -> dict:
        manifest = cls._load_manifest(name, out_dir)
        return {
            "name":       manifest.get("name"),
            "created_at": manifest.get("created_at"),
            "stats":      manifest.get("stats", {}),
            "sufficient": manifest.get("sufficient", False),
            "warning":    manifest.get("warning"),
        }
