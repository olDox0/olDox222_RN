
# [VULCAN-SKIP] Proteção contra introspecção Click
# -*- coding: utf-8 -*-
# engine/cli.p
"""
ORN — CLI (Ártemis)
Roteamento de comandos. Cada comando instancia o Executive e delega.

OSL-16: Este arquivo só registra grupos e comandos — sem lógica de negócio.
OSL-17: Responsabilidade única — roteamento de intenção do usuário.
OSL-7:  GoalResult verificado em cada comando antes de exibir resultado.
God: Ártemis — faz uma coisa, faz bem.

Comandos MVP:
  think   → chat livre com o Qwen               [Fase 1 — ATIVO]
  config  → exibe/verifica configuração          [Fase 1 — ATIVO]

Comandos futuros:
  audit   → análise AST + LLM                   [Fase 2]
  graph   → grafo de conceitos                   [Fase 2]
  brain   → estado do blackboard / memória       [Fase 3]
  fix     → sugestão de correção                 [Fase 4]
  gen     → geração de código                    [Fase 4]
"""

# [DOXOADE:VULCAN]
# [VULCAN-SKIP] Proteção contra introspecção Click
import os, sys; _b = os.path.join(os.getcwd(), ".doxoade", "vulcan", "bootstrap.py")
if os.path.exists(_b):
    import importlib.util as _u; _s = _u.spec_from_file_location("_vb", _b)
    _m = _u.module_from_spec(_s); _s.loader.exec_module(_m); _m.ignite(__file__, globals())
# [/DOXOADE:VULCAN]
import os
import sys
import json
import time
import re
import subprocess
from pathlib import Path
import click

from pathlib import Path

from engine.ui.display import Display

from engine.tools.server_client import query as server_query  # noqa: PLC0415
from engine.core.executive import SiCDoxExecutive  # noqa: PLC0415

#from engine.core.import_hook import install_lazy_imports
#install_lazy_imports([
#    "engine",
#    "doxoade",
#])

def _fmt_ms(value: float) -> str:
    value = float(value or 0)
    if value >= 1000:
        return f"{value / 1000.0:.3f}s"
    return f"{value:.3f}ms"


def _guess_lang_from_prompt(prompt: str) -> str:
    p = (prompt or "").lower()
    if "python" in p: return "python"
    if "javascript" in p or "js" in p: return "javascript"
    if "typescript" in p or "ts" in p: return "typescript"
    if "java" in p: return "java"
    if "c++" in p or "cpp" in p: return "cpp"
    if "c#" in p or "csharp" in p: return "csharp"
    return "python"


def _guess_function_name(prompt: str) -> str | None:
    p = (prompt or "").lower()
    tokens = re.findall(r"[a-z_][a-z0-9_]{2,}", p)
    stop = {
        "faca", "faça", "crie", "implemente", "codigo", "código", "em", "para",
        "python", "javascript", "typescript", "java", "funcao", "função",
        "algoritmo", "com", "sem", "uma", "um", "de", "do", "da",
    }
    for t in tokens:
        if t not in stop:
            return t
    return None


def _is_probably_python_snippet(code: str) -> bool:
    txt = (code or "").strip().lower()
    if not txt:
        return False
    strong_signals = ("def ", "class ", "import ", "from ", "return ", "lambda ")
    if any(sig in txt for sig in strong_signals):
        return True
    # Evita fast-path em pseudoalgoritmo textual.
    pseudo_signals = ("algoritmo", "início", "inicio", "fim", "lista of", "para cada")
    if any(sig in txt for sig in pseudo_signals):
        return False
    return False


# ---------------------------------------------------------------------------
# Grupo raiz
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(package_name="orn")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """ORN — AI CLI para código (Qwen2.5-Coder local)."""
    ctx.ensure_object(dict)
    ctx.obj['start_time'] = time.perf_counter()
    try:
        from doxoade.chronos import chronos_recorder
        chronos_recorder.start_command(ctx)
    except ImportError:
        pass

@cli.result_callback()
def process_result(result, **kwargs):
    ctx = click.get_current_context()
    if ctx.obj and 'start_time' in ctx.obj:
        try:
            from doxoade.chronos import chronos_recorder
            import sys
            duration_ms = (time.perf_counter() - ctx.obj['start_time']) * 1000
            exit_code = 0 if sys.exc_info()[0] is None else 1
            chronos_recorder.end_command(exit_code, duration_ms)
        except ImportError:
            pass


# ---------------------------------------------------------------------------
# think — MVP [Fase 1 ATIVO]
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("prompt", nargs=-1, required=True)
@click.option("--file", "-f", "context_file",
              type=click.Path(exists=True),
              default=None,
              help="Arquivo de contexto adicional (injeta no prompt).")
@click.option("--raw", is_flag=True, default=False,
              help="Exibe output bruto sem formatação.")
@click.option("--tokens", "-t",
              type=int, default=None,
              help="Limite de tokens da resposta (padrão: 128).")
@click.option("--direct", is_flag=True, default=False,
              help="Força modo direto (ignora servidor mesmo se online).")
@click.option("--search", "-s", default=None, metavar="QUERY|FONTE:QUERY",
              help="Busca contexto online. Ex: 'asyncio' ou 'pypi:requests'")
@click.option("--search-code-only", is_flag=True, default=False,
              help="Quando usar --search local/auto, restringe contexto local para blocos de código.")
@click.option("--drawer-first", is_flag=True, default=False,
              help="Tenta usar primeiro snippet do gaveteiro (repertório local) antes de buscar online.")
@click.option("--drawer-only", is_flag=True, default=False,
              help="Se achar snippet no gaveteiro, responde sem carregar modelo (modo ultra-rápido).")
@click.option("--drawer-auto-save/--no-drawer-auto-save", default=True,
              help="Quando houver contexto [CODE-BEGIN], salva snippets no gaveteiro automaticamente.")
@click.option("--no-auto", is_flag=True, default=False,
              help="Desativa busca autônoma (two-pass) nesta chamada.")
@click.option("--telemetry", is_flag=True, default=False,
              help="Ativa telemetria detalhada para modo direto (grava telemetry/direct_runtime.jsonl).")
@click.option("--consult", is_flag=True, default=False,
              help="Enriquece prompt com contexto do acervo Consult (FTS5).")
def think(prompt: tuple[str, ...], context_file: str | None,
          raw: bool, tokens: int | None, direct: bool, consult: bool,
          search: str | None, search_code_only: bool, drawer_first: bool,
          drawer_only: bool, drawer_auto_save: bool, no_auto: bool, telemetry: bool) -> None:
    """Pergunta livre ao Qwen. Ex: orn think 'como faço X em Python?'"""
    import time

    from engine.telemetry.runtime import record_direct

    telemetry_enabled = telemetry or (os.environ.get("ORN_TELEMETRY", "") == "1")
    question = " ".join(prompt).strip()
    context_blocks: list[str] = []

    consult_hint = ""
    consult_results = []
    if consult:
        try:
            from engine.tools.consult_bridge import ConsultBridge
            cb = ConsultBridge()
            if cb.is_available():
                consult_results = cb.search(question, limit=3)
                if consult_results:
                    consult_hint = (
                        "Use as informações de referência do acervo abaixo para complementar e fundamentar sua resposta:\n\n"
                        + cb.format_context(consult_results, max_chars=1200)
                    )
                    Display.info(f"[CONSULT] {len(consult_results)} fonte(s) injetada(s).")
                else:
                    Display.warn("[CONSULT] Sem resultado — seguindo sem RAG.")
        except Exception as e:
            Display.warn(f"[CONSULT] {e}")

    if tokens is not None:
        max_tokens = tokens
    else:
        from engine.core.executive import _adaptive_max_tokens  # noqa: PLC0415
        max_tokens = _adaptive_max_tokens(question)

    if consult_hint:
        context_blocks.append(f"[CONSULT-HINT]\n{consult_hint}\n[CONSULT-HINT-END]\n")

    # (A LINHA 'context_blocks: list[str] = []' FOI REMOVIDA DAQUI)
    drawer_snippet = None

    if drawer_first or drawer_only:
        try:
            from engine.tools.code_drawer import CodeDrawer  # noqa: PLC0415
            guessed_name = _guess_function_name(question)
            guessed_lang = _guess_lang_from_prompt(question)

            if guessed_name:
                drawer_sn = CodeDrawer().assemble(
                    name=guessed_name,
                    lang=guessed_lang,
                    inputs=[],
                    outputs=[],
                )

                if drawer_sn is not None:
                    drawer_snippet = drawer_sn
                    Display.success(f"[DRAWER] Reaproveitando snippet: {drawer_sn.name} [{drawer_sn.lang}]")

                    # contexto curto, não o código inteiro
                    code_preview = drawer_sn.code.strip()
                    if len(code_preview) > 1200:
                        code_preview = "\n".join(code_preview.splitlines()[:24]) + "\n[...TRUNCADO...]"

                    context_blocks.append(
                        "[CTX-BEGIN]\n"
                        f"scope: drawer:{drawer_sn.name}\n"
                        f"lang: {drawer_sn.lang}\n"
                        "[CODE-BEGIN]\n"
                        f"{code_preview}\n"
                        "[CODE-END]\n"
                        "[CTX-END]\n"
                    )
                else:
                    Display.info("[DRAWER] Sem snippet compatível no repertório.")
        except Exception as _de:
            Display.warn(f"[DRAWER] Falha ao consultar gaveteiro: {_de}")

    if drawer_only and drawer_snippet is not None:
        Display.banner()
        Display.section("DRAWER-ONLY", f"{drawer_snippet.name} [{drawer_snippet.lang}]")
        if raw:
            print(drawer_snippet.code)
        elif _is_probably_python_snippet(drawer_snippet.code) or "```" in drawer_snippet.code:
            Display.code_block(drawer_snippet.code)
        else:
            Display.separator()
            print(drawer_snippet.code)
            Display.separator()
        Display.info("Tempo: ~0s [drawer-only fast-path]")
        return

    if search:
        from engine.tools.crawler import OrnCrawler  # noqa: PLC0415

        src_key, _, sq = search.partition(":")
        if sq:
            crawl_query, crawl_source = sq.strip(), src_key.strip()
        else:
            crawl_query, crawl_source = search.strip(), "auto"

        Display.info(f"[CRAWLER] Buscando: [{crawl_source}] {crawl_query!r}")
        try:
            crawler = OrnCrawler()
            result = crawler.search(crawl_query, source=crawl_source, code_only=search_code_only)
            if result.ok:
                Display.success(f"[CRAWLER] {result.source}: {result.title!r}")
                context_blocks.append(result.to_prompt_block())

                if drawer_auto_save:
                    try:
                        from engine.tools.code_drawer import CodeDrawer  # noqa: PLC0415
                        guessed_lang = _guess_lang_from_prompt(question)
                        guessed_name = _guess_function_name(crawl_query) or _guess_function_name(question) or "snippet"
                        saved_n = CodeDrawer().save_from_context(
                            name=guessed_name,
                            lang=guessed_lang,
                            context=result.context or "",
                            tags=[f"source:{result.source}", "crawler"],
                        )
                        if saved_n:
                            Display.info(f"[DRAWER] {saved_n} snippet(s) salvos no repertório.")

                        if search_code_only and drawer_snippet is None:
                            drawer_snippet = CodeDrawer().assemble(
                                name=guessed_name,
                                lang=guessed_lang,
                                inputs=[],
                                outputs=[],
                            )
                    except Exception as _ds:
                        Display.warn(f"[DRAWER] Falha ao salvar snippet: {_ds}")

                if drawer_only and drawer_snippet is None:
                    try:
                        from engine.tools.code_drawer import CodeDrawer  # noqa: PLC0415
                        guessed_lang = _guess_lang_from_prompt(question)
                        guessed_name = _guess_function_name(crawl_query) or _guess_function_name(question) or "snippet"
                        drawer_snippet = CodeDrawer().assemble(
                            name=guessed_name,
                            lang=guessed_lang,
                            inputs=[],
                            outputs=[],
                        )
                    except Exception as _dr:
                        Display.warn(f"[DRAWER] Falha ao recarregar snippet: {_dr}")
            else:
                Display.warn(f"[CRAWLER] {result.error}")
        except Exception as _ce:
            Display.warn(f"[CRAWLER] Erro: {_ce}")

    if context_file:
        try:
            with open(context_file, encoding="utf-8", errors="replace") as _cf:
                ctx_text = _cf.read(3000)
            context_blocks.append(
                f"[CTX-BEGIN]\n"
                f"scope: {context_file}\n"
                f"{ctx_text}\n"
                f"[CTX-END]\n"
            )
        except OSError:
            pass

    if drawer_only and drawer_snippet is None:
        raise click.ClickException(
            "Nenhum snippet compatível no drawer para --drawer-only. "
            "Use --drawer-first com snippet salvo, ou rode sem --drawer-only."
        )

    if (
        search_code_only
        and drawer_snippet is not None
        and tokens is None
        and _is_probably_python_snippet(getattr(drawer_snippet, "code", ""))
    ):
        # Fast-path: evita inferência quando já temos snippet local confiável.
        Display.banner()
        Display.section("SEARCH-CODE-ONLY FAST-PATH", f"{drawer_snippet.name} [{drawer_snippet.lang}]")
        if raw:
            print(drawer_snippet.code)
        else:
            Display.code_block(drawer_snippet.code)
        Display.info("Tempo: ~0s  [search-code-only fast-path]")
        return

    Display.banner()
    Display.thinking(question)

    from engine.tools.server_client import is_server_online  # noqa: PLC0415

    use_server = (not direct) and is_server_online()
    if use_server:
        Display.info("Modo servidor ativo — inferência instantânea...")
    else:
        Display.info("Modo direto — carregando modelo (rápido via mmap)...")
    Display.separator()

    if use_server and not no_auto and not context_blocks and _should_auto_search(question):
        from engine.tools.auto_search import AutoSearchDecider  # noqa: PLC0415

        decider = AutoSearchDecider()
        search_term = decider.decide(question, server_query)
        if search_term:
            Display.info(f"[AUTO] Buscando: {search_term!r}")
            try:
                from engine.tools.crawler import OrnCrawler  # noqa: PLC0415
                result = OrnCrawler().search(search_term, source="auto", code_only=search_code_only)
                if result.ok:
                    Display.success(f"[AUTO] Contexto: {result.source}")
                    context_blocks.append(result.to_prompt_block())
            except Exception:
                pass

    full_prompt = question
    if context_blocks:
        full_prompt = "".join(context_blocks) + "\n[TASK]\n" + question

    t_start = time.perf_counter()
    ex = None
    result = None
    from types import SimpleNamespace

    try:
        if use_server:
            from engine.tools.server_client import query as server_query  # noqa: PLC0415

            server_resp = server_query(full_prompt, max_tokens=max_tokens)

            if not isinstance(server_resp, dict):
                result = SimpleNamespace(
                    success=False,
                    output="",
                    errors=["servidor offline ou resposta inválida"],
                    metadata={"elapsed_s": round(time.perf_counter() - t_start, 3)},
                )
            else:
                err = server_resp.get("error")
                result = SimpleNamespace(
                    success=not bool(err),
                    output=str(server_resp.get("output", "")),
                    errors=[str(err)] if err else [],
                    metadata={
                        "elapsed_s": float(server_resp.get("elapsed_s") or round(time.perf_counter() - t_start, 3))
                    },
                )
        else:
            from engine.core.executive import SiCDoxExecutive  # noqa: PLC0415
            ex = SiCDoxExecutive()
            result = ex.process_goal(
                intent="think",
                payload=question,            # ← prompt puro, sem Consult dentro
                context={
                    "consult_hint": consult_hint,   # ← novo campo
                    "context_file": context_file,
                    "max_tokens": max_tokens,
                    "search_code_only": search_code_only,
                    "use_server": False,
                },
            )
    finally:
        if ex is not None:
            ex.shutdown()

    total_s = round(time.perf_counter() - t_start, 3)

    if not result.success:
        for err in result.errors:
            Display.error(err)
        raise SystemExit(1)

    Display.separator()
    if raw:
        print(result.output)
    else:
        Display.code_block(result.output)
    Display.separator()

    reported_elapsed = result.metadata.get("elapsed_s") if getattr(result, "metadata", None) else None
    mode_label = "[servidor]" if use_server else "[direto]"
    Display.info(f"Tempo: {reported_elapsed or total_s}s  {mode_label}")

    if telemetry_enabled and not use_server:
        try:
            board_meta = result.metadata.get("board", {}) if getattr(result, "metadata", None) else {}
            payload = {
                "captured_at_unix": int(time.time()),
                "mode": "direct",
                "model_load_s": None,
                "infer_s": reported_elapsed or total_s,
                "total_s": total_s,
                "reported_elapsed": reported_elapsed,
                "prompt_chars": len(full_prompt) if full_prompt else 0,
                "max_tokens": max_tokens,
                "board_drafts": board_meta.get("draft_count", 0),
                "board_by_role": board_meta.get("by_role", {}),
                "board_token_hint": board_meta.get("token_hint"),
            }
            record_direct(payload)
            Display.info("Telemetria gravada: telemetry/direct_runtime.jsonl")
        except Exception as _te:
            Display.warn(f"Telemetria falhou: {_te}")

def _should_auto_search(question: str) -> bool:
    q = (question or "").strip()
    if not q:
        return False
    if q.isdigit():
        return False
    if len(q) < 12:
        return False
    if len(q.split()) < 3:
        return False
    return True

# ---------------------------------------------------------------------------
# config — verificação de ambiente [Fase 1 ATIVO]
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--model", "-m",
              type=click.Path(),
              default=None,
              help="Define caminho para o arquivo .gguf.")
@click.option("--threads", "-t",
              type=int,
              default=None,
              help="Número de threads CPU.")
@click.option("--gpu-layers", "-g",
              type=int,
              default=None,
              help="Camadas a carregar na GPU (0 = CPU only).")
@click.option("--show", "-s",
              is_flag=True, default=False,
              help="Exibe configuração atual e verifica ambiente.")
def config(model: str | None, threads: int | None,
           gpu_layers: int | None, show: bool) -> None:
    """Configura e verifica o ambiente do ORN."""
    Display.section("CONFIG", "")

    if show or (not model and threads is None and gpu_layers is None):
        _show_config()
        return

    if model:
        Display.warn(f"--model definido: {model}")
        Display.info("(persistência de config será implementada na Fase 2)")
    if threads is not None:
        Display.kv("n_threads", str(threads))
    if gpu_layers is not None:
        Display.kv("n_gpu_layers", str(gpu_layers))

    Display.info("Use `orn config --show` para verificar o ambiente.")


def _show_config() -> None:
    """Exibe configuração atual e resultado do first_contact. OSL-4."""
    from engine.core.llm_bridge import BridgeConfig          # noqa: PLC0415
    from engine.tools.first_contact import check_environment  # noqa: PLC0415

    cfg = BridgeConfig()

    Display.info("Configuração atual (padrão):")
    Display.kv("model_path",    str(cfg.model_path))
    Display.kv("model_exists",  str(cfg.model_path.exists()))
    Display.kv("n_ctx",         str(cfg.n_ctx))
    Display.kv("active_window", str(cfg.active_window))
    Display.kv("cache_type_k",  str(cfg.cache_type_k))
    Display.kv("cache_type_v",  str(cfg.cache_type_v))
    Display.kv("rope_freq_base",str(cfg.rope_freq_base))
    Display.kv("rope_freq_scale",str(cfg.rope_freq_scale))
    Display.kv("flash_attn",    str(cfg.flash_attn))
    Display.kv("memory_profile",str(cfg.memory_profile))
    Display.kv("use_mmap",      str(cfg.use_mmap))
    Display.kv("use_mlock",     str(cfg.use_mlock))
    Display.kv("no_alloc",      str(cfg.no_alloc))
    Display.kv("pin_threads",   str(cfg.pin_threads))
    Display.kv("cont_batching", str(cfg.cont_batching))
    Display.kv("min_p",         str(cfg.min_p))
    Display.kv("repetition_memo",str(cfg.repetition_memo_enabled))
    Display.kv("memo_size",     str(cfg.repetition_memo_size))
    Display.kv("ctx_rotation",  str(cfg.context_rotation))
    Display.kv("ctx_compact_ratio", str(cfg.context_compact_ratio))
    Display.kv("max_tokens",    str(cfg.max_tokens))
    Display.kv("n_threads",     str(cfg.n_threads))
    Display.kv("n_gpu_layers",  str(cfg.n_gpu_layers))
    Display.kv("ttl_seconds",   str(cfg.ttl_seconds))
    Display.kv("temperature",   str(cfg.temperature))
    Display.kv("top_p",         str(cfg.top_p))
    Display.kv("top_k",         str(cfg.top_k))
    Display.kv("repeat_penalty",str(cfg.repeat_penalty))

    Display.separator()
    Display.info("Flags de memória efetivas:")
    for key, value in cfg.effective_memory_flags().items():
        Display.kv(f"mem.{key}", str(value))

    Display.separator()
    Display.info("Verificação de ambiente (first_contact):")
    issues = check_environment()
    if not issues:
        Display.success("Ambiente OK — pronto para `orn think`.")
    else:
        for issue in issues:
            Display.warn(issue)


def _collect_python_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target] if target.suffix.lower() == ".py" else []
    return sorted(p for p in target.rglob("*.py") if p.is_file())


def _lint_python_text(text: str) -> list[str]:
    from engine.tools.code_sandbox import lint_python_text  # noqa: PLC0415
    return lint_python_text(text)

# ─────────────────────────────────────────────────────────────
# Session REPL — helpers (nível de módulo, antes do decorator)
# ─────────────────────────────────────────────────────────────
_SESSION_ALIASES = {
    "help":       "/help",       "?":      "/help",
    "open":       "/open",
    "fix":        "/fix",
    "fix-symbol": "/fix-symbol",
    "fix-auto":   "/fix-auto",
    "apply":      "/apply",      "diff":   "/diff",
    "undo":       "/undo",       "status": "/status",
    "clear":      "/clear",      "exit":   "/exit", "quit": "/exit",
}

_SESSION_HELP = """
  Comandos disponíveis (aceitam /cmd, \\cmd, cmd ou cmd:):

    /help                  Esta ajuda
    /open <arquivo>        Abre arquivo para edição
    /fix <instrução>       Gera patch, mostra diff e pede confirmação
    /fix-symbol <instrução> Fix cirúrgico (só alvo) — erro se não resolver
    /fix-auto <instrução>  Fix cirúrgico com fallback para arquivo inteiro
    /apply                 Reaplica o último patch (após confirmação)
    /diff                  Mostra o último diff gerado
    /undo                  Reverte do backup .bak mais recente
    /status                Stats do bridge (tokens, contexto, config)
    /clear                 Limpa a lousa (sessão do DoxoBoard)
    /exit                  Sai do REPL

  Qualquer outra entrada é enviada ao modelo como pergunta livre.
"""

def _normalize_session_command(raw: str) -> str:
    """Normaliza /cmd, \\cmd, cmd, cmd: → /cmd. Devolve '' se vazio."""
    if not raw:
        return ""
    text = raw.strip()
    if not text:
        return ""
    first = text.split(maxsplit=1)[0]
    rest  = text[len(first):]
    key   = first.lstrip("/\\").rstrip(":").lower()
    canonical = _SESSION_ALIASES.get(key)
    if canonical is None:
        return text   # não é comando conhecido → instrução livre
    return canonical + rest

def _session_handle_fix(ex, current_file: str, instruction: str, symbol_mode: str) -> None:
    """Executa fix em duas fases para /fix, /fix-symbol e /fix-auto.

    symbol_mode: 'off' (whole-file), 'on' (cirúrgico, erro se falhar),
                 'auto' (cirúrgico com fallback).
    """
    mode_label = {"off": "", "on": " [symbol]", "auto": " [symbol-auto]"}[symbol_mode]
    if mode_label:
        Display.info(f"Modo cirúrgico{mode_label}")

    # ── Fase 1 ──
    ctx1 = {"apply": False, "instruction": instruction}
    if symbol_mode != "off":
        ctx1["symbol_mode"] = symbol_mode

    result = ex.process_goal(
        intent="fix",
        payload=current_file,
        context=ctx1,
    )
    if not result.success:
        for e in result.errors:
            Display.error(e)
        return

    # Curto-circuito: nada a aplicar, não pergunta
    if result.metadata.get("no_op"):
        Display.info("O código já corresponde à sugestão (nada a aplicar).")
        return

    Display.separator()
    print(result.output)
    Display.separator()

    if not click.confirm("Aplicar?", default=False):
        return

    # ── Fase 2 ──
    raw_patch = result.metadata.get("raw_output", "")
    if not raw_patch:
        Display.error("internal: raw_output vazio.")
        return

    ctx2 = {
        "apply":               True,
        "instruction":         instruction,
        "raw_output_override": raw_patch,
    }
    if symbol_mode != "off":
        ctx2["symbol_mode"] = symbol_mode

    surgical_hunks = result.metadata.get("surgical_hunks")
    if surgical_hunks:
        ctx2["surgical_hunks_override"] = surgical_hunks

    apply_res = ex.process_goal(
        intent="fix",
        payload=current_file,
        context=ctx2,
    )
    if apply_res.success:
        if apply_res.metadata.get("no_op"):
            Display.info("O código já corresponde à sugestão (nada a aplicar).")
        else:
            n = apply_res.metadata.get("hunks", 0)
            Display.success(f"Patch aplicado ({n} hunk(s)).")
    else:
        for e in apply_res.errors:
            Display.error(e)

@cli.command("session")
@click.option("--file", "-f", "initial_file",
              type=click.Path(exists=True), default=None,
              help="Arquivo inicial para edição.")
def session_cmd(initial_file):
    """REPL para edição interativa com o ORN."""
    from engine.core.executive import SiCDoxExecutive
    from engine.tools.server_client import is_server_online

    if not is_server_online():
        Display.warn("Servidor offline. Inicie com: orn-server start --bg")
        Display.info("(a sessão funciona, mas recarrega o modelo a cada patch)")

    ex = SiCDoxExecutive()
    current_file = initial_file
    try:
        while True:
            tag = f"📄 {current_file}" if current_file else "∅"
            try:
                raw_input = input(f"orn[{tag}]> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not raw_input:
                continue

            cmd = _normalize_session_command(raw_input)

            # ── Saída ──────────────────────────────────────
            if cmd in ("/exit", "/quit"):
                break

            # ── /help ──────────────────────────────────────
            if cmd == "/help":
                print(_SESSION_HELP)
                continue

            # ── /status ────────────────────────────────────
            if cmd == "/status":
                import json as _json
                print(_json.dumps(ex.bridge_stats(), indent=2, ensure_ascii=False))
                continue

            # ── /clear ─────────────────────────────────────
            if cmd == "/clear":
                ex.clear_board()
                Display.success("Lousa limpa.")
                continue

            # ── /open <arquivo> ────────────────────────────
            if cmd.startswith("/open "):
                from pathlib import Path as _P
                path = cmd[6:].strip()
                if not _P(path).exists():
                    Display.error(f"arquivo não existe: {path}")
                    continue
                current_file = path
                Display.success(f"aberto: {path}")
                continue

            # ── /fix-symbol <instrução> ────────────────────
            if cmd.startswith("/fix-symbol "):
                if not current_file:
                    Display.error("use /open <arquivo> primeiro")
                    continue
                _session_handle_fix(ex, current_file, cmd[12:].strip(), "on")
                continue

            # ── /fix-auto <instrução> ──────────────────────
            if cmd.startswith("/fix-auto "):
                if not current_file:
                    Display.error("use /open <arquivo> primeiro")
                    continue
                _session_handle_fix(ex, current_file, cmd[10:].strip(), "auto")
                continue

            # ── /fix <instrução> ───────────────────────────
            if cmd.startswith("/fix "):
                if not current_file:
                    Display.error("use /open <arquivo> primeiro")
                    continue
                _session_handle_fix(ex, current_file, cmd[5:].strip(), "off")
                continue

            # ── /undo ──────────────────────────────────────
            if cmd == "/undo":
                from pathlib import Path as _P
                import shutil as _sh
                if not current_file:
                    Display.error("nenhum arquivo aberto")
                    continue
                bak = _P(current_file + ".bak")
                if not bak.exists():
                    Display.error(f"nenhum backup em {bak}")
                    continue
                _sh.copy2(bak, current_file)
                Display.success(f"revertido de {bak}")
                continue

            # ── Comando / ou \ desconhecido → NÃO envia ao modelo ──
            if raw_input.startswith(("/", "\\")):
                Display.warn(f"comando desconhecido: {raw_input.split()[0]}")
                Display.info("use /help para ver os comandos disponíveis")
                continue

            # ── Fallback: pergunta livre ───────────────────
            result = ex.process_goal(intent="think", payload=raw_input, context={})
            if result.success:
                Display.separator()
                print(result.output)
                Display.separator()
            else:
                for e in result.errors:
                    Display.error(e)
    finally:
        ex.shutdown()

@cli.command("sandbox")
@click.argument("target", type=click.Path(exists=True, dir_okay=False))
def sandbox_cmd(target):
    """Executa um arquivo Python em ambiente isolado (Job Object)."""
    from engine.tools.sandbox import run_in_sandbox
    from engine.ui.display import Display
    from pathlib import Path

    Display.section("SANDBOX", target)
    try:
        code = Path(target).read_text(encoding="utf-8")
    except Exception as e:
        Display.error(f"Falha ao ler arquivo: {e}")
        raise SystemExit(1)

    Display.info("Executando em isolamento...")
    result = run_in_sandbox(code, timeout_s=5)

    if result.success:
        Display.success("Execução concluída com sucesso.")
    else:
        Display.error(f"Falha com código {result.exit_code}")

    if result.stdout:
        Display.separator()
        print(result.stdout)
    if result.stderr:
        Display.separator()
        print(result.stderr)

@cli.command("diagnose")
@click.argument("target", type=click.Path(exists=True), default=".")
@click.option("--run", "run_script", is_flag=True, default=False, help="Executa script em modo isolado (-I).")
@click.option("--timeout", type=int, default=8, help="Timeout de execução do script em segundos.")
def diagnose(target: str, run_script: bool, timeout: int) -> None:
    """Diagnóstico local (stdlib): sintaxe + linter básico + execução isolada opcional."""
    target_path = Path(target)
    files = _collect_python_files(target_path)
    if not files:
        raise click.ClickException("Nenhum arquivo .py encontrado no alvo.")

    total_issues = 0
    for file_path in files:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        issues = _lint_python_text(text)
        if issues:
            total_issues += len(issues)
            Display.warn(f"[DIAG] {file_path} -> {len(issues)} issue(s)")
            for item in issues[:8]:
                Display.info(f"  - {item}")

    run_fail = False
    if run_script and target_path.is_file() and target_path.suffix.lower() == ".py":
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(target_path)],
                capture_output=True,
                text=True,
                timeout=max(1, timeout),
            )
            if proc.returncode != 0:
                run_fail = True
                Display.warn(f"[RUN] retorno={proc.returncode}")
                if proc.stderr.strip():
                    Display.info(proc.stderr.strip().splitlines()[-1])
        except subprocess.TimeoutExpired:
            run_fail = True
            Display.warn("[RUN] timeout expirado.")

    if total_issues == 0 and not run_fail:
        Display.success("Diagnóstico OK: sem issues detectadas.")
        return

    raise SystemExit(1)




@cli.command(
    "index",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    add_help_option=False,
)
@click.argument("local_index_args", nargs=-1, type=click.UNPROCESSED)
def index(local_index_args: tuple[str, ...]) -> None:
    """Encaminha comandos para o Local Index (build/search/info/list/diagnose/preload)."""
    from engine.tools.local_index import _cli_main  # noqa: PLC0415

    args = list(local_index_args)
    if not args:
        args = ["--help"]
    elif args[0] in ("-h", "--help"):
        args = ["--help"] + args[1:]

    exit_code = _cli_main(args)
    if exit_code:
        raise click.ClickException(f"Comando de index finalizado com código {exit_code}.")


@cli.command("tutorial")
def tutorial() -> None:
    click.echo("""
=== ORN — Guia Rápido de Uso ===

Comandos Principais:
  orn think "sua pergunta"           Consulta rápida à IA local
  orn think "..." --consult          Enriquece com o acervo Python do Doxoade (RAG FTS5)
  orn think "..." --drawer-first     Reaproveita funções locais testadas
  orn think "..." --tokens 256       Ajusta o limite de tokens

Edição & Ferramentas:
  orn diff arquivo.py -i "tarefa"    Gera e simula patch em formato @N
  orn diff arquivo.py -i "..." --apply   Aplica alteração cirúrgica no código
  orn gen "função quicksort"         Gera e valida código via CodeAssembler
  orn sandbox script.py              Roda código em isolamento (Windows JobObject)

Servidor & Observabilidade:
  orn server start [--bg]            Inicia servidor local em segundo plano
  orn server status                  Estatísticas de RPS, latência e uptime
  orn brain                          Lousa de hipóteses e telemetria agregada
  orn probe status                   Diagnóstico de hotspots do servidor
    """.strip())


def _csv_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


@cli.group("drawer", invoke_without_command=True)
@click.option("--list", "list_flag", is_flag=True, default=False, help="Atalho para `orn drawer list`.")
@click.pass_context
def drawer(ctx: click.Context, list_flag: bool) -> None:
    """Gerencia snippets locais de código (gaveteiro do usuário)."""
    if list_flag:
        ctx.invoke(drawer_list, lang=None)
        return
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@drawer.command("add")
@click.option("--name", required=True, help="Nome da função/bloco.")
@click.option("--lang", required=True, help="Linguagem (ex: python).")
@click.option("--in", "inputs", default="", help="Entradas CSV (ex: list[int],key).")
@click.option("--out", "outputs", default="", help="Saídas CSV (ex: list[int]).")
@click.option("--tags", default="", help="Tags CSV (opcional).")
@click.option("--file", "code_file", type=click.Path(exists=True), default=None, help="Arquivo do snippet.")
@click.option("--code", default=None, help="Código inline (alternativa ao --file).")
def drawer_add(name: str, lang: str, inputs: str, outputs: str, tags: str,
               code_file: str | None, code: str | None) -> None:
    """Adiciona/atualiza snippet no drawer."""
    from engine.tools.code_drawer import CodeDrawer  # noqa: PLC0415

    payload = code
    if code_file:
        payload = Path(code_file).read_text(encoding="utf-8", errors="replace")
    if not payload:
        raise click.ClickException("Informe --file ou --code.")

    sn = CodeDrawer().upsert_snippet(
        name=name,
        lang=lang,
        inputs=_csv_list(inputs),
        outputs=_csv_list(outputs),
        code=payload,
        tags=_csv_list(tags),
    )
    Display.success(f"Snippet salvo: {sn.name} [{sn.lang}]")


@drawer.command("list")
@click.option("--lang", default=None, help="Filtra por linguagem.")
def drawer_list(lang: str | None) -> None:
    """Lista snippets salvos no drawer."""
    from engine.tools.code_drawer import CodeDrawer  # noqa: PLC0415

    items = CodeDrawer().list_snippets(lang=lang)
    if not items:
        Display.warn("Drawer vazio.")
        return
    for sn in items:
        Display.kv(
            f"{sn.name} [{sn.lang}]",
            f"in={','.join(sn.inputs) or '-'} out={','.join(sn.outputs) or '-'} tags={','.join(sn.tags) or '-'}",
        )


@drawer.command("show")
@click.argument("name", required=True)
@click.option("--lang", default=None, help="Linguagem do snippet.")
def drawer_show(name: str, lang: str | None) -> None:
    """Exibe o código bruto de um snippet."""
    from engine.tools.code_drawer import CodeDrawer  # noqa: PLC0415

    sn = CodeDrawer().get(name=name, lang=lang)
    if sn is None:
        raise click.ClickException(f"Snippet não encontrado: {name!r}")
    Display.code_block(sn.code)

@drawer.command("assemble")
@click.option("--name", required=True, help="Função alvo.")
@click.option("--lang", required=True, help="Linguagem alvo.")
@click.option("--in", "inputs", default="", help="Entradas CSV esperadas.")
@click.option("--out", "outputs", default="", help="Saídas CSV esperadas.")
def drawer_assemble(name: str, lang: str, inputs: str, outputs: str) -> None:
    """Monta código por função + I/O usando snippets salvos."""
    from engine.tools.code_drawer import CodeDrawer  # noqa: PLC0415

    sn = CodeDrawer().assemble(
        name=name,
        lang=lang,
        inputs=_csv_list(inputs),
        outputs=_csv_list(outputs),
    )
    if sn is None:
        raise click.ClickException("Nenhum snippet compatível encontrado no drawer.")

    Display.section("ASSEMBLER", f"{sn.name} [{sn.lang}]")
    Display.kv("inputs", ", ".join(sn.inputs) if sn.inputs else "-")
    Display.kv("outputs", ", ".join(sn.outputs) if sn.outputs else "-")
    Display.code_block(sn.code)


# ---------------------------------------------------------------------------
# Comandos Fase 2+ — stubs com mensagem clara
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("target", type=click.Path(exists=True))
@click.option("--format", "-fmt", "output_format",
              type=click.Choice(["text", "json"]), default="text")
@click.option("--func", "-f", default=None,
              help="Foca a análise em uma função específica.")
def audit(target: str, output_format: str, func: str | None) -> None:
    """[Fase 2] Analisa AST + aponta problemas no arquivo."""
    Display.section("AUDIT", target)
    from engine.core.executive import SiCDoxExecutive
    ex = SiCDoxExecutive()
    try:
        result = ex.process_goal(
            intent="audit",
            payload=target,
            context={"func": func},
        )
    finally:
        ex.shutdown()

    if not result.success:
        for err in result.errors:
            Display.error(err)
        raise SystemExit(1)

    if output_format == "json":
        import json
        print(json.dumps(result.metadata, ensure_ascii=False, indent=2))
        return

    # Exibe issues estáticos
    static_issues = result.metadata.get("static_issues", [])
    if static_issues:
        Display.warn(f"{len(static_issues)} problema(s) detectado(s) pelo linter AST:")
        for item in static_issues:
            Display.info(f"  • {item}")
        Display.separator()

    # Exibe diagnóstico da IA
    Display.info("Diagnóstico da IA:")
    print(result.output)
    Display.separator()
    Display.info(f"Tempo: {result.metadata.get('elapsed_s', '?')}s")



@cli.command()
@click.argument("target", type=click.Path(exists=True))
@click.option("--instruction", "-i", default=None)
@click.option("--apply", is_flag=True, default=False)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--consult", is_flag=True, default=False)
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Mostra raw_output do modelo quando o parse falhar.")
@click.option("--symbol", "symbol_mode_on", is_flag=True, default=False,
              help="Força modo cirúrgico: resolve símbolo-alvo na instrução. "
                   "Falha com candidatos se não achar.")
@click.option("--symbol-auto", "symbol_mode_auto", is_flag=True, default=False,
              help="Tenta modo cirúrgico; fallback silencioso para arquivo inteiro.")
def fix(target, instruction, apply, dry_run, consult, verbose,
        symbol_mode_on, symbol_mode_auto):
    from engine.core.executive import SiCDoxExecutive

    if apply and dry_run:
        raise click.UsageError("--apply e --dry-run são mutuamente exclusivos.")
    if symbol_mode_on and symbol_mode_auto:
        raise click.UsageError("--symbol e --symbol-auto são mutuamente exclusivos.")

    symbol_mode = "on" if symbol_mode_on else "auto" if symbol_mode_auto else "off"

    Display.section("FIX", target)
    if symbol_mode != "off":
        Display.kv("symbol_mode", symbol_mode)

    # ── Fase 1 ──
    ex = SiCDoxExecutive()
    try:
        result = ex.process_goal(
            intent="fix",
            payload=target,
            context={
                "apply":       False,
                "instruction": instruction,
                "consult":     consult,
                "symbol_mode": symbol_mode,
            },
        )
    finally:
        ex.shutdown()

    if not result.success:
        for err in result.errors:
            if not verbose and "raw_output do modelo" in err:
                continue              # só mostra com -v
            for line in err.splitlines():
                Display.error(line)
        raise SystemExit(1)

    Display.separator()
    print(result.output)
    Display.separator()

    if dry_run:
        Display.info("dry-run — patch NÃO aplicado.")
        return

    raw = result.metadata.get("raw_output", "")
    if not raw:
        Display.error("internal: raw_output vazio — impossível aplicar.")
        raise SystemExit(1)

    if not apply:
        if not click.confirm("Aplicar este patch?", default=False):
            Display.info("Cancelado.")
            return

    # ── Fase 2 ──
    surgical_hunks = result.metadata.get("surgical_hunks")
    apply_context = {
        "apply":               True,
        "instruction":         instruction,
        "consult":             consult,
        "raw_output_override": raw,
        "symbol_mode":         symbol_mode,
    }
    if surgical_hunks:
        apply_context["surgical_hunks_override"] = surgical_hunks

    ex = SiCDoxExecutive()
    try:
        apply_res = ex.process_goal(
            intent="fix",
            payload=target,
            context=apply_context,
        )
    finally:
        ex.shutdown()

    if not apply_res.success:
        for err in apply_res.errors:
            Display.error(err)
        raise SystemExit(1)

    applied = apply_res.metadata.get("applied", False)
    no_op   = apply_res.metadata.get("no_op", False)
    n_hunks = apply_res.metadata.get("hunks", 0)
    elapsed = apply_res.metadata.get("elapsed_s", "?")

    if no_op:
        Display.info("O código já corresponde à sugestão do modelo — nada a aplicar.")
        return
    if applied:
        Display.success(f"Patch aplicado ({n_hunks} hunk(s)) em {elapsed}s — "
                        f"backup: {target}.bak")
    else:
        Display.warn(f"Patch NÃO aplicado ({elapsed}s).")
        raise SystemExit(1)

@cli.command()
@click.argument("description", nargs=-1, required=True)
@click.option("--lang", "-l", default="python",
              help="Linguagem alvo (python, c, cpp, batch).")
@click.option("--out", "-o", type=click.Path(), default=None,
              help="Salva o código gerado neste arquivo.")
def gen(description: tuple[str, ...], lang: str, out: str | None) -> None:
    """[Fase 4] Gera código a partir de descrição. Ex: orn gen 'busca binária'"""
    Display.section("GEN", f"[{lang.upper()}] {' '.join(description)}")
    Display.not_implemented("gen")


def _display_profile(last: int) -> None:
    """Lê telemetry/profiler.jsonl e exibe breakdown de spans."""
    prof_path = Path("telemetry/profiler.jsonl")
    if not prof_path.exists():
        Display.warn("profiler.jsonl ausente — rode `orn think ... --telemetry` primeiro.")
        return

    entries: list[dict] = []
    for line in prof_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    recent = [e for e in entries if e.get("v") == 1][-last:]
    if not recent:
        Display.warn("Nenhuma entrada v1 no profiler.jsonl.")
        return

    n = len(recent)
    Display.info(f"Profiler — breakdown de spans ({n} execuções):")

    # Span names em ordem de exibição
    span_names = ["load_check", "ctx_push", "prompt_build",
                  "llm_call", "text_parse", "memo_lookup", "memo_store"]

    # Agrega médias por span
    for sname in span_names:
        vals = [e["spans_ms"].get(sname, 0.0) for e in recent if "spans_ms" in e]
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        mx  = max(vals)
        # barra proporcional ao max (max = 40 chars)
        total_avg = sum(
            e["spans_ms"].get("total", 1) for e in recent if "spans_ms" in e
        ) / max(1, n)
        bar_len = int(avg / max(1.0, total_avg) * 40)
        bar = "█" * bar_len + "░" * (40 - bar_len)
        print(f"  {sname:<14} avg={avg:>8.1f}ms  max={mx:>8.1f}ms  |{bar}|")

    # Derivados médios
    Display.info("Derivados (médias):")
    for key, label in [
        ("overhead_ms",           "overhead Python"),
        ("overhead_pct",          "overhead %"),
        ("ms_per_token",          "ms/token"),
        ("ttft_est_ms",           "TTFT estimado"),
        ("prompt_eval_share_pct", "prompt_eval share%"),
        ("tokens_per_second",     "tok/s"),
    ]:
        vals = [e["derived"].get(key, 0.0) for e in recent if "derived" in e]
        if vals:
            avg = round(sum(vals) / len(vals), 2)
            print(f"  {label:<22} {avg}")

    # active_window
    aw_vals = [e["counters"].get("active_window_used", 0) for e in recent if "counters" in e]
    aw_cfg  = recent[-1].get("counters", {}).get("active_window_cfg", "?") if recent else "?"
    if aw_vals:
        avg_aw = round(sum(aw_vals) / len(aw_vals))
        Display.info(f"active_window: cfg={aw_cfg}  usado médio={avg_aw}  "
                     f"(economia={round(100*(1-avg_aw/max(1,int(aw_cfg))),1)}%)")


@cli.command()
@click.option("--clear", is_flag=True, default=False,
              help="Descarta a sessão corrente da lousa.")
@click.option("--last", "-n", type=int, default=10, show_default=True,
              help="Quantas entradas de telemetria exibir.")
@click.option("--json-output", "json_output", is_flag=True, default=False,
              help="Exibe dados brutos em JSON.")
@click.option("--profile", is_flag=True, default=False,
              help="Exibe breakdown de spans do profiler (telemetry/profiler.jsonl).")
def brain(clear: bool, last: int, json_output: bool, profile: bool) -> None:
    """Estado interno: telemetria do blackboard + bridge."""

    Display.section("BRAIN", "Estado interno")
    ex = SiCDoxExecutive()
    try:
        if clear:
            ex.clear_board()
            Display.success("Sessão da lousa descartada.")
            return

        # ── Telemetria em disco ──────────────────────────────────────────
        tele_path = Path("telemetry/direct_runtime.jsonl")
        entries: list[dict] = []
        if tele_path.exists():
            for line in tele_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        # Filtra por tipo de entrada — bridge e CLI escrevem linhas distintas
        infer_entries = [e for e in entries if "prompt_tokens" in e and "infer_s" in e]
        board_entries = [e for e in entries if "board_drafts" in e]
        recent_infer  = infer_entries[-last:]
        recent_board  = board_entries[-last:]

        if json_output:
            out = {
                "board": ex.board_summary(),
                "bridge": ex.bridge_stats(),
                "telemetry_infer": infer_entries[-last:],
                "telemetry_board": board_entries[-last:],
            }
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return

        # ── Bridge ──────────────────────────────────────────────────────
        bridge = ex.bridge_stats()
        Display.info("Bridge (Hefesto):")
        print(f"  - modelo carregado: {bridge.get('model_loaded', False)}")
        if bridge.get("model_loaded"):
            print(f"  - uptime:           {bridge.get('loaded_since_s', '?')}s")
            ctx = bridge.get("context", {})
            print(f"  - ctx turns/est:    {ctx.get('turns', 0)}/{ctx.get('token_est', 0)} tk")

        # ── Lousa (sessão corrente) ──────────────────────────────────────
        board = ex.board_summary()
        Display.info("Lousa (sessão corrente):")
        print(f"  - aberta:     {board.get('open', False)}")
        print(f"  - query:      {board.get('query_preview', '(vazia)') or '(vazia)'}")
        print(f"  - drafts:     {board.get('draft_count', 0)}")
        by_role = board.get("by_role", {})
        if by_role:
            print(f"  - por role:   {by_role}")

        # ── Telemetria agregada ──────────────────────────────────────────
        if not recent_infer and not recent_board:
            Display.warn("Sem telemetria gravada. Use `orn think ... --telemetry`.")
            return

        if recent_infer:
            n = len(recent_infer)
            total_infer   = sum(float(e.get("infer_s", 0)) for e in recent_infer)
            total_ptok    = sum(int(e.get("prompt_tokens", 0)) for e in recent_infer)
            total_ctok    = sum(int(e.get("completion_tokens", 0)) for e in recent_infer)
            total_tps_sum = sum(float(e.get("tokens_per_second", 0)) for e in recent_infer)
            Display.info(f"Telemetria de inferência (últimas {n}):")
            print(f"  - infer médio:     {round(total_infer / n, 2)}s")
            print(f"  - prompt tk médio: {round(total_ptok / n, 1)}")
            print(f"  - output tk médio: {round(total_ctok / n, 1)}")
            print(f"  - tok/s médio:     {round(total_tps_sum / n, 3)}")

        if recent_board:
            nb = len(recent_board)
            avg_drafts = sum(e.get("board_drafts", 0) for e in recent_board) / nb
            avg_hint   = sum(e.get("board_token_hint") or 0 for e in recent_board) / nb
            role_totals: dict[str, int] = {}
            for e in recent_board:
                for role, cnt in (e.get("board_by_role") or {}).items():
                    role_totals[role] = role_totals.get(role, 0) + cnt
            Display.info(f"Lousa (histórico agregado, últimas {nb}):")
            print(f"  - drafts médio:     {round(avg_drafts, 1)}")
            print(f"  - token_hint médio: {round(avg_hint, 1)}")
            if role_totals:
                print(f"  - roles acum.:      {role_totals}")

        # ── Últimas N execuções resumidas (inferência) ─────────────────
        Display.info("Últimas execuções (inferência):")
        for e in recent_infer:
            ts    = e.get("captured_at_unix", 0)
            ptok  = e.get("prompt_tokens", "?")
            ctok  = e.get("completion_tokens", "?")
            infer = e.get("infer_s", "?")
            print(f"  [{ts}] prompt={ptok}tk out={ctok}tk infer={infer}s")

        # ── Profiler (spans finos) ──────────────────────────────────────
        if profile:
            _display_profile(last)

    finally:
        ex.shutdown()


@cli.command()
@click.argument("target", type=click.Path(exists=True))
@click.option("--rebuild", is_flag=True, default=False)
def graph(target: str, rebuild: bool) -> None:
    """[Fase 2] Grafo de conceitos AST. Ex: orn graph main.py"""
    Display.section("GRAPH", target)
    Display.not_implemented("graph")


@cli.command()
@click.option("--prompt", default="qual é o kernel?", show_default=True, help="Prompt usado no benchmark.")
@click.option("--runs", type=int, default=2, show_default=True, help="Execuções por configuração (após warm-up).")
@click.option("--tokens", type=int, default=192, show_default=True, help="Max tokens por execução.")
def bench(prompt: str, runs: int, tokens: int) -> None:
    """Auto-tuning: varre configurações e escolhe menor tempo médio."""
    from engine.tools.benchmark_tuner import autotune  # noqa: PLC0415

    Display.section("BENCH", "Auto-tuning de latência")
    report = autotune(prompt=prompt, runs=max(1, runs), max_tokens=max(8, tokens))
    for row in report.get("candidates", []):
        print(
            f"  - n_ctx={row['n_ctx']:<4} min_p={row['min_p']:<4} "
            f"repeat_penalty={row['repeat_penalty']:<4} avg={row['avg_s']}s"
        )
    best = report.get("best")
    if best:
        Display.success(
            f"Melhor: n_ctx={best['n_ctx']} min_p={best['min_p']} repeat_penalty={best['repeat_penalty']} avg={best['avg_s']}s"
        )

# ---------------------------------------------------------------------------
# T4.2 — `orn diff` (edição cirúrgica via @N)
# ---------------------------------------------------------------------------

@cli.command("diff")
@click.argument("target", type=click.Path(exists=True, dir_okay=False))
@click.option("--instruction", "-i", required=True,
              help="Tarefa em linguagem natural. Ex: 'Troque + por - na linha 5'")
@click.option("--apply", is_flag=True, default=False,
              help="Aplicar o patch no arquivo (default: dry-run).")
@click.option("--verify", is_flag=True, default=False,
              help="Após aplicar, executa o código no Sandbox isolado.")
@click.option("--model", "-m", default=None,
              help="Alias do modelo (default: active_alias do catálogo).")
@click.option("--max-tokens", type=int, default=256, show_default=True)
@click.option("--temperature", type=float, default=0.2, show_default=True)
@click.option("--raw", is_flag=True, default=False,
              help="Mostrar output cru do modelo.")
@click.option("--consult", is_flag=True, default=False,
              help="Enriquece prompt do diff com contexto do acervo.")
def diff_cmd(target: str, instruction: str, apply: bool, verify: bool,
             consult: bool, model: str | None,
             max_tokens: int, temperature: float, raw: bool) -> None:
    """Gera e (opcionalmente) aplica edições cirúrgicas no formato @N - old + new."""
    from engine.tools.diff_engine import generate_and_apply

    Display.section("DIFF", target)
    Display.kv("instruction", instruction[:80])
    Display.kv("apply",       "sim" if apply else "não (dry-run)")
    Display.kv("verify",      "sim" if verify else "não")
    Display.kv("model",       model or "(active)")

    result = generate_and_apply(
        target, instruction,
        apply=apply,
        verify=verify,
        consult=consult,
        max_tokens=max_tokens,
        temperature=temperature,
        model_alias=model,
    )

    if raw:
        Display.separator()
        print(result.raw_output)

    if result.hunks:
        Display.separator()
        print(f"  {len(result.hunks)} hunk(s):")
        for h in result.hunks:
            print(f"    @{h.line}")
            for r in h.removed:
                print(f"      - {r}")
            for a in h.added:
                print(f"      + {a}")

    if result.errors:
        Display.separator()
        for e in result.errors:
            Display.error(e)

    Display.separator()
    if result.applied:
        Display.success(f"patch aplicado em {target} ({result.elapsed_s}s)")
    elif apply:
        Display.warn(f"patch NÃO aplicado ({result.elapsed_s}s)")
        raise SystemExit(1)
    else:
        Display.info(f"dry-run — use --apply para escrever ({result.elapsed_s}s)")

    if not result.success:
        raise SystemExit(1)

# ---------------------------------------------------------------------------
# server — grupo de subcomandos para orn-server
# ---------------------------------------------------------------------------

@cli.group()
def server() -> None:
    """Controla o SiCDox Server (inferencia persistente)."""
    pass


@server.command("start")
@click.option("--bg", is_flag=True, default=False,
              help="Inicia em background (log em server.log).")
@click.option("--pin-threads", is_flag=True, default=False,
              help="Ativa pinagem de threads quando suportado pelo backend.")
@click.option("--cont-batching", is_flag=True, default=False,
              help="Ativa continuous batching quando suportado pelo backend.")
def server_start(bg: bool, pin_threads: bool, cont_batching: bool) -> None:
    """Inicia o servidor de inferencia."""
    from engine.server.server import ServerCLI   # noqa
    args = ["start"]
    if bg:
        args.append("--bg")
    if pin_threads:
        args.append("--pin-threads")
    if cont_batching:
        args.append("--cont-batching")
    ServerCLI().run(args)


@server.command("stop")
def server_stop() -> None:
    """Para o servidor de inferencia."""
    from engine.server.server import ServerCLI   # noqa
    ServerCLI().run(["stop"])


@server.command("status")
def server_status() -> None:
    """Exibe uptime e estatisticas do servidor."""
    from engine.server.server import ServerCLI   # noqa
    ServerCLI().run(["status"])


@server.command("ask")
@click.argument("prompt", nargs=-1, required=True)
@click.option("--tokens", "-t", type=int, default=128)
def server_ask(prompt: tuple, tokens: int) -> None:
    """Consulta direta ao modelo via servidor."""
    from engine.server.server import ServerCLI   # noqa
    ServerCLI().run(["ask", " ".join(prompt), "--tokens", str(tokens)])


# ---------------------------------------------------------------------------
# web — grupo de subcomandos para orn-web
# ---------------------------------------------------------------------------

@cli.group()
def web() -> None:
    """Interface web local do ORN (porta 8372)."""
    pass


@web.command("start")
@click.option("--no-browser", is_flag=True, default=False,
              help="Nao abre o browser automaticamente.")
def web_start(no_browser: bool) -> None:
    """Inicia a interface web e abre o browser."""
    from engine.web.web_server import WebCLI   # noqa
    WebCLI().run(["start"] + (["--no-browser"] if no_browser else []))


@web.command("stop")
def web_stop() -> None:
    """Para a interface web."""
    from engine.web.web_server import WebCLI   # noqa
    WebCLI().run(["stop"])

# ---------------------------------------------------------------------------
# probe — telemetria operacional
# ---------------------------------------------------------------------------

@cli.group()
def probe() -> None:
    """Consulta telemetria e hotspots do servidor."""
    pass


@probe.command("status")
@click.option("--json-output", "json_output", is_flag=True, default=False,
              help="Exibe payload STATUS bruto em JSON.")
@click.option("--limit", type=int, default=5, show_default=True,
              help="Quantidade máxima de hotspots exibidos.")
@click.option("--strict", is_flag=True, default=False,
              help="Retorna código de erro quando o servidor estiver offline.")
@click.option("--out", type=click.Path(), default=None,
              help="Salva saída JSON em arquivo (útil no Windows sem /tmp).")
def probe_status(json_output: bool, limit: int, strict: bool, out: str | None) -> None:
    """Mostra status de telemetria do servidor (hotspots)."""
    from engine.telemetry.cli import normalize_status_payload, query_server_status  # noqa: PLC0415

    payload = query_server_status()
    if payload is None:
        if json_output:
            payload_text = json.dumps({"status": "offline", "error": "server_unreachable"}, ensure_ascii=False, indent=2)
            if out:
                t = Path(out)
                t.parent.mkdir(parents=True, exist_ok=True)
                t.write_text(payload_text + "\n", encoding="utf-8")
                Display.info(f"JSON salvo em: {t}")
            else:
                print(payload_text)
        else:
            Display.warn("Servidor offline. Execute: orn-server start")
        if strict:
            raise SystemExit(1)
        return

    if json_output:
        trimmed = dict(payload)
        if "telemetry_hotspots" in trimmed and isinstance(trimmed["telemetry_hotspots"], list):
            trimmed["telemetry_hotspots"] = trimmed["telemetry_hotspots"][:max(1, limit)]
        payload_text = json.dumps(trimmed, ensure_ascii=False, indent=2)
        if out:
            t = Path(out)
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_text(payload_text + "\n", encoding="utf-8")
            Display.info(f"JSON salvo em: {t}")
        else:
            print(payload_text)
        return

    payload, inferred = normalize_status_payload(payload)

    Display.section("PROBE", "orn-server status")
    Display.kv("status", str(payload.get("status", "unknown")))
    Display.kv("requests", str(payload.get("requests", 0)))
    Display.kv("errors", str(payload.get("errors", 0)))
    Display.kv("avg_elapsed_s", str(payload.get("avg_elapsed_s", 0)))

    boot = payload.get("boot_perf", {})
    if boot:
        Display.info("Boot perf:")
        print(f"  - vulcan_boot={_fmt_ms(boot.get('vulcan_boot_ms', 0))}")
        print(f"  - model_load={_fmt_ms(boot.get('model_load_ms', 0))}")

    system = payload.get("system_perf", {})
    if system:
        Display.info("System perf:")
        print(f"  - pid/threads={system.get('pid', 0)}/{system.get('threads', 0)}")
        print(f"  - cpu/load_1m={system.get('cpu_count', 0)}/{system.get('load_1m', 0)}")
        print(f"  - rss_mb={system.get('rss_mb', 0)}")

    ai = payload.get("ai_perf", {})
    if ai:
        Display.info("IA perf (compat)" if inferred else "IA perf:")
        print(f"  - infer_calls={ai.get('infer_calls', 0)}")
        print(f"  - last_infer={ai.get('last_infer_s', 0)}s")
        print(f"  - last_tokens_per_s={ai.get('last_tokens_per_s', 0)} tok/s")
        print(f"  - total_tokens_per_s={ai.get('total_tokens_per_s', 0)} tok/s")
        print(f"  - avg_prompt_chars={ai.get('avg_prompt_chars', 0)}")
        print(f"  - avg_output_chars={ai.get('avg_output_chars', 0)}")
        print(f"  - last_lock_wait={_fmt_ms(ai.get('last_lock_wait_ms', 0))}")
        print(f"  - last_llm_call={_fmt_ms(ai.get('last_llm_call_ms', 0))}")
        print(f"  - last_non_llm={_fmt_ms(ai.get('last_non_llm_ms', 0))}")
        print(f"  - last_llm_share={ai.get('last_llm_share_pct', 0)}%")

    hotspots = payload.get("telemetry_hotspots", [])
    if hotspots:
        total = sum(float(r.get("total_ms", 0) or 0) for r in hotspots) or 1.0
        Display.info("Hotspots:")
        for row in hotspots[:max(1, limit)]:
            share = (float(row.get("total_ms", 0) or 0) / total) * 100.0
            print(
                "  - "
                f"{row.get('name', '?')} calls={row.get('calls', 0)} "
                f"avg={_fmt_ms(row.get('avg_ms', 0))} p95={_fmt_ms(row.get('p95_ms', 0))} "
                f"total={_fmt_ms(row.get('total_ms', 0))} share={share:.1f}%"
            )

# ---------------------------------------------------------------------------
# T1 — Grupo `models` (catálogo de modelos GGUF)
# ---------------------------------------------------------------------------

@cli.group("models")
def models_group() -> None:
    """Catálogo de modelos GGUF (list, show, use, scan, verify)."""

@models_group.command("merge")
@click.argument("adapter")
@click.option("--base", required=True, type=click.Path(exists=True),
              help="GGUF base F16.")
@click.option("--out", required=True, type=click.Path(),
              help="GGUF de saída (F16 fundido).")
@click.option("--scale", default="auto", show_default=True,
              help="'auto' usa alpha/r do adapter_config.json.")
@click.option("--force", is_flag=True, default=False,
              help="Sobrescreve --out se existir.")

def models_merge(adapter: str, base: str, out: str, scale: str, force: bool) -> None:
    from engine.training.merge import merge_lora, load_adapter_config
    from engine.tools.model_catalog import resolve_alias
    from pathlib import Path as _P

    # Resolução do adapter, em ordem de precedência:
    # 1. path literal (se usuário passou caminho completo)
    # 2. data/training/<adapter>
    # 3. alias de modelo no catálogo (raro — adapter não é modelo, mas por consistência)
    candidate_paths = [
        _P(adapter),
        _P("data") / "training" / adapter,
    ]
    adapter_path = None
    for c in candidate_paths:
        if c.exists() and c.is_dir():
            adapter_path = c
            break
    if adapter_path is None:
        alias_resolved = resolve_alias(adapter)
        if alias_resolved is not None and alias_resolved.parent.is_dir():
            adapter_path = alias_resolved.parent
    if adapter_path is None:
        Display.error(f"adapter não encontrado: {adapter}")
        Display.info("Tentou: " + ", ".join(str(c) for c in candidate_paths))
        raise SystemExit(1)

    Display.section("MERGE", f"{adapter} → {out}")
    Display.kv("base",    base)
    Display.kv("adapter", str(adapter_path))
    Display.kv("out",     out)

    scale_val: float | str = scale
    if scale == "auto":
        try:
            cfg = load_adapter_config(adapter_path)
            r = cfg.get("r", 8)
            alpha = cfg.get("lora_alpha", 16)
            Display.kv("scale", f"auto (alpha/r = {alpha}/{r} = {alpha/r:.2f})")
        except Exception:
            pass

    result = merge_lora(
        base_gguf=_P(base),
        adapter_dir=adapter_path,
        out_gguf=_P(out),
        scale=scale_val,
        force=force,
    )

    if not result.success:
        for err in result.errors:
            Display.error(err)
        raise SystemExit(1)

    Display.separator()
    Display.success(
        f"{result.fused_tensors} tensor(es) fundido(s), "
        f"{result.skipped_tensors} pulado(s) em {result.elapsed_s}s"
    )
    Display.kv("out",   str(result.output_path))
    Display.kv("scale", f"{result.scale:.4f}")
    if result.errors:
        Display.warn(f"{len(result.errors)} erro(s) não-fatal(is):")
        for e in result.errors[:5]:
            Display.info(f"  - {e}")


@models_group.command("quantize")
@click.argument("input_gguf", type=click.Path(exists=True))
@click.option("--type", "quant_type",
              type=click.Choice(["q2_k", "q3_k_m", "q4_k_m", "q5_k_m", "q6_k", "q8_0"]),
              default="q4_k_m", show_default=True)
@click.option("--out", type=click.Path(), default=None,
              help="Saída (default: <input>-<type>.gguf).")
@click.option("--force", is_flag=True, default=False)
def models_quantize(input_gguf: str, quant_type: str, out: str | None, force: bool) -> None:
    from engine.training.quantize import quantize_gguf
    from pathlib import Path as _P

    inp = _P(input_gguf)
    if out is None:
        out = str(inp.with_name(f"{inp.stem}-{quant_type}.gguf"))

    Display.section("QUANTIZE", f"{inp.name} → {quant_type.upper()}")
    Display.kv("input",  str(inp))
    Display.kv("output", out)

    result = quantize_gguf(inp, _P(out), quant_type, force=force)

    if not result.success:
        Display.error(result.error or "quantize falhou")
        raise SystemExit(1)

    Display.separator()
    Display.success(
        f"{result.quant_type} gerado em {result.elapsed_s}s "
        f"({result.size_mb} MB)"
    )
    Display.kv("path", str(result.output_path))

@models_group.command("list")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Saída em JSON bruto.")
def models_list(as_json: bool) -> None:
    from engine.training.registry import ModelRegistry
    reg = ModelRegistry()
    entries = reg.all()
    active = reg.active_alias()

    if as_json:
        out = {
            "active_alias": active,
            "models": [
                {
                    "alias": e.alias,
                    "path": str(e.path),
                    "quant": e.quant,
                    "base": e.base,
                    "size_mb": e.size_mb,
                    "tags": e.tags,
                    "active": e.alias == active,
                }
                for e in entries
            ],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    Display.section("MODELS", f"{len(entries)} entradas — ativo: {active or '(nenhum)'}")
    for e in entries:
        marker = " ✓" if e.alias == active else "  "
        size = f"{e.size_mb:>7.1f} MB" if e.size_mb else "        ?"
        tags = ",".join(e.tags) if e.tags else "-"
        print(f"{marker} {e.alias:<22} {size}  {e.quant:<7}  [{tags}]")
        if not e.path.exists():
            Display.warn(f"    arquivo ausente: {e.path}")


@models_group.command("show")
@click.argument("alias")
@click.option("--json", "as_json", is_flag=True, default=False)
def models_show(alias: str, as_json: bool) -> None:
    from engine.training.registry import ModelRegistry
    reg = ModelRegistry()
    entry = reg.get(alias)
    if entry is None:
        Display.error(f"alias não catalogado: {alias!r}")
        raise SystemExit(1)

    ok, motivo = reg.verify(alias)

    if as_json:
        print(json.dumps({
            "alias": entry.alias,
            "path": str(entry.path),
            "base": entry.base,
            "quant": entry.quant,
            "adapter": entry.adapter,
            "tags": entry.tags,
            "source": entry.source,
            "created_at": entry.created_at,
            "size_mb": entry.size_mb,
            "sha256": entry.sha256,
            "verify_ok": ok,
            "verify_msg": motivo,
        }, ensure_ascii=False, indent=2))
        return

    Display.section("MODEL", entry.alias)
    Display.kv("path",       str(entry.path))
    Display.kv("base",       entry.base)
    Display.kv("quant",      entry.quant)
    if entry.adapter:
        Display.kv("adapter", entry.adapter)
    Display.kv("tags",       ", ".join(entry.tags) or "-")
    Display.kv("source",     entry.source)
    Display.kv("created_at", entry.created_at)
    Display.kv("size_mb",    str(entry.size_mb) if entry.size_mb else "?")
    Display.kv("sha256",     (entry.sha256[:16] + "...") if entry.sha256 else "(não calculado)")
    Display.separator()
    if ok:
        Display.success(motivo)
    else:
        Display.warn(motivo)


@models_group.command("use")
@click.argument("alias")
def models_use(alias: str) -> None:
    from engine.training.registry import ModelRegistry
    reg = ModelRegistry()
    entry = reg.get(alias)
    if entry is None:
        Display.error(f"alias não catalogado: {alias!r}")
        Display.info("Use `orn models list` para ver os disponíveis.")
        raise SystemExit(1)
    if not entry.path.exists():
        Display.warn(f"arquivo ausente: {entry.path} — ativando mesmo assim")
    reg.set_active(alias)
    Display.success(f"active_alias = {alias}")
    Display.info(f"Próximo `orn think` usará {entry.path.name}")


@models_group.command("scan")
@click.option("--dir", "models_dir", type=click.Path(),
              default="models", show_default=True,
              help="Diretório para escanear.")
@click.option("--hash", "compute_hash", is_flag=True, default=False,
              help="Calcula sha256 (lento, ~10-20s).")
def models_scan(models_dir: str, compute_hash: bool) -> None:
    from engine.training.registry import ModelRegistry
    reg = ModelRegistry()
    rows = reg.scan(models_dir=models_dir, compute_hash=compute_hash)

    if not rows:
        Display.warn(f"nenhum .gguf em {models_dir}")
        return

    known = [r for r in rows if r["known"]]
    unknown = [r for r in rows if not r["known"]]

    Display.section("SCAN", f"{len(rows)} arquivo(s) .gguf em {models_dir}")
    for r in rows:
        marker = "✓" if r["known"] else "?"
        alias = r["alias"] or "(não catalogado)"
        hash_str = f" sha256={r['sha256'][:12]}..." if r["sha256"] else ""
        print(f"  [{marker}] {alias:<22} {r['size_mb']:>7.1f} MB  {r['path']}{hash_str}")

    # Atualiza cache local com size_mb/sha256
    if compute_hash or known:
        cache = mc_load_local()
        cache.setdefault("models", {})
        for r in known:
            if r["alias"]:
                row = cache["models"].setdefault(r["alias"], {})
                row["size_mb"] = r["size_mb"]
                if r["sha256"]:
                    row["sha256"] = r["sha256"]
        mc_save_local(cache)

    Display.separator()
    Display.success(f"{len(known)} catalogado(s), {len(unknown)} não catalogado(s)")
    if unknown:
        Display.info("Adicione manualmente em data/model_catalog.json ou aguarde `orn models import` (T1.1)")


def mc_load_local() -> dict:
    from engine.tools import model_catalog
    return model_catalog.load_local_cache()


def mc_save_local(data: dict) -> None:
    from engine.tools import model_catalog
    model_catalog.save_local_cache(data)


@models_group.command("verify")
@click.argument("alias")
def models_verify(alias: str) -> None:
    from engine.training.registry import ModelRegistry
    reg = ModelRegistry()
    ok, motivo = reg.verify(alias)
    if ok:
        Display.success(f"{alias}: {motivo}")
    else:
        Display.warn(f"{alias}: {motivo}")
        raise SystemExit(1)

# ---------------------------------------------------------------------------
# T2 — Grupo `data` (dataset builder)
# ---------------------------------------------------------------------------

@cli.group("data")
def data_group() -> None:
    """Datasets de treino (build, inspect, preview, list, stats)."""

@data_group.command("gen-diffs")
@click.argument("name")
@click.option("--sources", "-s", required=True,
              help="Arquivos/pastas separados por vírgula (.py).")
@click.option("--max-per-file", type=int, default=20, show_default=True,
              help="Mutações máximas por arquivo.")
@click.option("--out", default="data/processed", show_default=True,
              type=click.Path(),
              help="Diretório de saída (pai do <name>).")
def data_gen_diffs(name: str, sources: str, max_per_file: int, out: str) -> None:
    """Gera dataset de diffs a partir de código Python válido."""
    from engine.tools.diff_dataset import build_diff_dataset

    src_list = [s.strip() for s in sources.split(",") if s.strip()]
    if not src_list:
        Display.error("--sources vazio")
        raise SystemExit(1)

    Display.section("DATA GEN-DIFFS", name)
    for s in src_list:
        Display.kv("source", s)
    Display.kv("max_per_file", str(max_per_file))
    Display.separator()

    manifest = build_diff_dataset(
        sources=src_list,
        name=name,
        out_dir=out,
        max_per_file=max_per_file,
    )
    stats = manifest["stats"]

    Display.success(
        f"{stats['total']} amostras "
        f"({stats['train']} train / {stats['val']} val)"
    )
    Display.kv("files_scanned",      str(stats["files_scanned"]))
    Display.kv("files_with_mut",     str(stats["files_with_mutations"]))
    Display.kv("mutations_gen",      str(stats["mutations_generated"]))
    Display.kv("mutations_valid",    str(stats["mutations_validated"]))
    Display.kv("manifest",           str(Path(out) / name / "manifest.json"))

    if manifest["warning"]:
        Display.warn(manifest["warning"])

@data_group.command("build")
@click.argument("name")
@click.option("--sources", "-s", required=True,
              help="Arquivos separados por vírgula (.jsonl ou .txt).")
@click.option("--dedup", type=click.Choice(["hash", "none"]), default="hash",
              show_default=True)
@click.option("--strict", is_flag=True, default=False,
              help="Dedup com normalização de whitespace (mais agressivo).")
@click.option("--split", type=float, default=0.9, show_default=True,
              help="Fração para train (resto vai para val).")
@click.option("--by", type=click.Choice(["line", "source"]), default="line",
              show_default=True,
              help="Split por linha ou por arquivo-fonte.")
def data_build(name: str, sources: str, dedup: str, strict: bool,
               split: float, by: str) -> None:
    from engine.training.dataset import DatasetBuilder
    src_list = [s.strip() for s in sources.split(",") if s.strip()]
    if not src_list:
        Display.error("--sources vazio")
        raise SystemExit(1)

    Display.section("DATA BUILD", name)
    for s in src_list:
        Display.kv("source", s)

    builder = DatasetBuilder(name)
    manifest = builder.build(
        src_list, dedup=dedup, strict=strict, split=split, by=by,
    )

    Display.separator()
    Display.success(
        f"{manifest.stats['train']} train / {manifest.stats['val']} val "
        f"({manifest.stats['total']} total)"
    )
    Display.kv("by_lang",   str(manifest.stats.get("by_lang", {})))
    Display.kv("by_task",   str(manifest.stats.get("by_task", {})))
    Display.kv("manifest",  str(Path("data/processed") / name / "manifest.json"))

    if manifest.warning:
        Display.warn(manifest.warning)


@data_group.command("inspect")
@click.argument("name")
def data_inspect(name: str) -> None:
    from engine.training.dataset import DatasetBuilder
    try:
        m = DatasetBuilder.inspect(name)
    except (FileNotFoundError, RuntimeError) as exc:
        Display.error(str(exc))
        raise SystemExit(1)

    Display.section("DATA INSPECT", name)
    Display.kv("created_at", m.get("created_at", "?"))
    stats = m.get("stats", {})
    Display.kv("total",   str(stats.get("total", 0)))
    Display.kv("train/val", f"{stats.get('train', 0)} / {stats.get('val', 0)}")
    Display.kv("by_lang", str(stats.get("by_lang", {})))
    Display.kv("by_source", str(stats.get("by_source", {})))
    Display.kv("by_task", str(stats.get("by_task", {})))
    Display.kv("avg_chars", str(stats.get("avg_chars", 0)))
    sizes = stats.get("sizes_mb", {})
    if sizes:
        Display.separator()
        for k, v in sizes.items():
            Display.kv(k, f"{v} MB")
    Display.separator()
    if m.get("sufficient"):
        Display.success("dataset suficiente para treino útil")
    else:
        Display.warn(m.get("warning") or "dataset pode ser insuficiente")


@data_group.command("preview")
@click.argument("name")
@click.option("-n", "n", type=int, default=3, show_default=True)
def data_preview(name: str, n: int) -> None:
    from engine.training.dataset import DatasetBuilder
    try:
        previews = DatasetBuilder.preview(name, n=n)
    except (FileNotFoundError, RuntimeError) as exc:
        Display.error(str(exc))
        raise SystemExit(1)
    if not previews:
        Display.warn("nenhuma amostra encontrada")
        return
    for i, p in enumerate(previews, 1):
        Display.separator()
        print(f"  [{i}]")
        for line in p.splitlines():
            print(f"  {line}")


@data_group.command("list")
def data_list() -> None:
    from engine.training.dataset import DatasetBuilder
    names = DatasetBuilder.list_processed()
    if not names:
        Display.warn("nenhum dataset em data/processed/")
        return
    Display.section("DATA LIST", f"{len(names)} dataset(s)")
    for name in names:
        try:
            m = DatasetBuilder.inspect(name)
            s = m.get("stats", {})
            print(f"  {name:<24} {s.get('train', 0):>5} train / "
                  f"{s.get('val', 0):>4} val")
        except Exception:
            print(f"  {name:<24} (manifest ilegível)")


@data_group.command("stats")
@click.argument("name")
def data_stats(name: str) -> None:
    from engine.training.dataset import DatasetBuilder
    try:
        info = DatasetBuilder.stats(name)
    except (FileNotFoundError, RuntimeError) as exc:
        Display.error(str(exc))
        raise SystemExit(1)

    Display.section("DATA STATS", name)
    stats = info.get("stats", {})
    Display.kv("total",    str(stats.get("total", 0)))
    Display.kv("train",    str(stats.get("train", 0)))
    Display.kv("val",      str(stats.get("val", 0)))
    Display.kv("by_lang",  str(stats.get("by_lang", {})))
    Display.kv("by_task",  str(stats.get("by_task", {})))
    Display.separator()
    if info.get("sufficient"):
        Display.success("dataset suficiente (>= 100 amostras únicas)")
    else:
        Display.warn(info.get("warning") or "insuficiente")

# ---------------------------------------------------------------------------
# T3.A — Grupo `tools` (provisionamento nativo)
# ---------------------------------------------------------------------------

@cli.group("tools")
def tools_group() -> None:
    """Ferramentas nativas (provision, list, which)."""


@tools_group.command("provision")
@click.option("--profile", type=click.Choice(["auto", "1235u", "portable"]),
              default="auto", show_default=True,
              help="Perfil de otimização da CPU.")
@click.option("--check-only", is_flag=True, default=False,
              help="Só verifica, não builda.")
@click.option("--tool", "tools", multiple=True,
              help="Targets específicos (default: llama-quantize).")
def tools_provision(profile: str, check_only: bool, tools: tuple) -> None:
    from engine.tools.provision import provision, check_all, detect_profile
    targets = list(tools) if tools else ["llama-quantize"]
    prof = profile if profile != "auto" else detect_profile()

    Display.section("TOOLS PROVISION", f"profile={prof}")
    if check_only:
        for name, path in check_all().items():
            if path:
                Display.success(f"{name}: {path}")
            else:
                Display.warn(f"{name}: não encontrado")
        return

    results = provision(targets, profile=prof, check_only=False)
    for r in results:
        if r.found and r.built:
            Display.success(f"{r.tool}: compilado em {r.elapsed_s}s → {r.path}")
        elif r.found:
            Display.info(f"{r.tool}: já existe → {r.path}")
        else:
            Display.error(f"{r.tool}: {r.error}")


@tools_group.command("which")
@click.argument("tool")
def tools_which(tool: str) -> None:
    from engine.tools.provision import find_tool
    p = find_tool(tool)
    if p:
        Display.success(f"{tool}: {p}")
    else:
        Display.warn(f"{tool}: não encontrado")
        Display.info("Rode `orn tools provision` para compilar.")


@tools_group.command("list")
def tools_list() -> None:
    from engine.tools.provision import check_all
    Display.section("TOOLS", "binários nativos")
    for name, path in check_all().items():
        if path:
            Display.kv(name, str(path))
        else:
            Display.kv(name, "(ausente)")

# ---------------------------------------------------------------------------
# T4 — Grupo `train` (LoRA) + `orn models import`
# ---------------------------------------------------------------------------

@cli.group("train")
def train_group() -> None:
    """Treino LoRA (lora, status, eval)."""


@train_group.command("lora")
@click.argument("name")
@click.option("--data", "data_dir", required=True,
              type=click.Path(exists=True),
              help="Dataset em data/processed/<nome>/")
@click.option("--base", default="HuggingFaceTB/SmolLM2-135M-Instruct",
              help="Modelo base do HuggingFace.")
@click.option("--out", default=None, help="Saída (default: data/training/<name>)")
@click.option("--rank", type=int, default=8, show_default=True)
@click.option("--alpha", type=int, default=16, show_default=True)
@click.option("--dropout", type=float, default=0.05, show_default=True)
@click.option("--target-modules", default="q_proj,k_proj,v_proj,o_proj",
              show_default=True)
@click.option("--epochs", type=int, default=3, show_default=True)
@click.option("--batch-size", type=int, default=4, show_default=True)
@click.option("--grad-accum", type=int, default=2, show_default=True)
@click.option("--lr", type=float, default=5e-5, show_default=True)
@click.option("--max-length", type=int, default=512, show_default=True)
@click.option("--patience", type=int, default=2, show_default=True)
@click.option("--qlora", is_flag=True, default=False,
              help="QLoRA 4-bit (requer bitsandbytes).")
@click.option("--dtype", type=click.Choice(["fp32", "fp16", "bf16"]),
              default="fp32", show_default=True)
def train_lora_cmd(name, data_dir, base, out, rank, alpha, dropout,
                   target_modules, epochs, batch_size, grad_accum, lr,
                   max_length, patience, qlora, dtype) -> None:
    from engine.training.train import TrainConfig, train_lora

    Display.section("TRAIN LORA", name)
    Display.kv("data",    data_dir)
    Display.kv("base",    base)
    Display.kv("rank/α",  f"{rank}/{alpha}")
    Display.kv("targets", target_modules)
    Display.kv("epochs",  str(epochs))
    Display.kv("lr",      str(lr))
    Display.kv("qlora",   str(qlora))
    Display.kv("dtype",   dtype)
    Display.separator()

    cfg = TrainConfig(
        name=name,
        data_dir=Path(data_dir),
        base_model=base,
        out_dir=Path(out) if out else None,
        rank=rank, alpha=alpha, dropout=dropout,
        target_modules=[t.strip() for t in target_modules.split(",") if t.strip()],
        epochs=epochs, batch_size=batch_size, grad_accum=grad_accum,
        lr=lr, max_length=max_length, patience=patience,
        qlora=qlora, dtype=dtype,
    )

    result = train_lora(cfg)

    if not result.success:
        for e in result.errors:
            Display.error(e)
        raise SystemExit(1)

    Display.separator()
    Display.success(
        f"treinado em {result.elapsed_s}s — "
        f"train_loss={result.final_loss} val_loss={result.val_loss}"
    )
    Display.kv("adapter", str(result.adapter_dir))
    Display.info("Próximo passo: orn models merge ... --base <gguf> --out ...")


@train_group.command("status")
@click.argument("name", required=False)
def train_status(name: str | None) -> None:
    from pathlib import Path as _P
    root = _P("data") / "training"
    if name:
        d = root / name
        if not d.exists():
            Display.error(f"adapter não encontrado: {d}")
            raise SystemExit(1)
        _print_adapter_status(d)
        return
    if not root.exists():
        Display.warn("data/training/ vazio")
        return
    Display.section("TRAIN STATUS", "adapters")
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if (d / "adapter_model.safetensors").exists():
            _print_adapter_status(d, compact=True)


def _print_adapter_status(d: Path, compact: bool = False) -> None:
    from pathlib import Path as _P
    cfg_p = d / "adapter_config.json"
    state_p = d / "trainer_state.json"
    r_str, a_str = "?", "?"
    if cfg_p.exists():
        try:
            c = json.loads(cfg_p.read_text(encoding="utf-8"))
            r_str = str(c.get("r", "?"))
            a_str = str(c.get("lora_alpha", "?"))
        except Exception:
            pass
    if compact:
        print(f"  {d.name:<30} r={r_str} α={a_str}")
    else:
        Display.section("ADAPTER", d.name)
        Display.kv("path",   str(d))
        Display.kv("rank",   r_str)
        Display.kv("alpha",  a_str)
    if state_p.exists():
        try:
            s = json.loads(state_p.read_text(encoding="utf-8"))
            log = s.get("log_history", [])
            train_l = [e for e in log if "loss" in e and "eval_loss" not in e]
            val_l   = [e for e in log if "eval_loss" in e]
            if train_l:
                last = train_l[-1]
                print(f"  last train_loss: {last['loss']:.4f}  (step {last.get('step','?')})")
            if val_l:
                last = val_l[-1]
                print(f"  last val_loss:   {last['eval_loss']:.4f}")
            if len(train_l) >= 2:
                first = train_l[0]['loss']
                final = train_l[-1]['loss']
                drop = (first - final) / first * 100 if first else 0
                print(f"  Δ train:         {first:.4f} → {final:.4f} ({drop:+.1f}%)")
        except Exception as exc:
            print(f"  (trainer_state ilegível: {exc})")


@models_group.command("import")
@click.argument("path", type=click.Path(exists=True))
@click.option("--alias", required=True)
@click.option("--base",   default="")
@click.option("--quant",  default="")
@click.option("--adapter", default="")
@click.option("--tags",   default="",
              help="Tags separadas por vírgula.")
def models_import(path, alias, base, quant, adapter, tags) -> None:
    from engine.tools.model_catalog import (
        load_catalog, save_catalog, catalog_path,
    )
    from pathlib import Path as _P
    from datetime import datetime, timezone

    cat = load_catalog()
    if alias in cat.get("models", {}):
        Display.warn(f"alias '{alias}' já existe no catálogo — sobrescrevendo")

    entry = {
        "path":       str(_P(path)).replace("\\", "/"),
        "base":       base,
        "quant":      quant or "F16",
        "tags":       [t.strip() for t in tags.split(",") if t.strip()],
        "source":     "local",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    if adapter:
        entry["adapter"] = adapter

    cat.setdefault("models", {})[alias] = entry
    save_catalog(cat)
    Display.success(f"importado: {alias} → {entry['path']}")


@models_group.command("unimport")
@click.argument("alias")
def models_unimport(alias: str) -> None:
    """Remove um alias do catálogo (NÃO deleta o arquivo .gguf)."""
    from engine.tools.model_catalog import load_catalog, save_catalog
    cat = load_catalog()
    if alias not in cat.get("models", {}):
        Display.error(f"alias não catalogado: {alias}")
        raise SystemExit(1)
    del cat["models"][alias]
    if cat.get("active_alias") == alias:
        cat["active_alias"] = None
    save_catalog(cat)
    Display.success(f"removido do catálogo: {alias}")

# ---------------------------------------------------------------------------
# RAG — Grupo `consult` (busca + ask no acervo Doxoade)
# ---------------------------------------------------------------------------

@cli.group("consult")
def consult_group() -> None:
    """Acervo Consult: busca FTS5 + RAG via LLM."""


@consult_group.command("search")
@click.argument("query", nargs=-1, required=True)
@click.option("--limit", "-n", type=int, default=5, show_default=True)
@click.option("--category", "-c", default=None,
              help="Filtrar por categoria (ex: python_basic_py4e).")
@click.option("--json", "as_json", is_flag=True, default=False)
def consult_search(query: tuple, limit: int, category: str | None, as_json: bool) -> None:
    """Busca no acervo FTS5 (sem LLM — instantâneo)."""
    from engine.tools.consult_bridge import ConsultBridge

    q = " ".join(query).strip()
    if not q:
        raise click.UsageError("query vazia")

    cb = ConsultBridge()
    if not cb.is_available():
        Display.error(f"Banco consult não encontrado: {cb.db_path}")
        Display.info("Execute no projeto doxoade: doxoade consult index")
        raise SystemExit(1)

    results = cb.search(q, limit=limit, category=category)

    if as_json:
        import json as _json
        print(_json.dumps(
            [{"path": r.path, "title": r.title, "snippet": r.snippet,
              "category": r.category} for r in results],
            ensure_ascii=False, indent=2,
        ))
        return

    if not results:
        Display.warn(f"Nenhum resultado para: {q!r}")
        return

    Display.section("CONSULT SEARCH", f"{len(results)} resultado(s) — {q!r}")
    for i, r in enumerate(results, 1):
        print(f"\n  [{i}] {r.title}")
        Display.kv("path", r.path)
        if r.category:
            Display.kv("category", r.category)
        print(f"  {r.snippet[:400]}")
    print()


@consult_group.command("ask")
@click.argument("question", nargs=-1, required=True)
@click.option("--limit", "-n", type=int, default=3, show_default=True,
              help="Nº de fontes injetadas no prompt.")
@click.option("--tokens", "-t", type=int, default=None)
@click.option("--model", "-m", default=None)
def consult_ask(question: tuple, limit: int, tokens: int | None,
                model: str | None) -> None:
    """RAG: busca no consult + pergunta ao LLM (resposta ancorada)."""
    from engine.tools.consult_bridge import ConsultBridge
    from engine.core.executive import SiCDoxExecutive, _adaptive_max_tokens

    q = " ".join(question).strip()
    if not q:
        raise click.UsageError("question vazia")

    cb = ConsultBridge()
    if not cb.is_available():
        Display.error(f"Banco consult não encontrado: {cb.db_path}")
        raise SystemExit(1)

    results = cb.search(q, limit=limit)
    context = cb.format_context(results) if results else ""

    if results:
        Display.info(f"[CONSULT] {len(results)} fonte(s) injetada(s).")
    else:
        Display.warn(f"[CONSULT] Nenhum contexto encontrado — respondendo sem RAG.")

    if model:
        os.environ["ORN_MODEL_ALIAS"] = model

    full_prompt = q
    if context:
        full_prompt = f"{context}\n[QUESTION]\n{q}"

    max_tokens = tokens or _adaptive_max_tokens(q)

    Display.banner()
    Display.thinking(q)

    ex = SiCDoxExecutive()
    try:
        result = ex.process_goal(
            intent="think",
            payload=full_prompt,
            context={
                "max_tokens": max_tokens,
                "context_file": None,
                "search_code_only": False,
                "use_server": False,
            },
        )
    finally:
        ex.shutdown()

    if not result.success:
        for e in result.errors:
            Display.error(e)
        raise SystemExit(1)

    Display.separator()
    Display.code_block(result.output)
    Display.separator()
    Display.info(f"Tempo: {result.metadata.get('elapsed_s', '?')}s")

    if results:
        Display.info("Fontes utilizadas:")
        for r in results:
            print(f"  - {r.path}")


@consult_group.command("list")
def consult_list() -> None:
    """Lista categorias e volume do acervo."""
    from engine.tools.consult_bridge import ConsultBridge

    cb = ConsultBridge()
    if not cb.is_available():
        Display.error("Banco consult não encontrado.")
        raise SystemExit(1)

    cats = cb.list_categories()
    if not cats:
        Display.warn("Banco vazio.")
        return

    total = sum(cats.values())
    Display.section("CONSULT", f"{len(cats)} categorias — {total} docs totais")
    for cat, count in cats.items():
        pct = (count / total * 100) if total else 0
        bar = "█" * int(pct / 3)
        print(f"  {cat:<38} {count:>5}  {bar}  {pct:.1f}%")


@consult_group.command("stats")
@click.option("--json", "as_json", is_flag=True, default=False)
def consult_stats(as_json: bool) -> None:
    """Estatísticas completas do banco."""
    from engine.tools.consult_bridge import ConsultBridge

    stats = ConsultBridge().stats()

    if as_json:
        import json as _json
        print(_json.dumps(stats, ensure_ascii=False, indent=2))
        return

    if not stats.get("available"):
        Display.error(f"Banco indisponível: {stats.get('db_path')}")
        raise SystemExit(1)

    Display.section("CONSULT STATS", "estado do acervo")
    Display.kv("db_path",   stats["db_path"])
    Display.kv("size_mb",   f"{stats['size_mb']} MB")
    Display.kv("total_docs", str(stats["total_docs"]))
    Display.kv("total_fts",  str(stats["total_fts"]))
    Display.kv("categorias", str(len(stats.get("categories", {}))))
