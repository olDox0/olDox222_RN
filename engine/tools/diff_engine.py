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
    raw_output_override: str | None = None,   # ← NOVO
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

    context = ""
    if consult and raw_output_override is None:
        try:
            from engine.tools.consult_bridge import ConsultBridge
            cb = ConsultBridge()
            if cb.is_available():
                results = cb.search(instruction, limit=2)
                if results:
                    context = cb.format_context(results, max_chars=1500)
        except Exception:
            pass

    # ── Geração (ou override) ────────────────────────────────
    if raw_output_override is not None:
        raw = raw_output_override
    else:
        prompt = build_prompt(content, instruction, context=context)
        from engine.tools.server_client import is_server_online, query as server_query
        if is_server_online():
            s_resp = server_query(prompt, max_tokens=max_tokens)
            if s_resp and not s_resp.get("error"):
                raw = str(s_resp.get("output", "")).strip()
            else:
                err_msg = (
                    s_resp.get("error") if s_resp
                    else "servidor offline ou resposta vazia"
                )
                return DiffResult(
                    success=False,
                    errors=[f"inferência no servidor falhou: {err_msg}"],
                    elapsed_s=round(time.monotonic() - t0, 2),
                )
        else:
            from engine.core.llm_bridge import BridgeConfig, SiCDoxBridge
            cfg = BridgeConfig()
            cfg.temperature = temperature
            bridge = SiCDoxBridge(cfg)
            try:
                bridge._ensure_loaded()
                call_res = bridge._call_engine(prompt, max_tokens=max_tokens)
                raw = str(call_res.get("text", "")).strip()
            except Exception as exc:
                return DiffResult(
                    success=False,
                    errors=[f"inferência falhou: {exc}"],
                    elapsed_s=round(time.monotonic() - t0, 2),
                )
            finally:
                try: bridge.shutdown()
                except Exception: pass

    # ── Resto do função: parse + apply (sem mudanças) ────────
    hunks = parse_diff(raw, original_content=content)
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

    # B-NOOP: todos os hunks são no-op (removed == added) → nada a fazer
    if all(h.removed == h.added for h in hunks):
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
            
            # Salva backup físico .bak antes de qualquer alteração (OSL-20)
            bak_path = path.with_suffix(path.suffix + ".bak")
            bak_path.write_text(backup_content, encoding="utf-8")

            # Escreve o patch no arquivo alvo
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
