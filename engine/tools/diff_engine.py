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
) -> str:
    """Prompt cirúrgico: o modelo vê só o símbolo-alvo e devolve a versão
    reescrita completa (bloco Python), não um patch @N.

    A saída é convertida em um único DiffHunk que substitui
    [start_line, end_line] no arquivo original.
    """
    system = (
        "Você é um assistente de edição de código cirúrgica. "
        f"Vou te dar APENAS o {symbol_kind} `{symbol_name}` extraído de um "
        "arquivo maior. Sua tarefa é REESCREVER esse símbolo conforme a "
        "instrução e devolver o bloco Python completo, substituível.\n\n"
        "Regras:\n"
        "- Devolva APENAS o bloco Python dentro de ```python ... ``` "
        "(ou [code-begin]...[code-end]).\n"
        "- Mantenha o MESMO nome e assinatura, salvo se a instrução pedir "
        "alteração explícita.\n"
        "- Preserve docstring e type hints quando existirem.\n"
        "- Sem explicações antes ou depois do bloco.\n"
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
    """Se o modelo reescreveu uma função, usa o AST para localizar e criar o hunk."""
    clean_code = _clean_model_output(text)
    try:
        model_tree = ast.parse(clean_code)
        orig_tree  = ast.parse(original_content)
    except SyntaxError:
        return []

    orig_map: dict[str, tuple[int, int]] = {}
    for node in ast.walk(orig_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            orig_map[node.name] = (node.lineno, getattr(node, "end_lineno", node.lineno))

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
) -> tuple[str, str | None]:
    """Chama o modelo (server se online; senão direto).
    Retorna (raw, error_msg_or_None)."""
    from engine.tools.server_client import is_server_online, query as server_query
    if is_server_online():
        s_resp = server_query(prompt, max_tokens=max_tokens)
        if not s_resp or s_resp.get("error"):
            err = s_resp.get("error") if s_resp else "servidor offline"
            return "", f"inferência no servidor falhou: {err}"
        return str(s_resp.get("output", "")).strip(), None

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
        try: bridge.shutdown()
        except Exception: pass


def _try_surgical_path(
    *,
    path: Path,
    content: str,
    instruction: str,
    symbol_mode: str,
    max_tokens: int,
    temperature: float,
    t0: float,
) -> "DiffResult | list[DiffHunk] | None":
    """Tenta resolver símbolo e produzir um único hunk cirúrgico.

    Retorno:
      - DiffResult      → erro terminal (symbol_mode='on' e falhou)
      - list[DiffHunk]  → sucesso; caller continua com apply pipeline
      - None            → fallback para whole-file (modo 'auto')
    """
    import ast
    try:
        from engine.tools.symbol_indexer import load_or_build as _idx_load_or_build
        from engine.tools.symbol_resolver import (
            resolve, pick_best, source_snippet, format_matches,
        )
    except ImportError:
        return None   # F5.1 indisponível → fallback silencioso

    try:
        index = _idx_load_or_build(path)
    except Exception:
        return None

    matches = resolve(instruction, index, scope=path)
    best = pick_best(matches)

    if best is None or best.confidence != "high":
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
            )
        return None

    n_lines = best.symbol.end_line - best.symbol.start_line + 1
    if n_lines > 200:
        if symbol_mode == "on":
            return DiffResult(
                success=False,
                errors=[
                    f"Símbolo {best.symbol.name} tem {n_lines} linhas (>200). "
                    "Grande demais para modo cirúrgico — use sem --symbol."
                ],
                elapsed_s=round(time.monotonic() - t0, 2),
            )
        return None

    snippet = source_snippet(best.symbol, path)
    if not snippet.strip():
        return None

    surgical_max = min(1024, max(384, n_lines * 8))
    prompt = build_prompt_surgical(
        snippet, best.symbol.name, best.symbol.kind, instruction,
    )
    raw, err = _infer_prompt(prompt, surgical_max, temperature)
    if err:
        if symbol_mode == "on":
            return DiffResult(
                success=False,
                errors=[f"(surgical) {err}"],
                elapsed_s=round(time.monotonic() - t0, 2),
            )
        return None

    new_code = _extract_python_block(raw)
    if not new_code:
        if symbol_mode == "on":
            return DiffResult(
                success=False,
                raw_output=raw,
                errors=["Modelo (surgical) não retornou bloco Python reconhecível."],
                elapsed_s=round(time.monotonic() - t0, 2),
            )
        return None

    try:
        ast.parse(new_code)
    except SyntaxError as exc:
        if symbol_mode == "on":
            return DiffResult(
                success=False,
                raw_output=raw,
                errors=[f"Modelo retornou código inválido: {exc}"],
                elapsed_s=round(time.monotonic() - t0, 2),
            )
        return None

    # F5.2 Guard C: output cirúrgico suspeito (perdeu corpo do símbolo).
    # Heurística: se < 30% do tamanho original, provavelmente o modelo
    # truncou (ex.: só docstring, corpo sumiu).
    ratio = len(new_code.strip()) / max(1, len(snippet.strip()))
    if ratio < 0.30 and n_lines > 3:
        if symbol_mode == "on":
            return DiffResult(
                success=False,
                raw_output=raw,
                errors=[
                    f"Modelo retornou apenas {int(ratio*100)}% do tamanho "
                    f"original de '{best.symbol.name}' ({n_lines} linhas). "
                    "Provável truncamento — tente instrução mais específica "
                    "ou use --symbol-auto com arquivo maior."
                ],
                elapsed_s=round(time.monotonic() - t0, 2),
            )
        return None

    snippet_lines = snippet.splitlines()
    new_lines = new_code.rstrip("\n").splitlines()
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
        return [l.rstrip() for l in lines]

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

    # ── Prioridade 1: hunks pré-computados (fase 2 do surgical) ──
    if hunks_override is not None:
        return _apply_and_finalize(
            path=path, content=content, hunks=hunks_override,
            raw=raw_output_override or "[surgical — hunks pré-computados]",
            t0=t0, apply=apply, verify=False,
        )

    # ── Prioridade 2: raw_output pré-computado (fase 2 do whole-file) ──
    if raw_output_override is not None:
        hunks = parse_diff(raw_output_override, original_content=content)
        return _apply_and_finalize(
            path=path, content=content, hunks=hunks, raw=raw_output_override,
            t0=t0, apply=apply, verify=verify,
        )

    # ── Prioridade 3: modo cirúrgico (fase 1) ──
    if symbol_mode in ("auto", "on"):
        surgical = _try_surgical_path(
            path=path, content=content, instruction=instruction,
            symbol_mode=symbol_mode, max_tokens=max_tokens,
            temperature=temperature, t0=t0,
        )
        if isinstance(surgical, DiffResult):
            return surgical
        if isinstance(surgical, list):
            return _apply_and_finalize(
                path=path, content=content, hunks=surgical,
                raw="[surgical — bloco Python substituído]",
                t0=t0, apply=apply, verify=False,
            )
        # surgical is None → cai no fallback

    # ── Prioridade 4: whole-file (padrão) ──
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
    raw, infer_err = _infer_prompt(prompt, max_tokens, temperature)
    if infer_err:
        return DiffResult(
            success=False,
            errors=[infer_err],
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    hunks = parse_diff(raw, original_content=content)
    return _apply_and_finalize(
        path=path, content=content, hunks=hunks, raw=raw,
        t0=t0, apply=apply, verify=verify,
    )
