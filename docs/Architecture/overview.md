# ORN — Architecture Overview
**CR:** 2026.02.19 | **AT:** 2026.02.19 | **Status:** MVP em desenvolvimento

---

## O que e o ORN

ORN (olDox222 Reasoning Node) e uma AI CLI especializada em codigo, executada localmente,
sem dependencia de APIs externas. Usa o modelo Qwen2.5-Coder-0.5B-Instruct-Q4_K_M via
llama-cpp-python como motor de inferencia, e uma camada simbolica (grafo, atlas, blackboard)
como memoria de contexto de sessao.

O projeto nasceu do lixao do OIA -- prototipos anteriores catalogados via
`doxoade intelligence` no chief_dossier.json v2026.Chief.v1.

---

## Principios Fundamentais

- Modelo e servico, nao dependencia. Sobe sob demanda, desce por TTL.
- Memoria controlada externamente. KV-cache com sliding window.
- Quantizacao INT4 obrigatoria. Q4_K_M ja resolvido no modelo escolhido.
- Edge/desktop first. Defaults: n_ctx=2048, n_threads=4, n_gpu_layers=0.
- Zero deps externas na UI. doxcolors (ColorManager + colors.conf).

---

## Fluxo Principal

  [Usuario / Terminal]
          |
          v  orn think / audit / fix / gen / brain / graph
  +-------------------+
  |   engine/cli.py   |  Artemis -- roteamento de intencao
  +--------+----------+
           |
           v  process_goal(intent, payload, context)
  +-------------------------------------------+
  |         SiCDoxExecutive (Zeus)            |
  |  _dispatch() -> _run_think / audit / ... |
  +---+----------+----------+----------------+
      |          |          |
      v          v          v
  +--------+ +--------+ +----------+
  |  LLM   | |Blackbrd| |Validator |
  | Bridge | |(Hades) | |(Anubis)  |
  |(Hefesto| +--------+ +----------+
  +---+----+
      |
  +---v------------------------------+
  |   Qwen2.5-Coder Q4_K_M          |
  |   ContextWindow (sliding window) |
  +----------------------------------+

---

## God Map

  executive.py        Zeus            Orquestrador / autoridade central
  llm_bridge.py       Hefesto         Transforma prompt em artefato
  blackboard.py       Hades           Persistencia invisivel da sessao
  logic_filter.py     Anubis          Valida o que passa ou morre
  atlas.py            Thoth           Linguagem e logica do sistema
  concept_mapper.py   Thoth + Atena   AST -> estrutura arquitetural
  graph_inspector.py  Horus           Supervisao e visao do fluxo
  vector_db.py        Osiris          Persistencia do contexto
  reasoning.py        Ma'at + Anubis  Invariantes e validacao
  planner.py          Atena           Estrategia antes do codigo
  colors.py/display   Afrodite+Apolo  Beleza e clareza no terminal
  cli.py              Artemis         Faz uma coisa, faz bem

---

*Proxima leitura recomendada: Architecture/core.md*