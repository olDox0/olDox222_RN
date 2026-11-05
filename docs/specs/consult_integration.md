# ORN — Consult Integration Spec

**CR:** 2026-10-31 | **AT:** 2026-10-31 | **Versão:** 0.1.0-draft
**Gods:** Hermes (bridge) · Thoth (conhecimento) · Hades (leitura) · Zeus (CLI)
**Fases:** T6 (RAG) → T7 (Dataset Extraction) → T8 (Distilação)
**Status:** 📋 Aguardando implementação T6

---

## 1. Contexto e Motivação

O subsistema **Consult** do Doxoade já indexa um corpus curado de Python
(~2.500 documentos, ~30-100 MB de texto puro) no banco FTS5
`~/.doxoade/consult_docs_fts5.db`.

O ORN, ao rodar o **Qwen2.5-Coder-0.5B** local, responde da memória
paramétrica do modelo — que é **dezenas de vezes menor** que o acervo
Consult. Isso causa:

- Alucinação em APIs específicas (`asyncio.create_task`, `functools.lru_cache`)
- Falta de exemplos canônicos de algoritmos
- Ausência de "conhecimento" sobre PEPs e padrões arquiteturais

**Insight central:** em vez de tentar fazer o modelo "saber tudo" via
fine-tuning (que já provou ser inviável com 135M — vide T4), podemos
**injetar** o conhecimento do Consult no prompt em tempo de inferência
(RAG). O modelo não precisa saber — precisa **ler e sintetizar**.

---

## 2. W5H (ProDeNov §1.1)

| Pergunta | Definição |
| :--- | :--- |
| **O quê?** | Integração do acervo Consult ao ORN via RAG, enriquecendo `orn think` e `orn diff` com contexto curado do banco FTS5 do Doxoade. |
| **Onde?** | `engine/tools/consult_bridge.py` (novo); patches em `engine/cli.py` e `engine/tools/diff_engine.py`. |
| **Quem?** | **Hermes** (bridge de leitura) + **Thoth** (conhecimento) + **Hades** (SQLite FTS5). |
| **Quando?** | T6: RAG end-to-end (~1 sessão). T7: dataset extraction (~1 sessão). T8: distilação (futuro). |
| **Por quê?** | Sem RAG, o Qwen 0.5B alucina em APIs específicas. Com RAG, responde ancorado em docs reais — custo zero de treino, ganho imediato de qualidade. |
| **Consequências?** | O ORN passa a ter "conhecimento" do Python inteiro sem fine-tuning. T7 usa o mesmo acervo para gerar dataset de treino. T8 usa o dataset para distilar o SmolLM 135M. |

---

## 3. Decisões de Design Travadas

| ID | Decisão | Justificativa |
| :--- | :--- | :--- |
| **D1** | Modelo alvo de distilação: **SmolLM 135M** | Ultra-portátil (Q4_K_M ≈ 100 MB), cabe no N2808. |
| **D2** | Dataset: **explicar + gerar código** | Corpus Consult cobre ambos naturalmente. |
| **D3** | Estratégia de perguntas: **heurística + LLM** | Heurística para código, LLM para explicações. |
| **D4** | Escopo: **T6 (RAG) → T7 (Dataset)** | Validar tese antes de expandir. |

---

## 4. Arquitetura (T6)

```
┌─────────────────────────────────────────────────────────────┐
│  orn think/ask/diff "...", "--consult"                       │
│       │                                                      │
│       ▼                                                      │
│  ┌──────────────────────┐                                    │
│  │ ConsultBridge.search │ ──► SQLite FTS5 (~/.doxoade/...)   │
│  │  sanitize → MATCH    │                                    │
│  └──────────┬───────────┘                                    │
│             │                                                │
│             ▼                                                │
│  ┌──────────────────────┐                                    │
│  │ format_context       │ ──► [CONSULT-BEGIN]...[END]         │
│  │  (truncation ≤ 2000) │                                    │
│  └──────────┬───────────┘                                    │
│             │                                                │
│             ▼                                                │
│  ┌──────────────────────┐                                    │
│  │ Prompt + Contexto    │ ──► Qwen 0.5B                      │
│  └──────────────────────┘                                    │
└─────────────────────────────────────────────────────────────┘
```

**Princípios:**
- **Graceful degradation** — DB ausente = RAG desativado silenciosamente
- **Sanitização FTS5** — protege contra `MATCH` errors (operadores, símbolos)
- **Truncation agressiva** — snippets ≤500 chars, total ≤2000 chars
- **Query-only connection** — `PRAGMA query_only = 1` (nunca escreve)
- **Timeout curto** — 2s de conexão, fallback imediato

---

## 5. Contratos

### 5.1 ConsultBridge

```python
class ConsultBridge:
    def __init__(self, db_path: Path | str | None = None) -> None: ...
    def is_available(self) -> bool: ...
    def search(query: str, limit: int = 5,
               category: str | None = None) -> list[ConsultResult]: ...
    def list_categories(self) -> dict[str, int]: ...
    def stats(self) -> dict: ...

    @staticmethod
    def format_context(results: list[ConsultResult],
                       max_chars: int = 2000) -> str: ...
```

**Garantias:**
- `search()` **nunca levanta exceção** — retorna `[]` em erro (OSL-15)
- `is_available()` é O(1) — apenas `stat()` no arquivo
- `format_context()` **sempre retorna string** — vazia se `results=[]`

### 5.2 CLI

| Comando | Função |
| :--- | :--- |
| `orn consult search <query>` | Busca pura FTS5 (sem LLM, instantâneo) |
| `orn consult ask <question>` | RAG: busca + LLM (resposta ancorada) |
| `orn consult list` | Lista categorias + volume |
| `orn consult stats` | Estatísticas do banco |
| `orn think "..." --consult` | `think` com RAG |
| `orn diff ... --consult` | `diff` com contexto enriquecido |

---

## 6. Fase T6 — RAG (Escopo)

### Artefatos

| Arquivo | Ação | Linhas |
| :--- | :--- | :--- |
| `engine/tools/consult_bridge.py` | **Novo** | ~180 |
| `engine/cli.py` | **Patch** (grupo `consult` + `--consult` em `think`/`diff`) | +200 |
| `engine/tools/diff_engine.py` | **Patch** (`context` em `build_prompt`, `consult` em `generate_and_apply`) | +25 |

### Critérios de Aceite (DoD)

- [ ] **CA-1:** `orn consult stats` retorna `total_docs > 0` e `size_mb` > 10
- [ ] **CA-2:** `orn consult search "context manager"` retorna ≥3 resultados em < 100ms
- [ ] **CA-3:** `orn consult ask "como usar dataclasses?"` retorna resposta + `Fontes utilizadas`
- [ ] **CA-4:** `orn think "o que é async/await?" --consult` mostra `[CONSULT] N fonte(s)`
- [ ] **CA-5:** `orn diff ... --consult --raw` gera diff correto com contexto injetado
- [ ] **CA-6:** Se o DB está ausente, `--consult` degrada graciosamente (warning, sem crash)

### Riscos & Mitigação

| Risco | Mitigação |
| :--- | :--- |
| DB corrompido | `is_available()` → `search()` retorna `[]` silenciosamente |
| Query com `AND`/`OR` | Sanitização: extrai tokens alfanuméricos, envolve em aspas |
| Contexto grande estoura prompt | `format_context(max_chars=2000)` trunca |
| DB não existe no N2808 | Copiar `consult_docs_fts5.db` manualmente (~50 MB) |

---

## 7. Fase T7 — Dataset Extraction (Preview)

### Objetivo

Extrair pares `instrução → resposta` do acervo Consult para treinar o
SmolLM 135M (T8).

### Estratégia por categoria

| Categoria | Pergunta | Resposta |
| :--- | :--- | :--- |
| `python_basic/*` | "O que é X?" (do título) | Conteúdo da seção |
| `python_algorithms/*` | "Implemente uma Trie" | Código + docstring |
| `python_peps/*` | "O que diz a PEP 484?" | Conteúdo da PEP |
| `python_snippets/*` | "Como funciona lru_cache?" | Snippet + explicação |
| `cpython_stdlib/*` | "Qual a assinatura de X?" | Assinatura + descrição |
| `python_typeshed/*` | "Qual o type hint de open?" | Stub |

### Pipeline (T7)

```
consult_docs_fts5.db
    ↓
[extractor] — parse title/content, extrai código
    ↓
[qa_generator] — pergunta heurística + LLM expansion
    ↓
data/processed/consult_v1/train.jsonl (ChatML)
    ↓
orn train lora (T4)
```

### Artefatos planejados

- `engine/tools/consult_extractor.py` (~250 linhas)
- `engine/cli.py`: `orn data build --consult` (nova opção)
- `data/processed/consult_v1/` (gerado)

### Critérios de Aceite (T7)

- [ ] Extrai ≥1.000 pares únicos do corpus
- [ ] Filtra duplicatas e código inválido (`ast.parse`)
- [ ] Distribuição balanceada entre categorias
- [ ] `orn train lora` roda com sucesso

---

## 8. Fase T8 — Distilação (Outlook)

**Objetivo:** usar o Qwen 0.5B + RAG como professor para gerar
respostas de alta qualidade, treinar o SmolLM 135M como aluno.

**Fluxo:**
```
pergunta consult → Qwen+RAG → resposta
    ↓
(pergunta, resposta) → dataset de distilação
    ↓
SmolLM 135M LoRA (T4)
    ↓
SmolLM com "conhecimento" do Consult
```

**Ganho esperado:** SmolLM 135M Q4_K_M (~100 MB) responde sobre Python
com qualidade próxima ao Qwen 0.5B + RAG, mas com **1/4 da RAM** e
**2x mais rápido** no N2808.

**Status:** planejado, não escopo de T6/T7.

---

## 9. Tasklist T6

### Fase 1 — Implementação (1 sessão)

- [ ] **T6.1:** Criar `engine/tools/consult_bridge.py` (ConsultBridge + ConsultResult)
- [ ] **T6.2:** Patch `engine/cli.py` — grupo `consult` (search/ask/list/stats)
- [ ] **T6.3:** Patch `engine/cli.py` — flag `--consult` em `think`
- [ ] **T6.4:** Patch `engine/cli.py` — flag `--consult` em `diff_cmd`
- [ ] **T6.5:** Patch `engine/tools/diff_engine.py` — `context` em `build_prompt` + `consult` em `generate_and_apply`

### Fase 2 — Homologação (30 min)

- [ ] **H6.1:** `orn consult stats` → DB encontrado, `total_docs > 0`
- [ ] **H6.2:** `orn consult list` → categorias visíveis
- [ ] **H6.3:** `orn consult search "context manager"` → ≥3 resultados
- [ ] **H6.4:** `orn consult ask "como usar dataclasses?"` → resposta + fontes
- [ ] **H6.5:** `orn think "o que é async/await?" --consult` → `[CONSULT] N fonte(s)`
- [ ] **H6.6:** `orn diff test.py -i "troque + por -" --consult --raw` → diff correto
- [ ] **H6.7:** Renomear `consult_docs_fts5.db` temporariamente → `--consult` degrada sem crash

### Fase 3 — Save

- [ ] **S6.1:** `doxoade save "T6 concluido - RAG Consult integrado ao ORN"`
- [ ] **S6.2:** Atualizar `docs/History/vol3_atualizacoes_0300.md` com resultados

---

## 10. Anexo — Cenário de Sucesso (Referência)

```bash
# Usuário no N2808 (Celeron, 2 GB RAM), servidor ORN ativo

$ orn think "como usar context managers?" --consult

[ORN] Processando: "como usar context managers?"
[CONSULT] 3 fonte(s) injetada(s).
Modo servidor ativo — inferência instantânea...
────────────────────────────────────────────────
Use @contextmanager do contextlib:

    from contextlib import contextmanager

    @contextmanager
    def arquivo(nome):
        f = open(nome)
        try:
            yield f
        finally:
            f.close()

Alternativa com __enter__ e __exit__:
    class MeuContexto:
        def __enter__(self): ...
        def __exit__(self, *args): ...
────────────────────────────────────────────────
Tempo: 2.3s

Fontes utilizadas:
  - python/cheatsheet/context_managers
  - python_basic_py4e/ch11_regex
  - python_basic_byteofpython/io
```

**Diferença para `orn think "..."` sem `--consult`:** a resposta é
**ancorada em documentação real** em vez de alucinada. Custo: +150ms
para a busca FTS5. Ganho: precisão muito maior em APIs específicas.

---

## 11. Referências

- `docs/specs/inference_api.md` — contratos do SiCDoxBridge
- `docs/specs/data_format.md` — formato do doxoade_atlas.json
- `doxoade/commands/consult_systems/doc_indexer.py` — schema do FTS5
- `doxoade/commands/consult_systems/cmd_consult.py` — CLI do Consult
- `docs/Protocols/OSL.md` — regras de qualidade (OSL-15, OSL-18)
- `docs/Protocols/Gods.md` — mapeamento Hermes/Thoth/Hades/Zeus

---

*Spec gerada em 2026-10-31 · Base: brainstorm ORN × Consult (D1-D4)*
