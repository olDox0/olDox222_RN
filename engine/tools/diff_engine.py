# -*- coding: utf-8 -*-
from __future__ import annotations
import ast, os, time, re
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class DiffHunk:
    line: int
    removed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)

@dataclass
class DiffResult:
    success: bool
    raw_output: str = ""
    hunks: list[DiffHunk] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0
    applied: bool = False
    no_op: bool = False
    surgical_trace: dict | None = None    # F5.5b

def build_prompt(file_content: str, instruction: str, context: str = "") -> str:
    system = (
        "Você é um assistente de edição de código cirúrgica. Escolha UMA das formas para responder:\n\n"
        "Opção 1 — Patch de linha (@N):\n"
        "@14\n"
        "-     issues: list[str] = []\n"
        "+     issues: tuple[str, ...] = ()\n\n"
        "Opção 2 — Apenas a função/bloco corrigido em Python:\n"
        "```python\n"
        "def nome_da_funcao(...):\n"
        "    # código corrigido com a alteração solicitada\n"
        "```\n\n"
        "Apenas o código ou patch, sem explicações conversacionais adicionais."
    )
    user_parts = []
    if context:
        user_parts.append(context)
    user_parts.append(f"Código:\n```python\n{file_content.strip()}\n```")
    user_parts.append(f"Tarefa: {instruction}")
    user = "\n\n".join(user_parts)
    return (
        f"<|im_start|>system\n{system}<|im_end|>\n"
        f"<|im_start|>user\n{user}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

def build_prompt_surgical(
    snippet: str,
    symbol_name: str,
    symbol_kind: str,
    instruction: str,
    start_line: int = 1,
    end_line: int = 0,
) -> str:
    """Prompt cirúrgico — formato bloco Python (NÃO @N).

    Qwen 0.5B comprovadamente copia templates @N literalmente em vez de
    preencher valores. Bloco ```python``` + `_parse_ast_replacements`
    funciona para símbolos < 100 linhas.

    F5.8: removidos exemplos @N e referências "linha antiga/linha nova".
    """
    if not end_line:
        end_line = start_line + len(snippet.splitlines()) - 1

    system = (
        "Você é um assistente de edição de código. "
        f"Vou te dar o {symbol_kind} `{symbol_name}` extraído de um "
        "arquivo maior. Reescreva-o conforme a instrução.\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "- Devolva APENAS o bloco Python dentro de ```python ... ```.\n"
        f"- Mantenha o MESMO nome `{symbol_name}` e assinatura.\n"
        "- Preserve docstring e type hints quando existirem.\n"
        "- Sem explicações antes ou depois.\n"
        "- Sem `print(...)` fora da função.\n"
        "- Sem `if __name__` ou `# Example usage:`.\n"
        "- NUNCA duplique a definição.\n"
        "- O bloco deve ser sintaticamente válido."
    )
    user = (
        f"```python\n{snippet.strip()}\n```\n\n"
        f"Tarefa: {instruction}"
    )
    return (
        f"<|im_start|>system\n{system}<|im_end|>\n"
        f"<|im_start|>user\n{user}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


def _extract_python_block(raw: str) -> str:
    """Extrai bloco Python de ```python```, [code-begin]...[code-end]
    ou código bare começando com def/class/@."""
    from engine.thinking.code_hook import _extract_code, _extract_markdown_code
    code = _extract_code(raw) or _extract_markdown_code(raw)
    if code:
        return code
    stripped = (raw or "").strip()
    if stripped.startswith(("def ", "class ", "async def ", "import ", "from ", "@")):
        return stripped
    return ""

def _clean_model_output(raw: str) -> str:
    txt = (raw or "").strip()
    if "```" in txt:
        m = re.search(r"```(?:diff|python)?\s*\n?(.*?)```", txt, re.DOTALL)
        if m and m.group(1).strip():
            return m.group(1).strip()
        parts = txt.split("```", 1)
        if len(parts) > 1:
            after = parts[1].strip()
            after = re.sub(r"^(?:diff|python)\s*\n?", "", after, flags=re.IGNORECASE)
            if after:
                return after
    return txt

def _parse_line_hunks(text: str) -> list[DiffHunk]:
    hunks: list[DiffHunk] = []
    current: DiffHunk | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        stripped = line.strip()
        if stripped.startswith("@"):
            m = re.match(r"^@+?\s*(\d+)", stripped)
            if m:
                n = int(m.group(1))
                if current is not None and (current.removed or current.added):
                    hunks.append(current)
                current = DiffHunk(line=n)
                continue
        if current is not None:
            if stripped.startswith("-") and not stripped.startswith("---"):
                current.removed.append(line[1:].lstrip(" "))
            elif stripped.startswith("+") and not stripped.startswith("+++"):
                current.added.append(line[1:].lstrip(" "))
    if current is not None and (current.removed or current.added):
        hunks.append(current)
    return hunks

def _parse_ast_replacements(text: str, original_content: str) -> list[DiffHunk]:
    """Modelo reescreveu função → localiza via AST e cria o hunk.

    Defesas em camadas:
      - Guard 0: rejeita output com marcadores de template (@N, linha antiga)
      - Guard 1: rejeita print() e if __name__ no top-level
      - Guard 2: rejeita duplicatas de definição (modelo quebrado)
    """
    clean_code = _clean_model_output(text)

    # ── Guard 0: modelo confundiu formato ──
    _BAD_MARKERS = (
        "@N", "@n\n", "linha antiga", "linha nova",
        "Formato OBRIGATÓRIO", "═══ EXEMPLO", "Devolva o patch",
    )
    if any(m in clean_code for m in _BAD_MARKERS):
        return []

    try:
        model_tree = ast.parse(clean_code)
        orig_tree = ast.parse(original_content)
    except SyntaxError:
        return []

    # ── Guard 1: código de teste/exemplo no top-level ──
    for stmt in model_tree.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            func = stmt.value.func
            if isinstance(func, ast.Name) and func.id == "print":
                return []
        if isinstance(stmt, ast.If):
            return []

    # ── Guard 2: duplicatas de definição ──
    model_defs: dict[str, int] = {}
    for stmt in model_tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            model_defs[stmt.name] = model_defs.get(stmt.name, 0) + 1
    for name, count in model_defs.items():
        if count > 1:
            return []

    orig_map: dict[str, tuple[int, int]] = {}
    for node in ast.walk(orig_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            orig_map[node.name] = (
                node.lineno, getattr(node, "end_lineno", node.lineno)
            )

    orig_lines = original_content.splitlines()
    model_lines = clean_code.splitlines()
    hunks: list[DiffHunk] = []

    for node in model_tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in orig_map:
                start_l, end_l = orig_map[node.name]
                new_start = node.lineno - 1
                new_end = getattr(node, "end_lineno", len(model_lines))
                new_func_lines = model_lines[new_start:new_end]

                hunks.append(DiffHunk(
                    line=start_l,
                    removed=orig_lines[start_l - 1 : end_l],
                    added=new_func_lines,
                ))
    return hunks

def parse_diff(text: str, original_content: str = "") -> list[DiffHunk]:
    clean = _clean_model_output(text)
    if not clean:
        return []

    # 1. Tenta formato @N
    hunks = _parse_line_hunks(clean)
    if hunks:
        return hunks

    # 2. Tenta substituição cirúrgica de funções via AST
    if original_content:
        hunks = _parse_ast_replacements(text, original_content)
        if hunks:
            return hunks

    return []

def apply_hunks(lines: list[str], hunks: list[DiffHunk]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    for hunk in sorted(hunks, key=lambda h: h.line, reverse=True):
        idx = hunk.line - 1
        if idx < 0 or idx >= len(lines):
            errors.append(f"@{hunk.line}: fora do arquivo")
            continue
        n_removed = len(hunk.removed)
        if n_removed > 0 and not hunk.added:
            lines = lines[:idx] + hunk.removed + lines[idx + n_removed:]
            continue
        actual = lines[idx:idx + n_removed] if n_removed > 0 else []
        if n_removed > 0 and [l.rstrip() for l in actual] != [l.rstrip() for l in hunk.removed]:
            errors.append(f"@{hunk.line}: conteúdo original não bate")
            continue
        lines = lines[:idx] + hunk.added + lines[idx + n_removed:]
    return lines, errors

def _line_ending(content: str) -> tuple[str, bool]:
    has_trailing = content.endswith(("\n", "\r\n"))
    return ("\r\n" if "\r\n" in content else "\n"), has_trailing

def _infer_prompt(
    prompt: str,
    max_tokens: int,
    temperature: float,
    bridge=None,
) -> tuple[str, str | None]:
    """Chama o modelo. Se `bridge` for passado, reusa (sem shutdown)."""
    from engine.tools.server_client import is_server_online, query as server_query
    if is_server_online():
        s_resp = server_query(prompt, max_tokens=max_tokens)
        if not s_resp or s_resp.get("error"):
            err = s_resp.get("error") if s_resp else "servidor offline"
            return "", f"inferência no servidor falhou: {err}"
        return str(s_resp.get("output", "")).strip(), None

    own_bridge = bridge is None
    if own_bridge:
        from engine.core.llm_bridge import BridgeConfig, SiCDoxBridge
        cfg = BridgeConfig()
        cfg.temperature = temperature
        bridge = SiCDoxBridge(cfg)

    try:
        bridge._ensure_loaded()
        call_res = bridge._call_engine(prompt, max_tokens=max_tokens)
        return str(call_res.get("text", "")).strip(), None
    except Exception as exc:
        return "", f"inferência falhou: {exc}"
    finally:
        if own_bridge:
            try: bridge.shutdown()
            except Exception: pass

def _instruction_looks_symbolic(text: str) -> bool:
    """True se instrução menciona identificador que parece nome de símbolo.

    Critério:
      - começa com '_' (≥4 chars): `_fmt_ms`, `_run_fix`
      - tem snake_case: `session_cmd`, `cache_dir`
      - tem camelCase: `GoalResult`, `SiCDoxExecutive`
    Não conta se for stopword PT-BR (mesmo critério do symbol_resolver).
    """
    if not text:
        return False
    try:
        from engine.tools.symbol_resolver import _STOPWORDS
    except ImportError:
        _STOPWORDS = frozenset()

    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text):
        low = t.lower()
        if low in _STOPWORDS:
            continue
        if t.startswith("_") and len(t) >= 4:
            return True
        if "_" in t and not t.startswith("__"):
            return True
        if re.search(r"[a-z][A-Z]", t):
            return True
    return False

def _try_surgical_path(
    *,
    path: Path,
    content: str,
    instruction: str,
    symbol_mode: str,
    max_tokens: int,
    temperature: float,
    t0: float,
    bridge=None,
    trace: dict | None = None,
) -> "DiffResult | list[DiffHunk] | None":
    """Tenta resolver símbolo e produzir patch cirúrgico.

    Ordem:
      1. resolve símbolo (filtro por arquivo-alvo)
      2. template determinístico (docstring/comment/rename)
      3. limite 100 linhas para o Qwen 0.5B
      4. modelo (prompt @N)
      5. guard A (regurgitação de template)
      6. parse_diff (@N) prioritário
      7. fallback bloco Python (compatibilidade)
    """
    import ast as _ast

    if trace is None:
        trace = {}
    trace["path"] = str(path)
    trace["instruction"] = instruction
    trace["symbol_mode"] = symbol_mode
    trace["matches_count"] = 0
    trace["resolved"] = None
    trace["resolved_file"] = None
    trace["resolved_lines"] = None
    trace["infer_raw_len"] = 0
    trace["infer_raw_preview"] = ""
    trace["outcome"] = "start"

    try:
        from engine.tools.symbol_indexer import load_or_build as _idx_load_or_build
        from engine.tools.symbol_resolver import (
            resolve, pick_best, source_snippet, format_matches,
        )
    except ImportError:
        trace["outcome"] = "import_error"
        return None

    try:
        index = _idx_load_or_build(path)
    except Exception as exc:
        trace["outcome"] = "index_error"
        trace["error"] = str(exc)
        return None

    matches = resolve(instruction, index, scope=path)

    try:
        _target_resolved = Path(path).resolve()
    except OSError:
        _target_resolved = Path(path)
    matches = [
        m for m in matches
        if Path(m.file_path).resolve() == _target_resolved
    ]
    trace["matches_count"] = len(matches)
    trace["matches"] = [
        (m.symbol.name, round(m.score, 2), m.confidence)
        for m in matches
    ]

    best = pick_best(matches)

    if best is not None:
        trace["resolved"] = best.symbol.name
        trace["resolved_file"] = str(best.file_path)
        trace["resolved_lines"] = (best.symbol.start_line, best.symbol.end_line)

    if best is None or best.confidence != "high":
        if best is None:
            trace["outcome"] = "no_match"
        else:
            trace["outcome"] = f"low_confidence_{best.confidence}"

        if symbol_mode == "on":
            if best is None:
                err_lines = [
                    f"Não identifiquei símbolo-alvo em: '{instruction}'",
                    "Candidatos próximos:",
                    format_matches(matches[:5]) if matches else "  (nenhum)",
                ]
            else:
                err_lines = [
                    f"Match ambíguo: {best.symbol.name} "
                    f"(score={best.score:.2f}, confiança={best.confidence})",
                    "Use --symbol-auto para fallback automático.",
                ]
            return DiffResult(
                success=False,
                errors=err_lines,
                elapsed_s=round(time.monotonic() - t0, 2),
                surgical_trace=trace,
            )

        if best is None and _instruction_looks_symbolic(instruction):
            trace["outcome"] = "symbol_not_in_target"
            return DiffResult(
                success=False,
                errors=[
                    f"Instrução menciona símbolo não encontrado em '{path.name}'.",
                    f"  Símbolo citado: {instruction}",
                    "Use `orn grep <nome>` para localizar o arquivo correto.",
                    "Ou reescreva a instrução sem referência a símbolo específico.",
                ],
                elapsed_s=round(time.monotonic() - t0, 2),
                surgical_trace=trace,
            )
        return None

    n_lines = best.symbol.end_line - best.symbol.start_line + 1
    trace["resolved_lines_count"] = n_lines

    snippet = source_snippet(best.symbol, path)
    trace["snippet_chars"] = len(snippet)
    if not snippet.strip():
        trace["outcome"] = "empty_snippet"
        return None

    # ── Template determinístico (antes do modelo) ─────────────
    try:
        from engine.tools.fix_templates import apply_template
        tpl = apply_template(
            instruction=instruction,
            snippet=snippet,
            symbol_name=best.symbol.name,
            symbol_kind=best.symbol.kind,
            start_line=best.symbol.start_line,
        )
    except Exception as exc:
        tpl = None
        trace["template_error"] = str(exc)

    if tpl is not None:
        trace["outcome"] = f"ok_template_{tpl.name}"
        trace["template_description"] = tpl.description
        snippet_lines = snippet.splitlines()
        new_lines = tpl.new_code.rstrip("\n").splitlines()
        trace["hunks_count"] = 1
        trace["added_lines"] = len(new_lines)
        trace["removed_lines"] = len(snippet_lines)
        return [DiffHunk(
            line=best.symbol.start_line,
            removed=snippet_lines,
            added=new_lines,
        )]

    # ── Limite de tamanho (Qwen 0.5B) ─────────────────────────
    if n_lines > 100:
        trace["outcome"] = "symbol_too_large"
        if symbol_mode == "on":
            return DiffResult(
                success=False,
                errors=[
                    f"Símbolo {best.symbol.name} tem {n_lines} linhas (>100).",
                    "Cirúrgico não escala para símbolos grandes no Qwen 0.5B.",
                    "Sugestões:",
                    f"  • refatore {best.symbol.name} em subfunções < 60 linhas",
                    "  • ou reformule com template "
                    "(docstring, comentário no topo, rename)",
                    "  • ou use `orn fix <arquivo>` sem --symbol (whole-file)",
                ],
                elapsed_s=round(time.monotonic() - t0, 2),
                surgical_trace=trace,
            )
        return None

    surgical_max = min(1024, max(256, n_lines * 6 + 128))
    trace["surgical_max_tokens"] = surgical_max

    prompt = build_prompt_surgical(
        snippet, best.symbol.name, best.symbol.kind, instruction,
        start_line=best.symbol.start_line,
        end_line=best.symbol.end_line,
    )
    trace["prompt_chars"] = len(prompt)

    raw, err = _infer_prompt(prompt, surgical_max, temperature, bridge=bridge)
    if err:
        trace["outcome"] = "infer_error"
        trace["infer_error"] = err
        if symbol_mode == "on":
            return DiffResult(
                success=False,
                errors=[f"(surgical) {err}"],
                elapsed_s=round(time.monotonic() - t0, 2),
                surgical_trace=trace,
            )
        return None

    trace["infer_raw_len"] = len(raw or "")
    trace["infer_raw_preview"] = (raw or "")[:800]

    # ── Guard A: regurgitação de template ─────────────────────
    if raw:
        _REP_MARKERS = ("linha antiga", "linha nova", "Devolva o patch")
        _rep_hit = any(m in raw for m in _REP_MARKERS)
        if not _rep_hit:
            _rep_hit = bool(re.search(r"^@[A-Za-z]", raw.strip(), re.MULTILINE))
        if _rep_hit:
            trace["outcome"] = "model_regurgitated_template"
            return DiffResult(
                success=False,
                raw_output=raw,
                errors=[
                    "Modelo (Qwen 0.5B) copiou o template do prompt em vez "
                    "de produzir um diff real.",
                    "Limitação do modelo — não é bug do sistema.",
                    "Sugestões:",
                    "  • use templates determinísticos "
                    "(docstring, comentário no topo, rename)",
                    "  • para símbolos pequenos, tente reformular a instrução",
                ],
                elapsed_s=round(time.monotonic() - t0, 2),
                surgical_trace=trace,
            )

    # ── parse_diff (@N) prioritário ───────────────────────────
    diff_hunks = parse_diff(raw, original_content=content)
    if diff_hunks:
        s_start = best.symbol.start_line
        s_end = best.symbol.end_line
        in_range = all(s_start <= h.line <= s_end for h in diff_hunks)
        if in_range:
            trace["outcome"] = "ok_diff_format"
            trace["hunks_count"] = len(diff_hunks)
            trace["added_lines"] = sum(len(h.added) for h in diff_hunks)
            trace["removed_lines"] = sum(len(h.removed) for h in diff_hunks)
            return diff_hunks
        trace["outcome"] = "hunk_outside_symbol"
        trace["hunk_out_of_range"] = [
            (h.line, s_start, s_end) for h in diff_hunks
        ]
        if symbol_mode == "on":
            return DiffResult(
                success=False,
                raw_output=raw,
                errors=[
                    f"Modelo gerou @N fora do range do símbolo "
                    f"({s_start}-{s_end}). Provável alucinação.",
                    "Use -v para ver o raw.",
                ],
                elapsed_s=round(time.monotonic() - t0, 2),
                surgical_trace=trace,
            )
        return None

    # ── Fallback: bloco Python ────────────────────────────────
    trace["diff_format_failed"] = True
    new_code = _extract_python_block(raw)
    if not new_code:
        trace["outcome"] = "no_patch_no_block"
        if symbol_mode == "on":
            return DiffResult(
                success=False,
                raw_output=raw,
                errors=[
                    "Modelo (surgical) não retornou nem patch @N "
                    "nem bloco Python reconhecível.",
                    "Use -v para ver o raw.",
                ],
                elapsed_s=round(time.monotonic() - t0, 2),
                surgical_trace=trace,
            )
        return None

    try:
        _ast.parse(new_code)
    except SyntaxError as exc:
        trace["outcome"] = "syntax_error"
        trace["syntax_error"] = str(exc)
        if symbol_mode == "on":
            return DiffResult(
                success=False,
                raw_output=raw,
                errors=[f"Modelo retornou código inválido: {exc}"],
                elapsed_s=round(time.monotonic() - t0, 2),
                surgical_trace=trace,
            )
        return None

    ratio = len(new_code.strip()) / max(1, len(snippet.strip()))
    trace["output_ratio"] = round(ratio, 3)
    if ratio < 0.30 and n_lines > 3:
        trace["outcome"] = "guard_c_ratio"
        if symbol_mode == "on":
            return DiffResult(
                success=False,
                raw_output=raw,
                errors=[
                    f"Modelo retornou apenas {int(ratio*100)}% do tamanho "
                    f"original de '{best.symbol.name}' ({n_lines} linhas). "
                    "Provável truncamento — tente instrução mais específica."
                ],
                elapsed_s=round(time.monotonic() - t0, 2),
                surgical_trace=trace,
            )
        return None

    trace["outcome"] = "ok_block_format"
    snippet_lines = snippet.splitlines()
    new_lines = new_code.rstrip("\n").splitlines()
    trace["hunks_count"] = 1
    trace["added_lines"] = len(new_lines)
    trace["removed_lines"] = len(snippet_lines)

    return [DiffHunk(
        line=best.symbol.start_line,
        removed=snippet_lines,
        added=new_lines,
    )]


def _apply_and_finalize(
    *,
    path: Path,
    content: str,
    hunks: list[DiffHunk],
    raw: str,
    t0: float,
    apply: bool,
    verify: bool,
) -> DiffResult:
    """Pipeline de aplicação compartilhado entre caminho cirúrgico e whole-file."""
    if not hunks:
        preview = (raw or "").strip()
        if len(preview) > 400:
            preview = preview[:400] + "\n[...truncado]"
        return DiffResult(
            success=False,
            raw_output=raw,
            errors=[
                "Modelo gerou resposta, mas não foi possível extrair "
                "um patch ou função reconhecível.",
                f"--- raw_output do modelo ({len(raw)} chars) ---\n{preview}",
            ],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    # F5.2 Guard B: no_op com normalização de trailing whitespace.
    # LLMs costumam reescrever com espaços extras; isso não é mudança real.
    def _norm(lines: list[str]) -> list[str]:
        return [re.sub(r"\s+", " ", l.strip()) for l in lines]

    if all(_norm(h.removed) == _norm(h.added) for h in hunks):
        return DiffResult(
            success=True,
            raw_output=raw,
            hunks=hunks,
            errors=[],
            elapsed_s=round(time.monotonic() - t0, 2),
            applied=False,
            no_op=True,
        )

    line_ending, has_trailing = _line_ending(content)
    lines = content.splitlines()
    new_lines, errors = apply_hunks(lines, hunks)
    applied = False
    if apply and not errors and new_lines != lines:
        new_content = line_ending.join(new_lines)
        if has_trailing:
            new_content += line_ending
        try:
            backup_content = path.read_text(encoding="utf-8", errors="replace")
            bak_path = path.with_suffix(path.suffix + ".bak")
            bak_path.write_text(backup_content, encoding="utf-8")
            path.write_text(new_content, encoding="utf-8")
            applied = True
            if verify:
                from engine.tools.sandbox import run_in_sandbox
                sb_res = run_in_sandbox(new_content, timeout_s=5)
                if not sb_res.success:
                    errors.append(f"Sandbox falhou: {sb_res.stderr.strip()}")
                    path.write_text(backup_content, encoding="utf-8")
                    applied = False
                    errors.append("Rollback executado: arquivo original restaurado.")
        except OSError as exc:
            errors.append(f"escrita falhou: {exc}")

    return DiffResult(
        success=not errors,
        raw_output=raw,
        hunks=hunks,
        errors=errors,
        elapsed_s=round(time.monotonic() - t0, 2),
        applied=applied,
    )


def generate_and_apply(
    file_path: Path | str,
    instruction: str,
    *,
    apply: bool = False,
    verify: bool = False,
    consult: bool = False,
    max_tokens: int = 512,
    temperature: float = 0.2,
    model_alias: str | None = None,
    raw_output_override: str | None = None,
    symbol_mode: str = "off",
    hunks_override: list[DiffHunk] | None = None,
) -> DiffResult:
    t0 = time.monotonic()
    path = Path(file_path)
    if not path.exists():
        return DiffResult(success=False, errors=[f"arquivo não existe: {path}"])
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return DiffResult(success=False, errors=[f"leitura falhou: {exc}"])

    if model_alias:
        os.environ["ORN_MODEL_ALIAS"] = model_alias

    # ── Prioridade 1: hunks_override ─────────────────────────────
    if hunks_override is not None:
        return _apply_and_finalize(
            path=path, content=content, hunks=hunks_override,
            raw=raw_output_override or "[surgical — hunks pré-computados]",
            t0=t0, apply=apply, verify=False,
        )

    # ── Prioridade 2: raw_output_override ────────────────────────
    if raw_output_override is not None:
        hunks = parse_diff(raw_output_override, original_content=content)
        return _apply_and_finalize(
            path=path, content=content, hunks=hunks, raw=raw_output_override,
            t0=t0, apply=apply, verify=verify,
        )

    # ── Bridge compartilhado ─────────────────────────────────────
    from engine.tools.server_client import is_server_online
    shared_bridge = None
    if not is_server_online():
        try:
            from engine.core.llm_bridge import BridgeConfig, SiCDoxBridge
            cfg = BridgeConfig()
            cfg.temperature = temperature
            shared_bridge = SiCDoxBridge(cfg)
        except Exception:
            shared_bridge = None

    surgical_trace: dict | None = None

    try:
        # ── Prioridade 3: surgical ──────────────────────────────
        if symbol_mode in ("auto", "on"):
            surgical_trace = {}
            surgical = _try_surgical_path(
                path=path, content=content, instruction=instruction,
                symbol_mode=symbol_mode, max_tokens=max_tokens,
                temperature=temperature, t0=t0,
                bridge=shared_bridge,
                trace=surgical_trace,
            )
            if isinstance(surgical, DiffResult):
                return surgical
            if isinstance(surgical, list):
                result = _apply_and_finalize(
                    path=path, content=content, hunks=surgical,
                    raw="[surgical — bloco Python substituído]",
                    t0=t0, apply=apply, verify=False,
                )
                result.surgical_trace = surgical_trace
                return result
            # None → fallback (trace preservado para anexar no final)

        # ── Prioridade 4: whole-file ─────────────────────────────
        context = ""
        if consult:
            try:
                from engine.tools.consult_bridge import ConsultBridge
                cb = ConsultBridge()
                if cb.is_available():
                    results = cb.search(instruction, limit=2)
                    if results:
                        context = cb.format_context(results, max_chars=1500)
            except Exception:
                pass

        prompt = build_prompt(content, instruction, context=context)
        raw, infer_err = _infer_prompt(
            prompt, max_tokens, temperature, bridge=shared_bridge,
        )
        if infer_err:
            res = DiffResult(
                success=False,
                errors=[infer_err],
                elapsed_s=round(time.monotonic() - t0, 2),
            )
            res.surgical_trace = surgical_trace
            return res

        hunks = parse_diff(raw, original_content=content)
        result = _apply_and_finalize(
            path=path, content=content, hunks=hunks, raw=raw,
            t0=t0, apply=apply, verify=verify,
        )
        result.surgical_trace = surgical_trace
        return result
    finally:
        if shared_bridge is not None:
            try: shared_bridge.shutdown()
            except Exception: pass
