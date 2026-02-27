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

import sys
import click

from engine.ui.display import Display


# ---------------------------------------------------------------------------
# Grupo raiz
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(package_name="orn")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """ORN — AI CLI para código (Qwen2.5-Coder local)."""
    ctx.ensure_object(dict)   # OSL-6: contexto mínimo


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
def think(prompt: tuple[str, ...], context_file: str | None,
          raw: bool, tokens: int | None, direct: bool,
          search: str | None = None) -> None:
    """Pergunta livre ao Qwen. Ex: orn think 'como faço X em Python?'"""
    import time
    full_prompt = " ".join(prompt)

    # --search: busca contexto online e injeta antes do prompt
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
                full_prompt = result.to_prompt_block() + "\n" + full_prompt
            else:
                Display.warn(f"[CRAWLER] {result.error}")
        except Exception as _ce:
            Display.warn(f"[CRAWLER] Erro: {_ce}")

    # Injeta contexto de arquivo se fornecido
    if context_file:
        try:
            ctx_text = open(context_file, encoding="utf-8", errors="replace").read(3000)
            full_prompt = f"[CONTEXTO DO ARQUIVO: {context_file}]\n{ctx_text}\n\n[PERGUNTA]\n{full_prompt}"
        except OSError:
            pass

    max_tokens = tokens or 128

    Display.banner()
    Display.thinking(full_prompt if not context_file else " ".join(prompt))

    # ---------------------------------------------------------------
    # MODO SERVIDOR: detecta e usa SiCDox Server se disponivel
    # ---------------------------------------------------------------
    from engine.tools.server_client import is_server_online, ask as server_ask  # noqa

    use_server = (not direct) and is_server_online()

    if use_server:
        Display.info("Modo servidor ativo — sem espera de load.")
        Display.separator()

        t0 = time.monotonic()
        resp = server_ask(full_prompt, max_tokens)
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
            Display.info(f"Tempo: {resp.get('elapsed_s', elapsed)}s  [servidor]")
            return

    # ---------------------------------------------------------------
    # MODO DIRETO: Executive + Bridge (carrega modelo aqui)
    # ---------------------------------------------------------------
    if not use_server:
        Display.info("Modo direto — carregando modelo (~80s no N2808)...")
        Display.separator()

        from engine.core.executive import SiCDoxExecutive  # noqa: PLC0415
        ex = SiCDoxExecutive()

        try:
            result = ex.process_goal(
                intent  = "think",
                payload = full_prompt,
                context = {"context_file": None, "max_tokens": max_tokens},
            )
        finally:
            ex.shutdown()

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
        Display.info(f"Tempo: {result.metadata.get('elapsed_s', '?')}s  [direto]")


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

    # Persistência de config — TODO Fase 2: salvar em data/orn_config.json
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
    from engine.core.llm_bridge import BridgeConfig       # noqa: PLC0415
    from engine.tools.first_contact import check_environment  # noqa: PLC0415

    cfg = BridgeConfig()

    Display.info("Configuração atual (padrão):")
    Display.kv("model_path",    str(cfg.model_path))
    Display.kv("model_exists",  str(cfg.model_path.exists()))
    Display.kv("n_ctx",         str(cfg.n_ctx))
    Display.kv("active_window", str(cfg.active_window))
    Display.kv("max_tokens",    str(cfg.max_tokens))
    Display.kv("n_threads",     str(cfg.n_threads))
    Display.kv("n_gpu_layers",  str(cfg.n_gpu_layers))
    Display.kv("ttl_seconds",   str(cfg.ttl_seconds))

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