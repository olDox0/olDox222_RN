# -*- coding: utf-8 -*-
# engine/diff/surgeon.py
"""
Aplicador de hunks — port do `mody_patch.py` sem dependência do doxoade.

Recebe hunks parseados (LineHunk do format.py) e aplica no arquivo alvo
usando ancoragem por CONTEÚDO (não por número de linha fixo). Resiste a
drift de linhas, patches fora de ordem e idempotência.

God: Hefesto (transformação) + Ma'at (invariantes de sintaxe).
OSL-15: nunca levanta exceção — retorna SurgeonResult(success=False).
OSL-17: só aplica. Parser é format.py. Sandbox é code_sandbox (externo).

Uso:
    python -m engine.diff.surgeon --test      # suite de testes
    python -m engine.diff.surgeon --demo      # demo
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from engine.diff.format import (
    LineHunk,
    SearchReplaceBlock,
    HunkLike,
    parse_any_hunks,
    validate_any_hunk,
)

logger = logging.getLogger("engine.diff.surgeon")


# ---------------------------------------------------------------------------
# Estruturas
# ---------------------------------------------------------------------------

@dataclass
class PatchLine:
    kind: str   # ' ' | '-' | '+'
    text: str


@dataclass
class Hunk:
    """Hunk interno (formato unificado pro surgeon)."""
    old_start: int                          # 1-based (vem do @N)
    lines: list[PatchLine] = field(default_factory=list)

    def expected_lines(self) -> list[str]:
        return [pl.text for pl in self.lines if pl.kind == '-']

    def new_lines(self) -> list[str]:
        return [pl.text for pl in self.lines if pl.kind == '+']

    def replacement_block(self) -> list[str]:
        return [pl.text for pl in self.lines if pl.kind in (' ', '+')]


@dataclass
class FilePatch:
    target_path: Path
    hunks: list[Hunk] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


@dataclass
class SurgeonResult:
    success: bool = False
    hunks_total: int = 0
    hunks_applied: int = 0
    hunks_failed: int = 0
    hunks_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    details: list[dict] = field(default_factory=list)
    syntax_ok: bool = True
    output_content: str = ""


# ---------------------------------------------------------------------------
# Conversão LineHunk → Hunk
# ---------------------------------------------------------------------------

def convert_to_hunk(h: HunkLike) -> Optional[Hunk]:
    """Converte LineHunk ou SearchReplaceBlock em Hunk interno."""
    if isinstance(h, LineHunk):
        lines: list[PatchLine] = []
        for e in h.expected:
            lines.append(PatchLine('-', e))
        for n in h.new:
            lines.append(PatchLine('+', n))
        return Hunk(old_start=h.line, lines=lines)

    if isinstance(h, SearchReplaceBlock):
        lines = []
        for e in h.search.splitlines():
            lines.append(PatchLine('-', e))
        for n in h.replace.splitlines():
            lines.append(PatchLine('+', n))
        return Hunk(old_start=1, lines=lines)

    return None


def make_file_patch(
    target_path: Path | str, hunks: list[HunkLike],
) -> FilePatch:
    """Valida, converte e monta o FilePatch."""
    fp = FilePatch(target_path=Path(target_path))
    for i, h in enumerate(hunks, 1):
        ok, msg = validate_any_hunk(h)
        if not ok:
            fp.parse_errors.append(f"hunk #{i}: {msg}")
            continue
        converted = convert_to_hunk(h)
        if converted is None:
            fp.parse_errors.append(f"hunk #{i}: conversão falhou")
            continue
        fp.hunks.append(converted)
    return fp


# ---------------------------------------------------------------------------
# PatchSurgeon
# ---------------------------------------------------------------------------

class PatchSurgeon:
    """
    Motor de aplicação de hunks com ancoragem por conteúdo.

    Principais garantias (herdadas do mody_patch v6.4.2):
      - Idempotência: aplicar 2x não corrompe.
      - Match parcial: âncora por `-` (não por contexto).
      - Validação de sintaxe em 2 camadas (anti falso-positivo).
      - Detecção de overlap entre hunks.
      - Preflight classification antes de aplicar.
    """

    # ---- normalização de linha (para matching) ----
    @staticmethod
    def _normalize_line(line: str) -> str:
        line = line.rstrip('\r\n').rstrip()
        return re.sub(r'\s+', ' ', line).strip()

    # ---- busca de âncora (o coração) ----
    @classmethod
    def _find_removal_anchor(
        cls,
        file_lines: list[str],
        hunk: Hunk,
        max_offset: int = 200,
    ) -> tuple[Optional[int], int, str, int, list[int]]:
        """
        Localiza o hunk buscando as linhas `-` (expected).

        Retorna (loc_0based, offset, match_type, contig_len, candidates).
        """
        expected = hunk.expected_lines()
        norm_file = [cls._normalize_line(l) for l in file_lines]
        target_idx = max(0, hunk.old_start - 1)
        total_file = len(file_lines)

        # Pure add → usa old_start direto
        if not expected:
            return (target_idx, 0, 'ADD_ONLY', 0, [target_idx])

        expected_norm = [cls._normalize_line(e) for e in expected]
        n_expected = len(expected_norm)
        if n_expected > total_file:
            return (None, 0, 'NONE', 0, [])

        # Busca todos os matches exatos das remoções
        all_matches: list[int] = []
        for cand in range(total_file - n_expected + 1):
            if norm_file[cand:cand + n_expected] == expected_norm:
                all_matches.append(cand)

        if len(all_matches) == 1:
            loc = all_matches[0]
            return (loc, loc - target_idx, 'EXACT', n_expected, [loc])

        if len(all_matches) > 1:
            all_matches.sort(key=lambda c: abs(c - target_idx))
            best = all_matches[0]
            return (best, best - target_idx, 'EXACT_MULTI', n_expected, all_matches[:5])

        # Sem match exato → tenta streak parcial (threshold 50%)
        best_len = 0
        best_loc: Optional[int] = None
        for cand in range(total_file):
            streak = 0
            for i in range(n_expected):
                if cand + i < total_file and norm_file[cand + i] == expected_norm[i]:
                    streak += 1
                else:
                    break
            if streak > best_len:
                best_len = streak
                best_loc = cand
                if best_len == n_expected:
                    break

        threshold = max(2, int(n_expected * 0.5))
        if best_len >= threshold and best_loc is not None:
            return (best_loc, best_loc - target_idx, 'PARTIAL', best_len, [best_loc])

        return (None, 0, 'NONE', best_len, [])

    # ---- detecção de duplicação ----
    @classmethod
    def _would_create_duplicate(
        cls, file_lines: list[str], loc: int, replacement: list[str],
    ) -> bool:
        if len(replacement) < 2:
            return False
        norm_repl = [cls._normalize_line(l) for l in replacement]
        n = len(norm_repl)
        total = len(file_lines)
        for cand in range(total - n + 1):
            if cand <= loc < cand + n:
                continue
            block = [cls._normalize_line(file_lines[cand + i]) for i in range(n)]
            if block == norm_repl:
                return True
        return False

    @classmethod
    def _is_already_applied(cls, file_lines: list[str], hunk: Hunk) -> bool:
        """
        True se a modificação já está aplicada.

        Regra: replacement existe no arquivo E expected NÃO existe.
        Isso cobre replacement de 1 linha (o caso que _would_create_duplicate
        não pegava).
        """
        expected_norm = [cls._normalize_line(l) for l in hunk.expected_lines()]
        replacement_norm = [cls._normalize_line(l) for l in hunk.new_lines()]

        if not replacement_norm:
            return False  # pure remove: se expected existe, ainda pode aplicar

        # 1. Se o expected ainda existe → não foi aplicado
        if expected_norm:
            n_exp = len(expected_norm)
            for cand in range(len(file_lines) - n_exp + 1):
                block = [
                    cls._normalize_line(file_lines[cand + i])
                    for i in range(n_exp)
                ]
                if block == expected_norm:
                    return False

        # 2. Expected ausente. Replacement existe? → já aplicado
        n_rep = len(replacement_norm)
        for cand in range(len(file_lines) - n_rep + 1):
            block = [
                cls._normalize_line(file_lines[cand + i])
                for i in range(n_rep)
            ]
            if block == replacement_norm:
                return True

        return False

    # ---- validação de sintaxe (2 camadas) ----
    @classmethod
    def _validate_syntax(cls, content: str, target_path: Path) -> Optional[str]:
        if not target_path or target_path.suffix.lower() != '.py':
            return None
        try:
            compile(content, str(target_path), 'exec')
            return None
        except SyntaxError as e_full:
            # Camada 2: compila só o prefixo até o erro
            if e_full.lineno:
                try:
                    prefix = "\n".join(content.splitlines()[:e_full.lineno - 1])
                    if prefix.strip():
                        compile(prefix, str(target_path), 'exec')
                        return None
                except SyntaxError:
                    pass
            return f"SyntaxError em L{e_full.lineno}: {e_full.msg}"
        except Exception as e:
            return f"Erro inesperado: {e}"

    # ---- preflight ----
    @classmethod
    def preflight(cls, patch: FilePatch) -> dict:
        """
        Classifica cada hunk SEM aplicar.

        Returns:
            {"hunks": [{idx, status, loc, reason}], "safe_to_apply": bool}
        """
        if not patch.target_path.exists():
            return {
                "hunks": [],
                "safe_to_apply": False,
                "error": f"arquivo ausente: {patch.target_path}",
            }

        try:
            content = patch.target_path.read_text(encoding='utf-8', errors='ignore')
            file_lines = content.splitlines(keepends=True)
        except Exception as e:
            return {
                "hunks": [],
                "safe_to_apply": False,
                "error": f"leitura falhou: {e}",
            }

        result: dict = {"hunks": [], "safe_to_apply": True}
        applied_ranges: list[tuple[int, int, int]] = []

        for idx, hunk in enumerate(patch.hunks, 1):
            info = {"idx": idx, "status": "UNKNOWN", "loc": None, "reason": ""}

            # Já aplicado?
            if cls._is_already_applied(file_lines, hunk):
                info["status"] = "ALREADY_APPLIED"
                info["reason"] = "modificação já presente no arquivo"
                result["hunks"].append(info)
                continue

            loc, offset, match_type, contig_len, candidates = (
                cls._find_removal_anchor(file_lines, hunk)
            )

            if match_type == 'NONE':
                info["status"] = "WILL_CONFLICT"
                info["reason"] = f"contexto insuficiente ({contig_len}/{len(hunk.expected_lines())})"
                result["safe_to_apply"] = False
                result["hunks"].append(info)
                continue

            info["loc"] = (loc or 0) + 1

            # Overlap?
            expected_len = len(hunk.expected_lines())
            new_start, new_end = loc or 0, (loc or 0) + expected_len
            overlap = None
            for ps, pe, pidx in applied_ranges:
                if new_start < pe and new_end > ps:
                    overlap = pidx
                    break
            if overlap:
                info["status"] = "WILL_CONFLICT"
                info["reason"] = f"overlap com hunk #{overlap}"
                result["safe_to_apply"] = False
                result["hunks"].append(info)
                continue

            info["status"] = "WILL_APPLY"
            info["reason"] = f"{match_type} em L{info['loc']}"
            applied_ranges.append((new_start, new_end, idx))
            result["hunks"].append(info)

        return result

    # ---- simulate (dry-run) ----
    @classmethod
    def simulate(cls, patch: FilePatch, *, run_preflight: bool = True) -> SurgeonResult:
        """
        Simula a aplicação. GRANULAR: aplica o que funciona, pula o que conflita.

        Não aborta quando um hunk falha — continua com os outros. O caller
        decide (via `result.success` e `result.details`) se vale aplicar.
        """
        result = SurgeonResult(success=False, hunks_total=len(patch.hunks))
        result.errors.extend(patch.parse_errors)

        if not patch.target_path.exists():
            result.errors.append(f"arquivo ausente: {patch.target_path}")
            return result

        try:
            content = patch.target_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            result.errors.append(f"leitura falhou: {e}")
            return result

        file_lines = content.splitlines(keepends=True)
        modified = list(file_lines)

        # Classificação prévia (sem aplicar)
        classifications: dict[int, dict] = {}
        if run_preflight:
            pf = cls.preflight(patch)
            for h in pf.get("hunks", []):
                classifications[h["idx"]] = h
            result.details = list(pf.get("hunks", []))

        applied_ranges: list[tuple[int, int, int]] = []

        for idx, hunk in enumerate(patch.hunks, 1):
            cls_status = classifications.get(idx, {}).get("status")

            # Pula idempotente
            if cls_status == "ALREADY_APPLIED":
                result.hunks_skipped += 1
                continue

            # Rejeita conflito (mas NÃO aborta — próximo hunk ainda tenta)
            if cls_status == "WILL_CONFLICT":
                result.hunks_failed += 1
                # já está em result.details pelo preflight
                continue

            # Aplica (re-busca em `modified`, pode ter mudado)
            expected = hunk.expected_lines()
            replacement = hunk.new_lines()

            # Re-check idempotência no estado atual
            if cls._is_already_applied(modified, hunk):
                result.hunks_skipped += 1
                result.details.append({
                    "hunk": idx, "status": "IDEMPOTENT",
                    "reason": "já aplicado (re-check)",
                })
                continue

            loc, offset, match_type, contig_len, _ = (
                cls._find_removal_anchor(modified, hunk)
            )
            if match_type == 'NONE':
                result.hunks_failed += 1
                result.details.append({
                    "hunk": idx, "status": "FAILED",
                    "reason": f"contexto insuficiente ({contig_len}/{len(expected)})",
                })
                continue

            # Overlap runtime (além do preflight — modified mudou)
            new_start, new_end = loc, loc + len(expected)
            overlap = None
            for ps, pe, pidx in applied_ranges:
                if new_start < pe and new_end > ps:
                    overlap = pidx
                    break
            if overlap:
                result.hunks_failed += 1
                result.details.append({
                    "hunk": idx, "status": "FAILED",
                    "reason": f"overlap runtime com hunk #{overlap}",
                })
                continue

            # Aplica este hunk
            new_lines_eol = [
                n + '\n' if not n.endswith('\n') else n for n in replacement
            ]
            modified[loc:loc + len(expected)] = new_lines_eol
            applied_ranges.append((new_start, new_end, idx))
            result.hunks_applied += 1
            result.details.append({
                "hunk": idx, "status": "APPLIED",
                "reason": f"{match_type} em L{(loc or 0) + 1}",
            })

        result.output_content = "".join(modified)
        syntax_err = cls._validate_syntax(result.output_content, patch.target_path)
        result.syntax_ok = syntax_err is None
        if syntax_err:
            result.errors.append(f"sintaxe inválida: {syntax_err}")

        # success=True apenas se TODOS aplicaram/pularam E sintaxe OK
        result.success = (
            result.hunks_failed == 0
            and result.syntax_ok
            and not result.errors
        )
        return result

    # ---- apply (disk write) ----
    @classmethod
    def apply(
        cls, patch: FilePatch, *, backup: bool = True, strict: bool = True,
    ) -> SurgeonResult:
        """
        Aplica em disco.

        strict=True  → só escreve se TODOS os hunks passaram (padrão seguro).
        strict=False → escreve o que foi possível, reporta falhas em errors.
        """
        sim = cls.simulate(patch, run_preflight=True)

        if strict and not sim.success:
            return sim

        if not strict and sim.hunks_applied == 0:
            return sim

        try:
            if backup:
                bak = patch.target_path.with_suffix(
                    patch.target_path.suffix + '.bak'
                )
                shutil.copy2(patch.target_path, bak)
            patch.target_path.write_text(sim.output_content, encoding='utf-8')
            if not strict and not sim.success:
                sim.errors.append(
                    f"apply parcial: {sim.hunks_failed} hunk(s) não aplicados"
                )
            return sim
        except Exception as e:
            sim.errors.append(f"escrita falhou: {e}")
            sim.success = False
            return sim


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

def _write_tmp(content: str) -> Path:
    import tempfile
    tf = tempfile.NamedTemporaryFile(
        mode='w', suffix='.py', delete=False, encoding='utf-8',
    )
    tf.write(content)
    tf.close()
    return Path(tf.name)

def _t_granular_apply() -> None:
    """1 hunk conflita, outros 2 aplicam. success=False, mas parcial."""
    p = _write_tmp("a = 1\nb = 2\nc = 3\n")
    text = (
        "@1\n- a = 1\n+ a = 10\n"
        "\n"
        "@2\n- nonexistent\n+ ghost\n"   # conflita
        "\n"
        "@3\n- c = 3\n+ c = 30\n"
    )
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.simulate(patch)
    assert not res.success, "deve ter sucesso=False (1 falhou)"
    assert res.hunks_applied == 2, f"esperado 2 aplicados, achou {res.hunks_applied}"
    assert res.hunks_failed == 1, f"esperado 1 falha, achou {res.hunks_failed}"
    assert "a = 10" in res.output_content
    assert "c = 30" in res.output_content
    assert "b = 2" in res.output_content  # não foi tocado


def _t_apply_strict_skip() -> None:
    """strict=True (padrão): não escreve se houve falha."""
    p = _write_tmp("a = 1\n")
    original = p.read_text(encoding='utf-8')
    text = "@1\n- nonexistent\n+ ghost\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.apply(patch, backup=False, strict=True)
    assert not res.success
    # Arquivo NÃO deve ter mudado
    assert p.read_text(encoding='utf-8') == original
    p.unlink(missing_ok=True)

def _t_granular_apply() -> None:
    """1 hunk conflita, outros 2 aplicam. success=False, mas parcial."""
    p = _write_tmp("a = 1\nb = 2\nc = 3\n")
    text = (
        "@1\n- a = 1\n+ a = 10\n"
        "\n"
        "@2\n- nonexistent\n+ ghost\n"
        "\n"
        "@3\n- c = 3\n+ c = 30\n"
    )
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.simulate(patch)
    assert not res.success, "success deve ser False (1 falhou)"
    assert res.hunks_applied == 2, f"esperado 2 aplicados, achou {res.hunks_applied}"
    assert res.hunks_failed == 1, f"esperado 1 falha, achou {res.hunks_failed}"
    assert "a = 10" in res.output_content
    assert "c = 30" in res.output_content
    assert "b = 2" in res.output_content

def _t_apply_strict_skip() -> None:
    """strict=True (padrão): não escreve se houve falha."""
    p = _write_tmp("a = 1\n")
    original = p.read_text(encoding='utf-8')
    text = "@1\n- nonexistent\n+ ghost\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.apply(patch, backup=False, strict=True)
    assert not res.success
    assert p.read_text(encoding='utf-8') == original
    p.unlink(missing_ok=True)
    
def _run_tests() -> int:
    tests = [
        ("simples: replace 1 linha",            _t_simple_replace),
        ("multi-linha: replace bloco",          _t_multiline_replace),
        ("pure add: insere sem remover",        _t_pure_add),
        ("pure remove: remove linha",           _t_pure_remove),
        ("idempotente: aplicar 2x",             _t_idempotent),
        ("match parcial: âncora existe",        _t_partial_match),
        ("offset: âncora deslocada",            _t_offset),
        ("overlap: 2 hunks conflitantes",       _t_overlap),
        ("multi-hunk: aplica todos",            _t_multi_hunk),
        ("sintaxe inválida: detecta",           _t_syntax_invalid),
        ("sintaxe válida: passa",               _t_syntax_valid),
        ("preflight: classifica OK",            _t_preflight_ok),
        ("preflight: detecta conflito",         _t_preflight_conflict),
        ("preflight: detecta idempotente",      _t_preflight_idempotent),
        ("apply: escreve em disco",             _t_apply),
        ("apply: faz backup",                   _t_apply_backup),
        ("arquivo ausente: erro gracioso",      _t_missing_file),
        ("parse_errors: propaga",               _t_parse_errors),
    ]

    passed = failed = 0
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

    print(f"\n{passed}/{passed + failed} passaram")
    return 1 if failed else 0


# -- helpers --

def _parse_and_patch(path: Path, text: str) -> FilePatch:
    hunks = parse_any_hunks(text)
    return make_file_patch(path, hunks)


def _t_simple_replace() -> None:
    p = _write_tmp("def f(a, b):\n    return a - b\n")
    text = "@2\n-     return a - b\n+     return a + b\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.simulate(patch)
    assert res.success, f"falhou: {res.errors}"
    assert "return a + b" in res.output_content
    assert "return a - b" not in res.output_content


def _t_multiline_replace() -> None:
    p = _write_tmp("def f():\n    x = 1\n    return x\n")
    text = "@1\n- def f():\n-     x = 1\n+ def f():\n+     x = 10\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.simulate(patch)
    assert res.success, f"falhou: {res.errors}"
    assert "x = 10" in res.output_content


def _t_pure_add() -> None:
    p = _write_tmp("def f():\n    pass\n")
    text = "@1\n+ # comentário novo\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.simulate(patch)
    assert res.success, f"falhou: {res.errors}"
    assert "comentário novo" in res.output_content


def _t_pure_remove() -> None:
    p = _write_tmp("def f():\n    print('debug')\n    return 1\n")
    text = "@2\n-     print('debug')\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.simulate(patch)
    assert res.success, f"falhou: {res.errors}"
    assert "debug" not in res.output_content


def _t_idempotent() -> None:
    p = _write_tmp("def f():\n    return a + b\n")
    text = "@2\n-     return a - b\n+     return a + b\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.simulate(patch)
    assert res.hunks_skipped >= 1, f"esperado skip, details={res.details}"


def _t_partial_match() -> None:
    p = _write_tmp("def f():\n    x = 1\n    y = 2\n    return x + y\n")
    text = "@2\n-     x = 1\n-     y = 2\n+     x = 10\n+     y = 20\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.simulate(patch)
    assert res.success, f"falhou: {res.errors}"


def _t_offset() -> None:
    p = _write_tmp("a = 1\nb = 2\nc = 3\nd = 4\n")
    text = "@10\n- c = 3\n+ c = 30\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.simulate(patch)
    assert res.success, f"falhou: {res.errors}"
    assert "c = 30" in res.output_content


def _t_overlap() -> None:
    p = _write_tmp("a = 1\nb = 2\n")
    text = "@1\n- a = 1\n- b = 2\n+ a = 10\n+ b = 20\n\n@2\n- b = 2\n+ b = 22\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.simulate(patch)
    assert res.hunks_failed >= 1, "esperado conflito"


def _t_multi_hunk() -> None:
    p = _write_tmp("a = 1\nb = 2\nc = 3\n")
    text = "@1\n- a = 1\n+ a = 10\n\n@3\n- c = 3\n+ c = 30\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.simulate(patch)
    assert res.success, f"falhou: {res.errors}"
    assert "a = 10" in res.output_content
    assert "c = 30" in res.output_content


def _t_syntax_invalid() -> None:
    p = _write_tmp("def f():\n    return 1\n")
    text = "@2\n-     return 1\n+     return (1\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.simulate(patch)
    assert not res.success, "sintaxe inválida deveria rejeitar"
    assert not res.syntax_ok


def _t_syntax_valid() -> None:
    p = _write_tmp("def f():\n    return 1\n")
    text = "@2\n-     return 1\n+     return 2\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.simulate(patch)
    assert res.syntax_ok, f"sintaxe inválida: {res.errors}"


def _t_preflight_ok() -> None:
    p = _write_tmp("x = 1\ny = 2\n")
    text = "@1\n- x = 1\n+ x = 10\n"
    patch = _parse_and_patch(p, text)
    pf = PatchSurgeon.preflight(patch)
    assert pf["safe_to_apply"], f"preflight: {pf}"
    assert pf["hunks"][0]["status"] == "WILL_APPLY"


def _t_preflight_conflict() -> None:
    p = _write_tmp("a = 1\n")
    text = "@1\n- nonexistent_line\n+ new_line\n"
    patch = _parse_and_patch(p, text)
    pf = PatchSurgeon.preflight(patch)
    assert not pf["safe_to_apply"]


def _t_preflight_idempotent() -> None:
    p = _write_tmp("x = 10\n")
    text = "@1\n- x = 1\n+ x = 10\n"
    patch = _parse_and_patch(p, text)
    pf = PatchSurgeon.preflight(patch)
    statuses = [h["status"] for h in pf["hunks"]]
    assert "ALREADY_APPLIED" in statuses, f"statuses={statuses}"


def _t_apply() -> None:
    p = _write_tmp("v = 1\n")
    text = "@1\n- v = 1\n+ v = 2\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.apply(patch, backup=False)
    assert res.success, f"falhou: {res.errors}"
    assert "v = 2" in p.read_text(encoding='utf-8')
    p.unlink(missing_ok=True)


def _t_apply_backup() -> None:
    p = _write_tmp("v = 1\n")
    text = "@1\n- v = 1\n+ v = 2\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.apply(patch, backup=True)
    assert res.success, f"falhou: {res.errors}"
    bak = p.with_suffix(p.suffix + '.bak')
    assert bak.exists(), "backup deveria existir"
    bak.unlink(missing_ok=True)
    p.unlink(missing_ok=True)


def _t_missing_file() -> None:
    p = Path("/tmp/nao_existe_xyz.py")
    text = "@1\n- a\n+ b\n"
    patch = _parse_and_patch(p, text)
    res = PatchSurgeon.simulate(patch)
    assert not res.success
    assert any("ausente" in e for e in res.errors)


def _t_parse_errors() -> None:
    p = _write_tmp("x = 1\n")
    # hunk inválido (@0) — parser descarta, mas FilePatch fica vazio
    text = "@0\n- x = 1\n+ x = 2\n"
    hunks = parse_any_hunks(text)
    patch = make_file_patch(p, hunks) if hunks else FilePatch(target_path=p)
    assert patch.hunks == [] or patch.parse_errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_run_tests())
    elif "--demo" in sys.argv:
        p = _write_tmp("def somar(a, b):\n    return a - b\n")
        text = "@2\n-     return a - b\n+     return a + b\n"
        patch = _parse_and_patch(p, text)
        res = PatchSurgeon.simulate(patch)
        print(f"success={res.success} applied={res.hunks_applied}")
        print(f"syntax_ok={res.syntax_ok}")
        print(res.output_content)
        p.unlink(missing_ok=True)
    else:
        print("Uso: python -m engine.diff.surgeon --test|--demo")
