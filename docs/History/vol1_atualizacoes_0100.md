# ORN — Historia e Atualizacoes v0.1.0
**Volume:** 1 | **Periodo:** 2026.02.19 | **Versao:** 0.1.0-skeleton

---

## Contexto Inicial

O ORN nasceu de uma decisao arquitetural clara: o lixao do OIA (Orquestra de
Inteligencia Artificial) continha material valioso disperso em prototipos
experimentais. Em vez de descartar, catalogamos com `doxoade intelligence`
e planejamos a migracao cirurgica.

chief_dossier.json v2026.Chief.v1:
  Total de arquivos mapeados: 124
  Distribuicao por deus:
    Dionisio:  66 (prototipagem / pesquisa)
    Unknown:   23 (arquivos sem atribuicao)
    Hades:     11 (persistencia / storage)
    Anubis:    10 (validacao)
    Poseidon:   5 (fluxos / analise forense)
    Zeus:       6 (orquestracao)
    Atena:      3 (arquitetura)

---

## 2026.02.19 -- Sessao de Fundacao

### [PLAN] Planejamento e Arvore de Diretorios
  - Analise do chief_dossier.json
  - Definicao da arquitetura em 5 camadas:
      core/ tools/ memory/ thinking/ ui/
  - Inventario do lixao com prioridades de aproveitamento
  - Roadmap em 5 fases definido
  - Archaeology layers documentadas (3 funcoes perdidas identificadas)

Funcoes a recuperar das archaeology layers:
  generate_plan()  -- llm_bridge.py  (2026-02-01, layer 1) -- Fase 4
  ponder()         -- planner.py     (2025-12-27, layer 2) -- Fase 4
  map_file()       -- concept_mapper (2026-01-26, layer 2) -- Fase 2
  visit_node()     -- concept_mapper (2026-01-26, layer 2) -- Fase 2

### [ARCH] Arquivo de Arquitetura doxoade mk -a
  - orn_architecture.txt criado no formato tab do doxoade mk
  - Todos os arquivos com comentarios OSL e God embutidos
  - doxoade mk -a orn_architecture.txt executado com sucesso (50+ arquivos)
  - doxoade mk -t confirmou topologia correta

### [SKEL] Esqueleto de Infraestrutura
  - 27 arquivos Python criados -- 0 erros de sintaxe
  - pyproject.toml configurado com doxoade.check e pytest
  - Todos os __init__.py com headers de responsabilidade
  - Stubs com TODO FaseX e archaeology notes preservadas

### [MVP] Pipeline think Fase 1 -- ATIVO
  Arquivos implementados com logica real:
    engine/core/executive.py     -- dispatcher + _run_think() completo
    engine/core/llm_bridge.py    -- Llama() ativo, ContextWindow sliding window
    engine/core/blackboard.py    -- DoxoBoard completo (post_hypothesis, etc)
    engine/core/logic_filter.py  -- SiCDoxValidator completo (_validar_python)
    engine/ui/colors.py          -- ColorManager (doxcolors) integrado
    engine/ui/display.py         -- Display completo, 12 metodos
    engine/cli.py                -- think e config ATIVOS; resto stub fase 2+

  Testes passando (sem modelo):
    9/9 validacoes de integracao
    6/6 testes do validator
    3/3 testes de contrato do bridge

### [FIX] Correcoes de Infraestrutura
  - pyproject.toml: backend corrigido de setuptools.backends.legacy
    para setuptools.build_meta (fix do pip install -e . no Python 3.12)
  - colorama removido: substituido por doxcolors (ColorManager + colors.conf)
  - colors.conf criado: 20 entradas ANSI para ORN
  - requirements.txt: llama-cpp-python documentado para instalacao manual
    via wheel pre-compilada (sem compilador C++ no Windows)
  - rich removido: Display nativo cobre todas as necessidades

### [MEM] Politica de Memoria (Relatorio de Prototipo)
  Decisoes incorporadas na arquitetura:
  - n_ctx=2048 (metade do maximo -- conservador)
  - active_window=1024 (sliding window ativa)
  - n_gpu_layers=0 (CPU-only -- edge/desktop safe)
  - ttl_seconds=300 (modelo desce apos 5min inatividade)
  - max_chars=3000 (limite de contexto de arquivo)
  - ContextWindow preservada apos shutdown (sessao retomavel)

---

## Estado Atual (v0.1.0)

  FASE 1 -- think:    ATIVO (aguardando llama-cpp-python no ambiente)
  FASE 2 -- audit:    planejado (ConceptMapper + GraphInspector)
  FASE 2 -- graph:    planejado
  FASE 3 -- brain:    planejado (VectorDB + Sherlock)
  FASE 4 -- fix:      planejado
  FASE 4 -- gen:      planejado

Para ativar o MVP:
  python -c "import llama_cpp; print(llama_cpp.__version__)"
  Se nao instalado:
    pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
  pip install -e .
  orn config --show
  orn think "explique KV-cache em 3 linhas"

---

*Proximo volume: vol2_atualizacoes_0200.md (Fase 2: audit + graph)*