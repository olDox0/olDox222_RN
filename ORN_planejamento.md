# ORN — Planejamento do Projeto CLI de IA para Código

> Versão do Dossier: `2026.Chief.v1` | Modelo: `Qwen2.5-Coder-0.5B-Instruct-Q4_K_M`

---

## 1. Visão Geral

O ORN é uma **IA CLI especializada em código**, capaz de analisar, sugerir, depurar e gerar trechos de código usando um modelo GGUF local. O usuário interage via terminal; a IA usa o Qwen como "cérebro" e uma camada simbólica (grafo, atlas, blackboard) como memória de contexto.

---

## 2. Inventário do Lixão (o que temos)

| Origem | Arquivo | Valor | Prioridade de Aproveitamento |
|--------|---------|-------|------------------------------|
| `ia_core/` | `llm_bridge.py` → `SiCDoxBridge` | Interface com llama.cpp/GGUF | ⭐⭐⭐ USAR |
| `ia_core/` | `executive.py` → `SiCDoxExecutive` | Orquestrador de metas | ⭐⭐⭐ USAR |
| `ia_core/` | `blackboard.py` → `DoxoBoard` | Memória de hipóteses e causalidade | ⭐⭐ USAR |
| `ia_core/` | `logic_filter.py` → `SiCDoxValidator` | Validação de output da IA | ⭐⭐ USAR |
| `ia_tools/` | `concept_mapper.py` → `ConceptMapper` | AST → grafo de conceitos | ⭐⭐⭐ USAR |
| `ia_tools/` | `graph_inspector.py` → `GraphInspector` | Visualizar fluxo do grafo | ⭐ USAR |
| `ia_tools/` | `first_contact.py` | Bootstrap / primeiro contato | ⭐⭐ USAR |
| `recycle/sicdox.py` | CLI commands (Click) | Esqueleto CLI já com grupos/comandos | ⭐⭐⭐ BASE DA CLI |
| `recycle/neural/memory.py` | `VectorDB` | Busca por similaridade coseno | ⭐⭐ USAR |
| `recycle/neural/reasoning.py` | `Sherlock` | Raciocínio + análise de falha | ⭐⭐ USAR |
| `recycle/neural/classifier.py` | `IntentionBrain` | Classificador de intenção | ⭐ CONSIDERAR |
| `recycle/thinking/planner.py` | `ExecutivePlanner` | Formulação de estratégia | ⭐⭐ USAR |
| `recycle/thinking/associator.py` | `Associator` | Aprendizado de associações | ⭐ CONSIDERAR |
| `old/doxovis.py` | `Cores` + funções de TUI | Terminal UI colorido | ⭐⭐ USAR |
| `old/interface.py` | `banner`, `menu` | Interface texto existente | ⭐ ADAPTAR |
| `.doxoade/vulcan/` | `v_llm_bridge.pyx`, `v_first_contact.pyx` | Extensões Cython para C | ⭐ FUTURO |
| `cerebro_*.pkl` | Modelos/pesos serializados | Dados de treinamento anteriores | ⭐ AVALIAR |

### O que DESCARTAR (por ora)
- `old/adversario.py` — lógica de sabotagem, fora do escopo
- `recycle/neural/hrl*.py` — HRL complexo demais para MVP
- `recycle/trace_generation.py` — específico demais
- `old/doxolang*.py` — substituído pelo Qwen

---

## 3. Arquitetura do Sistema

```
[Usuário / Terminal]
        │ CLI (Click)
        ▼
  ┌─────────────┐
  │  orn/__main__ │  ← entry point
  └──────┬──────┘
         │
  ┌──────▼──────────────────────────────┐
  │           Executive (Orquestrador)   │
  │  • recebe goal do usuário            │
  │  • consulta Planner                  │
  │  • despacha para LLM Bridge          │
  └──────┬──────────────┬───────────────┘
         │              │
  ┌──────▼──────┐  ┌────▼──────────┐
  │  LLM Bridge │  │  Blackboard   │
  │  (Qwen GGUF)│  │  (hipóteses)  │
  └──────┬──────┘  └───────────────┘
         │
  ┌──────▼──────────────────────────────┐
  │         Validator / Logic Filter     │
  └──────┬──────────────────────────────┘
         │
  ┌──────▼──────────────────────────────┐
  │        Saída no Terminal (TUI)       │
  │  doxovis / rich / colorama           │
  └─────────────────────────────────────┘

Módulos de Suporte:
  ConceptMapper  ← analisa AST do código do usuário
  VectorDB       ← memória semântica de sessão
  Sherlock       ← raciocínio sobre erros/falhas
  GraphInspector ← visualiza o grafo interno
```

---

## 4. Árvore de Diretórios Proposta

```
orn/
│
├── README.md
├── requirements.txt
├── setup.py / pyproject.toml
├── .gitignore
│
├── main.py                        ← entry point direto (dev)
│
├── orn/                           ← pacote principal
│   ├── __init__.py
│   ├── __main__.py                ← `python -m orn`
│   ├── cli.py                     ← comandos Click (de recycle/sicdox.py)
│   │
│   ├── core/                      ← lógica central (de ia_core/)
│   │   ├── __init__.py
│   │   ├── executive.py           ← SiCDoxExecutive (adaptado)
│   │   ├── llm_bridge.py          ← SiCDoxBridge (adaptado)
│   │   ├── blackboard.py          ← DoxoBoard
│   │   ├── logic_filter.py        ← SiCDoxValidator
│   │   └── atlas.py               ← carrega/gera doxoade_atlas.json
│   │
│   ├── tools/                     ← ferramentas de análise (de ia_tools/)
│   │   ├── __init__.py
│   │   ├── concept_mapper.py      ← ConceptMapper (AST)
│   │   ├── graph_inspector.py     ← GraphInspector
│   │   └── first_contact.py       ← bootstrap
│   │
│   ├── memory/                    ← camada de memória (de recycle/neural/)
│   │   ├── __init__.py
│   │   ├── vector_db.py           ← VectorDB (busca coseno)
│   │   ├── reasoning.py           ← Sherlock
│   │   └── associator.py          ← Associator
│   │
│   ├── thinking/                  ← planejamento e intenção
│   │   ├── __init__.py
│   │   ├── planner.py             ← ExecutivePlanner
│   │   └── classifier.py          ← IntentionBrain
│   │
│   └── ui/                        ← interface no terminal
│       ├── __init__.py
│       ├── colors.py              ← de old/doxovis.py (Cores)
│       └── display.py             ← banner, tabelas, output formatado
│
├── models/                        ← modelos GGUF (não commitados no git)
│   └── sicdox/
│       └── Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF/
│           └── qwen2.5-coder-0.5b-instruct-q4_k_m.gguf
│
├── data/                          ← dados persistentes
│   ├── seed_graph.json            ← de ia_tools/seed_graph.json
│   ├── doxoade_atlas.json         ← atlas funcional
│   └── session/                   ← sessões salvas (gerado em runtime)
│
├── docs/                          ← documentação
│   ├── OIA_CORE_ARCHITECTURE.md
│   ├── Internals/
│   └── vol19_hybrid_intelligence.md
│
├── tests/                         ← testes
│   ├── __init__.py
│   ├── test_bridge.py
│   ├── test_validator.py
│   ├── test_concept_mapper.py
│   └── lab/                       ← de recycle/sicdox_lab/
│       ├── run_fixer_test.py
│       └── referencia_estavel.py
│
└── lixao/                         ← arquivo do lixão (read-only, referência)
    ├── old/
    ├── recycle/
    └── .doxoade/
```

---

## 5. Comandos CLI Planejados

Baseado em `recycle/sicdox.py` e expandido:

```bash
orn think  "<pergunta>"         # Pergunta livre ao Qwen (chat mode)
orn audit  <arquivo.py>         # Analisa AST + aponta problemas
orn fix    <arquivo.py>         # Sugere correções para o arquivo
orn gen    "<descrição>"        # Gera código a partir de descrição
orn brain                       # Exibe estado do blackboard/memória
orn graph  <arquivo.py>         # Exibe grafo de conceitos do código
orn config                      # Configura modelo, parâmetros, etc.
```

---

## 6. Roadmap de Implementação

### Fase 1 — MVP Funcional (Semana 1-2)
- [ ] Criar estrutura de diretórios
- [ ] Migrar `llm_bridge.py` → `orn/core/llm_bridge.py` (limpar, testar conexão com Qwen)
- [ ] Migrar `cli.py` de `recycle/sicdox.py`
- [ ] Implementar `orn think` funcionando end-to-end
- [ ] Migrar `doxovis.py` → `orn/ui/colors.py`

### Fase 2 — Análise de Código (Semana 3)
- [ ] Migrar `concept_mapper.py` para `orn/tools/`
- [ ] Implementar `orn audit` (AST → relatório)
- [ ] Conectar `SiCDoxValidator` no pipeline de output
- [ ] Implementar `orn graph` com visualização no terminal

### Fase 3 — Memória e Contexto (Semana 4)
- [ ] Migrar `VectorDB` → `orn/memory/`
- [ ] Integrar `DoxoBoard` (blackboard) no Executive
- [ ] Implementar persistência de sessão em `data/session/`
- [ ] `orn brain` — exibir estado da memória

### Fase 4 — Geração e Fix (Semana 5)
- [ ] Implementar `orn gen` com prompt estruturado
- [ ] Implementar `orn fix` (audit + sugestão de patch)
- [ ] Recuperar `generate_plan` da archaeology layer do `llm_bridge.py`
- [ ] Integrar `Sherlock` para análise de erros

### Fase 5 — Extensões C (Futuro)
- [ ] Avaliar `.doxoade/vulcan/` (Cython bridges)
- [ ] Integrar extensões C para performance crítica

---

## 7. Dependências

```
# requirements.txt (base)
llama-cpp-python       # interface com GGUF
click                  # CLI
rich                   # TUI / display bonito
colorama               # cores portáteis (fallback)
numpy                  # VectorDB coseno
```

---

## 8. Decisões de Design

**Por que não tocar no lixão diretamente?**
O lixão é a referência arqueológica. Todo código migrado passa por uma revisão antes de entrar em `orn/`. Isso evita trazer bugs e lógica obsoleta junto com o código útil.

**Por que `orn/core/` separado de `orn/tools/`?**
`core/` é o que roda sempre (executive, bridge, validator). `tools/` são capacidades opcionais que podem ser desabilitadas. Fica mais fácil testar e substituir.

**Por que manter `lixao/` no repo?**
As archaeology layers nos arquivos mostram que lógica importante foi perdida antes. Manter o lixão garante que o `generate_plan`, `ponder`, `map_file` etc. estejam acessíveis para recuperação.

---

## 9. Notas sobre o Modelo

- `Qwen2.5-Coder-0.5B-Instruct-Q4_K_M` — 397MB, rápido, bom para completions de código curtas
- Inferência via `llama-cpp-python` (já é o padrão em `llm_bridge.py`)
- Context window: 4096 tokens (verificar no README do modelo)
- Para `orn audit` e `orn fix`, o código do usuário deve ser truncado/sumarizado antes de entrar no prompt se for grande

---

*Documento gerado em 2026-02-18 | Base: chief_dossier.json v2026.Chief.v1*
