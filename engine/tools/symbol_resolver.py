# -*- coding: utf-8 -*-
"""Symbol resolver — dada uma instrução em linguagem natural, encontra
o símbolo-alvo no índice do symbol_indexer.

Fase 5.1.2 — heurística conservadora (sem fuzzy, sem LLM).
God: Thoth (linguagem e lógica).

Uso programático:
    from engine.tools.symbol_resolver import resolve, pick_best, source_snippet
    matches = resolve("melhore o session_cmd", index, scope=Path("cli.py"))
    best = pick_best(matches)
    if best:
        snippet = source_snippet(best.symbol, best.file_path)

Uso CLI:
    python -m engine.tools.symbol_resolver "melhore o session_cmd" engine/cli.py
    python -m engine.tools.symbol_resolver --test
"""
from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from engine.tools.symbol_indexer import Symbol


# ──────────────────────────────────────────────────────────
# Stopwords — verbos de comando + artigos/preposições PT-BR
# ──────────────────────────────────────────────────────────
_STOPWORDS = frozenset({
    "a", "o", "as", "os", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas",
    "para", "por", "com", "sem", "sobre", "ao", "aos",
    "e", "ou", "mas", "que", "se", "como", "onde", "quando",
    "este", "esta", "estes", "estas", "esse", "essa",
    "isso", "isto", "aquilo", "ele", "ela", "eles", "elas",
    "melhore", "melhorar", "refatore", "refatorar",
    "modularize", "modularizar", "reorganize", "reorganizar",
    "adicione", "adicionar", "remova", "remover",
    "troque", "trocar", "mude", "mudar",
    "corrija", "corrigir", "conserte", "consertar",
    "renomeie", "renomear", "crie", "criar", "gere", "gerar",
    "explique", "explicar", "faça", "fazer",
    "veja", "ver", "olhe", "olhar",
    "atualize", "atualizar", "implemente", "implementar",
    "otimize", "otimizar", "simplifique", "simplificar",
    "divida", "dividir", "extraia", "extrair", "separe", "separar",
    "funcao", "metodo", "classe", "classes",
    "codigo", "arquivo", "arquivos", "sistema", "sistemas",
    "bloco", "blocos", "trecho", "trechos",
})

_RE_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

_SCORE_EXACT       = 1.00
_SCORE_STARTS_WITH = 0.85
_SCORE_CONTAINS    = 0.70
_SCORE_DOCSTRING   = 0.45
_SCORE_SCOPE_BOOST = 0.10
_MIN_SCORE         = 0.40

Confidence = Literal["high", "medium", "low"]


@dataclass
class SymbolMatch:
    symbol:     Symbol
    file_path:  Path
    score:      float
    confidence: Confidence
    reason:     str

    def to_dict(self) -> dict:
        return {
            "symbol":     self.symbol.name,
            "kind":       self.symbol.kind,
            "file":       str(self.file_path),
            "lines":      f"{self.symbol.start_line}-{self.symbol.end_line}",
            "score":      round(self.score, 3),
            "confidence": self.confidence,
            "reason":     self.reason,
        }


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )


def _extract_candidates(instruction: str) -> list[str]:
    """Extrai TODOS os identificadores. O filtro de stopword é feito
    em `resolve()` após o scoring — só filtramos stopwords de score fraco."""
    if not instruction:
        return []
    normalized = _strip_accents(instruction)
    seen: set[str] = set()
    out: list[str] = []
    for raw in _RE_IDENT.findall(normalized):
        low = raw.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(raw)
    return out


def _score_one(candidate: str, sym: Symbol) -> tuple[float, str]:
    c_low = candidate.lower()
    n_low = sym.name.lower()
    d_low = (sym.docstring or "").lower()

    if c_low == n_low:
        return _SCORE_EXACT, "exact"

    if len(c_low) >= 3 and (n_low.startswith(c_low) or c_low.startswith(n_low)):
        return _SCORE_STARTS_WITH, "prefix"

    if len(c_low) >= 3 and (c_low in n_low or n_low in c_low):
        return _SCORE_CONTAINS, "contains"

    if c_low in d_low:
        return _SCORE_DOCSTRING, "docstring"

    return 0.0, ""


def _confidence(score: float) -> Confidence:
    if score >= 0.90:
        return "high"
    if score >= 0.70:
        return "medium"
    return "low"


def _safe_resolve(path: Path | str) -> Path:
    try:
        return Path(path).resolve()
    except OSError:
        return Path(path)


def resolve(
    instruction: str,
    index: dict[Path, list[Symbol]],
    *,
    scope: Path | str | None = None,
    min_score: float = _MIN_SCORE,
    max_results: int = 5,
) -> list[SymbolMatch]:
    """Encontra símbolos-alvo de uma instrução.

    Estratégia two-tier para stopwords:
      - stopword com match forte (exact/prefix, ≥ 0.85) → mantém
        (ex.: 'dividir' é verbo E nome de função)
      - stopword com match fraco (contains, < 0.85) → filtra como ruído
        (ex.: 'divida' numa instrução genérica)
    """
    candidates = _extract_candidates(instruction)
    if not candidates or not index:
        return []

    scope_path = _safe_resolve(scope) if scope is not None else None

    matches: list[SymbolMatch] = []
    for file_path, symbols in index.items():
        in_scope = scope_path is not None and _safe_resolve(file_path) == scope_path
        for sym in symbols:
            best_score = 0.0
            best_reason = ""
            best_candidate = ""
            for cand in candidates:
                score, reason = _score_one(cand, sym)
                if score > best_score:
                    best_score = score
                    best_reason = reason
                    best_candidate = cand
            if best_score <= 0:
                continue
            # Guard: stopword só passa se o match for forte (exact/prefix)
            if (best_candidate.lower() in _STOPWORDS
                    and best_score < _SCORE_STARTS_WITH):
                continue
            boost = _SCORE_SCOPE_BOOST if in_scope else 0.0
            final = min(1.0, best_score + boost)
            if final < min_score:
                continue
            matches.append(SymbolMatch(
                symbol     = sym,
                file_path  = Path(file_path),
                score      = final,
                confidence = _confidence(final),
                reason     = best_reason + ("+scope" if in_scope else ""),
            ))

    matches.sort(key=lambda m: (-m.score, m.symbol.start_line))
    return matches[:max_results]


def pick_best(
    matches: list[SymbolMatch],
    *,
    ambiguity_margin: float = 0.20,
) -> SymbolMatch | None:
    """Retorna o melhor match SE for claramente superior ao segundo."""
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    if (matches[0].score - matches[1].score) >= ambiguity_margin:
        return matches[0]
    return None


def source_snippet(
    symbol: Symbol,
    file_path: Path | str,
    *,
    context_lines: int = 0,
) -> str:
    """Extrai linhas [start_line, end_line] do arquivo."""
    path = Path(file_path)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    start = max(0, symbol.start_line - 1 - context_lines)
    end   = min(len(lines), symbol.end_line + context_lines)
    return "\n".join(lines[start:end])


def format_matches(matches: list[SymbolMatch]) -> str:
    if not matches:
        return "  (nenhum símbolo encontrado)"
    lines = []
    for i, m in enumerate(matches, 1):
        s = m.symbol
        parent = f" em {s.parent}" if s.parent else ""
        lines.append(
            f"  [{i}] {s.name}{parent} "
            f"({s.kind}, L{s.start_line}-{s.end_line}, "
            f"score={m.score:.2f}, {m.confidence})"
        )
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────
# Testes embutidos
# ──────────────────────────────────────────────────────────
_FIXTURE = '''\
def dividir(a, b):
    """Divide a por b."""
    if b == 0:
        return 0
    return a / b


def multiplicar(a, b):
    return a * b


class Calculadora:
    """Uma calculadora simples."""

    def somar(self, a, b):
        return a + b

    def subtrair(self, a, b):
        return a - b


def _helper():
    pass
'''


def _run_tests() -> int:
    import tempfile

    passed = failed = 0

    def _check(name, cond, detail=""):
        nonlocal passed, failed
        if cond:
            print(f"  [OK] {name}")
            passed += 1
        else:
            print(f"  [X]  {name}" + (f" — {detail}" if detail else ""))
            failed += 1

    tmp = Path(tempfile.mkdtemp())
    sample = tmp / "sample.py"
    sample.write_text(_FIXTURE, encoding="utf-8")
    try:
        from engine.tools.symbol_indexer import build as build_file, build_dir
        index = build_dir(tmp)

        # Exact match
        m = resolve("melhore a função dividir", index)
        _check("exact match 'dividir'",
               len(m) >= 1 and m[0].symbol.name == "dividir",
               f"{[x.symbol.name for x in m]}")
        _check("confidence=high em exact",
               bool(m) and m[0].confidence == "high",
               m[0].confidence if m else "?")

        # Prefix
        m = resolve("ajuste o divid", index)
        _check("prefix match", bool(m) and m[0].symbol.name == "dividir",
               f"{[x.symbol.name for x in m]}")

        # Verbo genérico → vazio
        m = resolve("modularize", index)
        _check("verbo genérico → []", m == [], f"achou {len(m)}")

        # Stopwords filtradas (com acento)
        m = resolve("a o de para com dividir", index)
        names = {x.symbol.name for x in m}
        _check("stopwords filtradas",
               "a" not in names and "o" not in names and "dividir" in names,
               f"achou {names}")

        # Guard two-tier: stopword com match exato é mantida
        m = resolve("dividir", index)
        _check("stopword exata mantida",
               bool(m) and m[0].symbol.name == "dividir",
               f"{[x.symbol.name for x in m]}")

        # Guard two-tier: stopword sem match forte é filtrada
        # (não há símbolo 'divida' no fixture, e 'divida' não é substring de 'dividir')
        m = resolve("divida em duas", index)
        _check("stopword fraca filtrada", m == [],
               f"{[x.symbol.name for x in m]}")

        # Multiple matches
        m = resolve("renomeie multiplicar para dividir", index)
        names = {x.symbol.name for x in m}
        _check("multi-candidato",
               "multiplicar" in names and "dividir" in names,
               f"achou {names}")

        # Scope boost
        m1 = resolve("dividir", index, scope=sample)
        _check("scope aplicado", bool(m1) and "scope" in m1[0].reason,
               m1[0].reason if m1 else "?")

        # pick_best
        best = pick_best(resolve("dividir", index))
        _check("pick_best único", bool(best) and best.symbol.name == "dividir")

        # Case insensitive
        m = resolve("calculadora", index)
        _check("case-insensitive", any(x.symbol.name == "Calculadora" for x in m),
               f"{[x.symbol.name for x in m]}")

        # Método com parent
        m = resolve("somar", index)
        _check("match de método",
               bool(m) and m[0].symbol.name == "somar",
               f"{[x.symbol.name for x in m]}")
        _check("método somar parent=Calculadora",
               bool(m) and m[0].symbol.parent == "Calculadora",
               m[0].symbol.parent if m else "?")

        # source_snippet
        syms = index[sample]
        dividir = next(s for s in syms if s.name == "dividir")
        snippet = source_snippet(dividir, sample)
        _check("snippet contém def", "def dividir" in snippet)
        _check("snippet contém corpo", "return 0" in snippet)
        _check("snippet não inclui vizinho",
               "def multiplicar" not in snippet)

        ctx = source_snippet(dividir, sample, context_lines=3)
        _check("snippet com contexto expande",
               "def multiplicar" in ctx)

        # format_matches
        txt = format_matches(resolve("dividir", index))
        _check("format legível", "dividir" in txt and "L" in txt)

        # Edge cases
        _check("instrução vazia → []", resolve("", index) == [])
        _check("index vazio → []", resolve("dividir", {}) == [])
        _check("'_' isolado → []", resolve("_", index) == [])

        # Smoke real em engine/cli.py
        real_cli = Path(__file__).resolve().parent.parent / "cli.py"
        if real_cli.exists():
            real_index = {real_cli: build_file(real_cli)}

            m = resolve("melhore o session_cmd", real_index, scope=real_cli)
            _check("smoke real: session_cmd",
                   bool(m) and m[0].symbol.name == "session_cmd",
                   f"{[x.symbol.name for x in m]}")

            m = resolve("ajuste o _fmt_ms", real_index, scope=real_cli)
            _check("smoke real: _fmt_ms",
                   bool(m) and m[0].symbol.name == "_fmt_ms",
                   f"{[x.symbol.name for x in m]}")

            m = resolve("modularize", real_index, scope=real_cli)
            _check("smoke real: 'modularize' → []", m == [],
                   f"{[x.symbol.name for x in m]}")

            # A instrução real do teste antigo: "melhore session_cmd"
            m = resolve("melhore session_cmd", real_index, scope=real_cli)
            _check("smoke real: 'melhore session_cmd' → session_cmd",
                   bool(m) and m[0].symbol.name == "session_cmd",
                   f"{[x.symbol.name for x in m]}")
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

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("Uso:")
        print("  python -m engine.tools.symbol_resolver --test")
        print("  python -m engine.tools.symbol_resolver '<instrução>' <arquivo|dir>")
        raise SystemExit(1)

    instruction = args[0]
    target = Path(args[1])
    from engine.tools.symbol_indexer import build, build_dir

    if target.is_dir():
        index = build_dir(target)
        scope = None
    else:
        index = {target: build(target)}
        scope = target

    matches = resolve(instruction, index, scope=scope)
    print(f"Instrução: {instruction!r}")
    print(f"Matches ({len(matches)}):")
    print(format_matches(matches))

    best = pick_best(matches)
    if best is not None:
        print(f"\n→ Melhor: {best.symbol.name} em {best.file_path}")
        print(f"\nSnippet ({best.symbol.start_line}-{best.symbol.end_line}):")
        print(source_snippet(best.symbol, best.file_path))
    elif matches:
        print(f"\n→ Ambíguo — {len(matches)} candidatos, escolha manual")
    else:
        print(f"\n→ Nenhum match — fallback para arquivo inteiro")
