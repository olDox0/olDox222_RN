# ORN — Plugin API Specification
**CR:** 2026.02.19 | **AT:** 2026.02.19 | **Status:** Planejado (Fase 5+)

---

## Visao Geral

O sistema de plugins do ORN permite adicionar novos comandos CLI e
ferramentas de analise sem modificar o engine/ central. Baseado no
modelo de extensao do doxoade (Click groups + entry points).

Status atual: PLANEJADO. Nao implementado em v0.1.0.

---

## Estrutura de um Plugin

  meu_plugin/
      __init__.py
      plugin.py         <- ponto de entrada Click
      tools/            <- ferramentas especificas
      colors.conf       <- paleta opcional (extends ORN colors.conf)

  plugin.py:
    import click
    from engine.ui.display import Display

    @click.group()
    def plugin_group():
        pass

    @plugin_group.command()
    @click.argument("target")
    def minha_ferramenta(target):
        Display.section("MEU PLUGIN", target)
        # logica aqui

---

## Registro via pyproject.toml

  [project.entry-points."orn.plugins"]
  meu_plugin = "meu_plugin.plugin:plugin_group"

  Carregamento automatico pelo cli.py:
    for ep in importlib.metadata.entry_points(group="orn.plugins"):
        cli.add_command(ep.load(), name=ep.name)

---

## Contratos que Plugins Devem Respeitar

  OSL-16: Nao mais de 500 linhas por arquivo Python
  OSL-17: Plugins nao acessam _llm ou _ctx diretamente
  OSL-18: Dependencias externas minimas e documentadas
  OSL-19: Tests em tests/plugins/ com quarentena separada

  Acesso ao Executive:
    Plugins recebem GoalResult via process_goal() -- nunca instanciam
    SiCDoxBridge diretamente.

---

## Extensoes Vulcan (Cython) -- Fase 5

  .doxoade/vulcan/bin/ ja contem:
    v_first_contact.pyd
    v_first_contact_ccc58c.pyd
    v_llm_bridge_2e5b19.pyd

  Estes .pyd sao extensoes Cython pre-compiladas do lixao.
  Na Fase 5, serao avaliadas para substituir hot-paths do bridge
  (estimativa de tokens, pre-processamento de prompt).

  Build: doxoade vulcan ignite