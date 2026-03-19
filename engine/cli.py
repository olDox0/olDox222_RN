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

import os
import sys
import json
import time
import re
import click

from pathlib import Path

from engine.ui.display import Display

def _fmt_ms(value: float) -> str:
    value = float(value or 0)
    if value >= 1000:
        return f"{value / 1000.0:.3f}s"
    return f"{value:.3f}ms"


def _guess_lang_from_prompt(prompt: str) -> str:
    p = (prompt or "").lower()
    if "python" in p:
        return "python"
    if "javascript" in p or "js" in p:
        return "javascript"
    if "typescript" in p or "ts" in p:
        return "typescript"
    if "java" in p:
        return "java"
    if "c++" in p or "cpp" in p:
        return "cpp"
    if "c#" in p or "csharp" in p:
        return "csharp"
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
def think(prompt: tuple[str, ...], context_file: str | None,
          raw: bool, tokens: int | None, direct: bool,
          search: str | None, search_code_only: bool, drawer_first: bool,
          drawer_only: bool, drawer_auto_save: bool, no_auto: bool, telemetry: bool) -> None:
    """Pergunta livre ao Qwen. Ex: orn think 'como faço X em Python?'"""
    import time

    from engine.telemetry.runtime import record_direct

    telemetry_enabled = telemetry or (os.environ.get("ORN_TELEMETRY", "") == "1")
    question = " ".join(prompt).strip()
    if tokens is not None:
        max_tokens = tokens
    else:
        # Busca focada em código tende a precisar menos verbosidade.
        max_tokens = 96 if search_code_only else 128

    context_blocks: list[str] = []
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
        else:
            Display.code_block(drawer_snippet.code)
        Display.info("Tempo: ~0s  [drawer-only]")
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

    if search_code_only and drawer_snippet is not None and tokens is None:
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
        from engine.tools.server_client import query as server_query  # noqa: PLC0415

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
                payload=full_prompt,
                context={
                    "context_file": None,
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
    Display.kv("use_mmap",      str(cfg.use_mmap))
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
    Display.info("Verificação de ambiente (first_contact):")
    issues = check_environment()
    if not issues:
        Display.success("Ambiente OK — pronto para `orn think`.")
    else:
        for issue in issues:
            Display.warn(issue)




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
    """Mostra guia rápido com comandos principais do ORN."""
    click.echo(
        """
=== ORN TUTORIAL (GUIA RÁPIDO) ===

1) Perguntas para IA
   orn think "explique quicksort em python"

2) Servidor de inferência (recomendado para uso contínuo)
   orn server start
   orn server status
   orn server ask "resuma esse texto" --tokens 128
   orn server stop

3) Interface Web
   orn web start
   orn web stop

4) Telemetria / saúde operacional
   orn probe status
   orn probe status --json-output --out status.json

   5) Index local (atalho para engine.tools.local_index)
   orn index list
   orn index info wikipedia_pt_computer_maxi_2026_01
   orn index search wikipedia_pt_computer_maxi_2026_01 "quicksort python"
   orn index search wikipedia_pt_computer_maxi_2026_01 "quicksort python" --code-only
   orn index preload wikipedia_pt_computer_maxi_2026_01

6) Code Drawer / Code Assembler (sem gastar token com remontagem)
   orn drawer add --name quicksort --lang python --in "list[int]" --out "list[int]" --file quicksort.py
   orn drawer list --lang python
   orn drawer show quicksort --lang python
   orn drawer assemble --name quicksort --lang python --in "list[int]" --out "list[int]"
   orn think "faça quicksort python" --drawer-first
   orn think "faça quicksort python" --drawer-first --drawer-only

Dica: use `orn <comando> --help` para detalhes.
        """.strip()
    )


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
    """[Fase 2] Analisa AST + aponta problemas. Ex: orn audit main.py"""
    Display.section("AUDIT", target)
    Display.not_implemented("audit")


@cli.command()
@click.argument("target", type=click.Path(exists=True))
@click.option("--apply", is_flag=True, default=False,
              help="Aplica o patch sugerido diretamente no arquivo.")
def fix(target: str, apply: bool) -> None:
    """[Fase 4] Sugere ou aplica correções. Ex: orn fix buggy.py"""
    Display.section("FIX", target)
    Display.not_implemented("fix")


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
    from engine.core.executive import SiCDoxExecutive  # noqa: PLC0415

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
@click.option("--tokens", type=int, default=96, show_default=True, help="Max tokens por execução.")
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
