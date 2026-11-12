# ORN — Roadmap
**CR:** 2026.02.19 | **AT:** 2026.02.19 | **Versao:** 0.1.0

---

## Status Geral

  Fase 1 -- think       [============================] INFRAESTRUTURA 100%
                         aguardando: llama-cpp-python no ambiente
  Fase 2 -- audit/graph [--------------------] PLANEJADO
  Fase 3 -- brain       [--------------------] PLANEJADO
  Fase 4 -- fix/gen     [--------------------] PLANEJADO
  Fase 5 -- Vulcan/API  [--------------------] FUTURO

---

## Fase 1 -- MVP: orn think

  Objetivo: primeiro orn think funcionando end-to-end.
  Entrada:  orn think "pergunta" [--file contexto.py]
  Saida:    resposta do Qwen no terminal com formatacao ORN

  Completo:
    [x] Esqueleto de infraestrutura (27 arquivos, 0 erros)
    [x] SiCDoxExecutive + _run_think() pipeline completo
    [x] SiCDoxBridge + ContextWindow sliding window
    [x] DoxoBoard (blackboard de hipoteses)
    [x] SiCDoxValidator (validacao de output)
    [x] Display + ColorManager (doxcolors, zero deps)
    [x] orn config --show (verificacao de ambiente)
    [x] 9/9 testes de integracao sem modelo
    [x] Documentacao completa (docs/)

  Pendente:
    [ ] Confirmar llama-cpp-python instalado
    [ ] pip install -e .
    [ ] orn think "teste" -- PRIMEIRO REAL
    [ ] doxoade canonize "Fase 1 MVP"

  Criterio de conclusao:
    orn think "o que e KV-cache?" retorna resposta coerente
    elapsed_s registrado em metadata
    Nenhum traceback nao tratado

---

## Fase 2 -- orn audit + orn graph

  Objetivo: ORN consegue analisar seu proprio codigo.
  Entrada:  orn audit engine/core/llm_bridge.py
  Saida:    relatorio de problemas encontrados pelo Qwen

  Escopo:
    ConceptMapper.internalizar() -- AST -> grafo de conceitos
    Recuperar map_file() e visit_node() da archaeology layer
    GraphInspector.show() -- grafo ASCII no terminal
    Executive._run_audit() -- prompt estruturado com grafo
    Executive._run_graph() -- visualizacao do grafo
    Estimativa de tokens -> tokenizer real (llm.tokenize())
    Migrar seed_graph.json do lixao para data/

  Criterio de conclusao:
    orn audit engine/core/executive.py retorna analise coerente
    orn graph engine/core/llm_bridge.py exibe grafo no terminal
    doxoade canonize "Fase 2"

---

## Fase 3 -- orn brain

  Objetivo: memoria de sessao funcional.
  Entrada:  orn brain
  Saida:    estado do blackboard + estatisticas da memoria

  Escopo:
    VectorDB.add() e search() com coseno (numpy)
    Sherlock.analisar_falha() -- raciocinio forense
    Sherlock.verificar_coerencia()
    ExecutivePlanner.formulate_strategy()
    Recuperar ponder() da archaeology layer
    Persistencia de sessao em data/session/
    IntentionBrain.classify() com VectorDB (substituir keywords)

  Criterio de conclusao:
    orn brain exibe hipoteses da sessao e stats de memoria
    orn brain --clear limpa blackboard
    Sessao retomavel apos shutdown do modelo

---

## Fase 4 -- orn fix + orn gen

  Objetivo: ORN gera e corrige codigo.
  Entrada:  orn fix buggy.py / orn gen "funcao de busca binaria em C"
  Saida:    patch sugerido ou codigo gerado + validacao sintatica

  Escopo:
    Recuperar generate_plan() da archaeology layer
    SiCDoxBridge.generate_plan(user_intent, context_graph_snippet)
    Executive._run_fix() -- audit + diff + backup + optional --apply
    Executive._run_gen() -- generate_plan + LLM + Validator
    Validator expandido: C, C++, batch (alem de Python)
    orn gen --out salva em arquivo
    orn fix --apply com backup automatico

  Criterio de conclusao:
    orn fix engine/core/logic_filter.py sugere melhoria valida
    orn gen "funcao quicksort em C" gera codigo C compilavel
    orn fix --apply faz backup e aplica patch sem crashar

---



## Fase 6 -- Estabilização e Dívida Técnica

  Objetivo: consolidar F1-F5, zerar dívida acumulada.

  Escopo (ver `docs/planning/vol6_plan.md`):

    [ ] F6.1  Refactor `_run_fix` (147 linhas → 3 funções < 60)
    [ ] F6.2  Telemetria Windows (`rss_mb`, `lib_bin`)
    [ ] F6.3  `__pycache__` volta em `doxoade save --apply`
    [ ] F6.4  MA'AT falsos positivos (kwonlyargs com default)
    [ ] F6.5  `orn grep` sem cache em `build_dir`
    [ ] F6.6  F5.10 preventivo (escopo em `_parse_ast_replacements`)
    [ ] F6.7  Consult/RAG (T6) — depende de `doxoade consult index`
    [ ] F6.8  `__main__.py` bootstrap dedup (3 arquivos x 200 linhas)

  Critério de conclusão:
    `doxoade check engine/` sem erros
    `orn fix` regressão limpa nos 8 cenários de F5
    `orn-server status` mostra rss_mb > 0
    `doxoade save --apply` não adiciona .pyc
## Fase 5 -- Fix Cirúrgico (--symbol/--symbol-auto) [COMPLETO 2026-11-12]

  Objetivo: performance e extensibilidade.

  Escopo:
    Avaliar .doxoade/vulcan/bin/ (.pyd ja compilados)
    Benchmark Python puro vs Cython nos hot-paths
    Implementar Plugin API via entry points
    doxoade vulcan ignite no engine/ do ORN

  Criterio de conclusao:
    ColorManager 4x mais rapido (como observado no benchmark)
    Plugin de exemplo funcional

---

## Linha do Tempo Estimada

  Fase 1 ATIVO:   2026.02 -- semana 1-2
  Fase 2:         2026.02 -- semana 2-3
  Fase 3:         2026.02 -- semana 4-5
  Fase 4:         2026.03 -- semana 5-6
  Fase 5:         2026.03 -- semana 7+

---

## Principios que Guiam o Roadmap

  Planejamento antes de codigo (Atena)
  Base solida antes de features (OSL-17)
  Modelo e servico, nao dependencia
  Memoria controlada, nunca infinita
  Zero deps externas onde possivel (OSL-18)
  doxoade canonize a cada fase concluida (OSL-20.1)
  Conhecimento não mora no modelo, mora na base (RAG > fine-tuning)
  Consult é a fonte de verdade para Python

| **T6** | Consult Integration — RAG | ⏳ Aguardando |
| **T7** | Consult Dataset Extraction | ⏳ Planejado |
| **T8** | Distilação Qwen→SmolLM | ⏳ Futuro |

