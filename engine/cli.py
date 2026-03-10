# -*- coding: utf-8 -*-
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
from pathlib import Path
import click

from engine.ui.display import Display
from engine.telemetry.runtime import record, system_stats


def _fmt_ms(value: float) -> str:
    value = float(value or 0)
    if value >= 1000:
        return f"{value / 1000.0:.3f}s"
    return f"{value:.3f}ms"


# ---------------------------------------------------------------------------
# Grupo raiz
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(package_name="orn")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """ORN — AI CLI para código (Qwen2.5-Coder local)."""
    ctx.ensure_object(dict)


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
@click.option("--no-auto", is_flag=True, default=False,
              help="Desativa busca autônoma (two-pass) nesta chamada.")
@click.option("--telemetry", is_flag=True, default=False,
              help="Ativa telemetria detalhada para modo direto (grava telemetry/direct_runtime.jsonl).")
def think(prompt: tuple[str, ...], context_file: str | None,
          raw: bool, tokens: int | None, direct: bool,
          search: str | None, no_auto: bool, telemetry: bool) -> None:
    """Pergunta livre ao Qwen. Ex: orn think 'como faço X em Python?'"""
    from engine.telemetry.runtime import record, system_stats
    import time
    import os

    # permitir também via env var
    telemetry_enabled = telemetry or (os.environ.get("ORN_TELEMETRY", "") == "1")

    # Pergunta pura — imutável durante toda a montagem do prompt
    question   = " ".join(prompt)
    max_tokens = tokens or 128

    # Blocos de contexto acumulados — cada um no formato [CTX-BEGIN/END]
    context_blocks: list[str] = []

    # --search manual: busca e acumula bloco
    if search:
        from engine.tools.crawler import OrnCrawler   # noqa: PLC0415
        src_key, _, sq = search.partition(":")
        if sq:
            crawl_query, crawl_source = sq.strip(), src_key.strip()
        else:
            crawl_query, crawl_source = search.strip(), "auto"
        Display.info(f"[CRAWLER] Buscando: [{crawl_source}] {crawl_query!r}")
        try:
            crawler = OrnCrawler()
            result  = crawler.search(crawl_query, source=crawl_source)
            if result.ok:
                Display.success(f"[CRAWLER] {result.source}: {result.title!r}")
                context_blocks.append(result.to_prompt_block())
            else:
                Display.warn(f"[CRAWLER] {result.error}")
        except Exception as _ce:
            Display.warn(f"[CRAWLER] Erro: {_ce}")

    # --file: lê arquivo e acumula bloco
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

    Display.banner()
    Display.thinking(question)

    # ---------------------------------------------------------------
    # MODO SERVIDOR
    # ---------------------------------------------------------------
    from engine.tools.server_client import is_server_online, ask as server_ask  # noqa

    use_server = (not direct) and is_server_online()

    if use_server:
        Display.info("Modo servidor ativo — sem espera de load.")

        # -----------------------------------------------------------
        # TWO-PASS AUTÔNOMO
        # Condições: servidor ativo + sem contexto manual + não desativado
        # -----------------------------------------------------------
        auto_search_ran = False
        if not no_auto and not context_blocks:
            from engine.tools.auto_search import AutoSearchDecider  # noqa: PLC0415
            decider     = AutoSearchDecider()
            search_term = decider.decide(question, server_ask)

            if search_term:
                Display.info(f"[AUTO] Buscando: {search_term!r}")
                try:
                    from engine.tools.crawler import OrnCrawler   # noqa: PLC0415
                    result = OrnCrawler().search(search_term, source="auto")
                    if result.ok:
                        Display.success(
                            f"[AUTO] Contexto: {result.source} — {result.title!r}"
                        )
                        context_blocks.append(result.to_prompt_block())
                    else:
                        Display.warn(
                            f"[AUTO] Busca falhou ({result.error}). "
                            f"Respondendo sem contexto externo."
                        )
                except Exception as _ae:
                    Display.warn(f"[AUTO] Erro no crawler: {_ae}. Continuando sem contexto.")
                auto_search_ran = True
            else:
                Display.info("[AUTO] Respondendo do conhecimento interno.")

        # Monta prompt final: N blocos → [TASK] → question
        if context_blocks:
            full_prompt = "".join(context_blocks) + "\n[TASK]\n" + question
        else:
            full_prompt = question

        Display.separator()

        t0      = time.monotonic()
        resp    = server_ask(full_prompt, max_tokens)
        elapsed = round(time.monotonic() - t0, 3)

        if resp is None:
            Display.warn("Servidor desconectou. Caindo para modo direto...")
            use_server = False   # fallback abaixo
        elif resp.get("error"):
            Display.error(f"Servidor retornou erro: {resp['error']}")
            sys.exit(1)
        else:
            Display.separator()
            if raw:
                print(resp["output"])
            else:
                Display.code_block(resp["output"])
            Display.separator()
            mode_label = "[servidor+auto]" if auto_search_ran else "[servidor]"
            Display.info(f"Tempo: {resp.get('elapsed_s', elapsed)}s  {mode_label}")
            return

    # ---------------------------------------------------------------
    # MODO DIRETO: Executive + Bridge (carrega modelo aqui)
    # Two-pass não roda no modo direto — custo proibitivo no N2808.
    # --search e --file manuais funcionam normalmente.
    # ---------------------------------------------------------------
    if not use_server:
        if context_blocks:
            full_prompt = "".join(context_blocks) + "\n[TASK]\n" + question
        else:
            full_prompt = question

        Display.info("Modo direto — carregando modelo (~80s no N2808)...")
        Display.separator()

        # instrumentacao de telemetria local (minima, fail-safe)
        t_start = time.perf_counter()
        model_load_s = None
        infer_s = None
        total_s = None

        try:
            # tempo de criação (modelo carregado dentro do Executive)
            t_ml0 = time.perf_counter()
            from engine.core.executive import SiCDoxExecutive  # noqa: PLC0415
            ex = SiCDoxExecutive()
            t_ml1 = time.perf_counter()
            model_load_s = round(t_ml1 - t_ml0, 3)

            try:
                t_inf0 = time.perf_counter()
                result = ex.process_goal(
                    intent  = "think",
                    payload = full_prompt,
                    context = {"context_file": None, "max_tokens": max_tokens},
                )
                t_inf1 = time.perf_counter()
                infer_s = round(t_inf1 - t_inf0, 3)
            finally:
                ex.shutdown()

        finally:
            t_end = time.perf_counter()
            total_s = round(t_end - t_start, 3)

        if not result.success:
            for err in result.errors:
                Display.error(err)
            sys.exit(1)

        Display.separator()
        if raw:
            print(result.output)
        else:
            Display.code_block(result.output)
        Display.separator()

        # metadata do resultado pode conter elapsed (mantemos se existir)
        reported_elapsed = result.metadata.get("elapsed_s") if getattr(result, "metadata", None) else None
        Display.info(f"Tempo: {reported_elapsed or infer_s or '?'}s  [direto]")

        # se telemetria ativada -> gravar e registrar em GLOBAL_TELEMETRY
        if telemetry_enabled:
            try:
                # registro leve: cria payload e delega para core (fail-safe)
                from engine.telemetry.core import record_direct_telemetry  # noqa: PLC0415
                payload = {
                    "captured_at_unix": int(time.time()),
                    "mode": "direct",
                    "model_load_s": model_load_s,
                    "infer_s": infer_s,
                    "total_s": total_s,
                    "reported_elapsed": reported_elapsed,
                    "prompt_chars": len(full_prompt) if full_prompt else 0,
                    "max_tokens": max_tokens,
                }
                record_direct_telemetry(payload)
                Display.info(f"Telemetria gravada: telemetry/direct_runtime.jsonl")
            except Exception as _te:
                Display.warn(f"Telemetria falhou: {_te}")

        return


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


@cli.command()
@click.option("--clear", is_flag=True, default=False,
              help="Limpa o blackboard da sessão atual.")
def brain(clear: bool) -> None:
    """[Fase 3] Exibe estado do blackboard e memória de sessão."""
    Display.section("BRAIN", "Estado interno")
    Display.not_implemented("brain")


@cli.command()
@click.argument("target", type=click.Path(exists=True))
@click.option("--rebuild", is_flag=True, default=False)
def graph(target: str, rebuild: bool) -> None:
    """[Fase 2] Grafo de conceitos AST. Ex: orn graph main.py"""
    Display.section("GRAPH", target)
    Display.not_implemented("graph")


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
def server_start(bg: bool) -> None:
    """Inicia o servidor de inferencia."""
    from engine.server.server import ServerCLI   # noqa
    ServerCLI().run(["start"] + (["--bg"] if bg else []))


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