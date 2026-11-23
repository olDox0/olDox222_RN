# BLITZPLAN — Sistema de Tarefas (v1)

> **Blitz Devlopmente** (ProDeNov §conceitos). Plano de execução curto, sequencial, com Plano A/B/C por capítulo, RIT por passo, sonda/diagnóstico obrigatória, regressão em cada parte. Não é arquitetura final — é o roteiro até ela.

---

## §A — Decisões consolidadas

| # | Pergunta | Decisão | Efeito arquitetural |
|---|---|---|---|
| 1 | Ciclo de vida | Vive/survive exit **conforme contexto** | 3 modos: `server` (persistente), `local` (in-process, morre com o CLI), `ephemeral` (descartável) |
| 2 | Dono do estado | **Server** é dono; CLI é **painel de controle** | `TaskStore` mora **no server**; CLI só envia comandos + lê stream |
| 3 | Fases | **Série** por enquanto | `phase` é campo linear; `chunk_idx` basta; hook de paralelismo só na Parte 4 |
| 4 | Web auth | **Não** nesta versão | `TASK_W01 auth pendente` na err_table; web read-only |
| 5 | Contrato de evento | **Estender `StreamEvent`** | Branch aditivo em `to_dict`/`from_raw`; round-trip obrigatório |

**Metáfora operacional (fixa):** CLI = ignição/marcha. Server = motor. Task = viagem registrada no motor. Web = painel de passageiro (leitura).

**Consequência dura:** `engine/tasks/store.py` **não** existe no cliente. Ou está no server (`engine/tasks/server_store.py`), ou o CLI usa `--ephemeral`/`--local` como fallback explícito.

---

## §B — Blitzplan (5 capítulos, ordem de execução)

### CAPÍTULO 0 — Fundação (revisão já feita, agora fechar inventário)

**Objetivo:** transformar o rascunho em inventário executável.

| # | Tasklist | Critério de done |
|---|---|---|
| 0.1 | Ler `engine/tasks/cli.py` + `__init__.py` (reais, não truncados) | Lista de comandos e eventos existentes |
| 0.2 | Ler `engine/tools/server_client.py` (API real de `query`/`status`) | Endpoints disponíveis documentados |
| 0.3 | Escrever `engine/tasks/err_table.py` (só tabela + docstring, sem lógica) | Arquivo compila, `python -m engine.tasks.err_table` imprime tabela |
| 0.4 | Escrever `engine/tasks/diagnostics.py` stub: `check_health() -> dict` retornando `{"cli": bool, "server": bool, "events_contract": bool, "tasks_module": bool}` | `python -m engine.tasks.diagnostics --test` roda 4 checks |
| 0.5 | `docs/Research/tasks_inventory.md` (§7.3) com inventário + 5 decisões §A | Preservação feita |
| 0.6 | **Sonda de contrato** `TASK_E06` (do §C): round-trip `to_ndjson`/`parse_ndjson_line` de cada kind de tarefa — **vai falhar hoje** (é o bug §1.1) | Teste escrito, marcado `xfail` até Cap 1 |

- **Plano A:** todos os arquivos acessíveis → inventário fecha em 1 sessão.
- **Plano B:** `tasks/cli.py` maior que esperado → congelar inventário e só listar comandos (sem detalhar) na v1.
- **Plano C:** `tasks/` não existe de fato (só stub de `task_group`) → Cap 1 começa do zero, sem dívida.

**RIT:** discussão (feita) → ler → escrever err_table + diagnostics stub → rodar `--test` → diff review → commit `blitz: fase 0 inventário`.

**Regressão Cap 0:** `orn task --help`, `orn think`, `orn server status` inalterados.

**Sondas:** `python -m engine.tasks.diagnostics --test`, `python -m engine.tasks.err_table`.

---

### CAPÍTULO 1 — Contrato de Eventos + Modelo (sem rede)

**Objetivo:** consertar §1.1 (bug de `events.py`) **antes** de qualquer integração. Sem isto, Cap 2/3 são castelo de areia.

| # | Tasklist | Done |
|---|---|---|
| 1.1 | Estender `StreamEvent` com `task_id: str = ""`, `phase: str = ""`, `progress: float = 0.0` | Aditivo, retrocompatível |
| 1.2 | `to_dict()` — branches para `task_start / phase_start / phase_done / phase_error / sandbox_start / sandbox_done / task_done` | Cada kind emite só seus campos |
| 1.3 | `from_raw()` — branches equivalentes | Round-trip completo |
| 1.4 | `_run_tests()` de `events.py` ganha 14 testes novos (2 por kind × 7) | Verde |
| 1.5 | Criar `engine/tasks/models.py`: `Task`, `TaskPhase`, `TaskState` (enum `pending/running/paused/done/failed`) | Sem I/O, sem `events` |
| 1.6 | `engine/tasks/events_adapter.py`: `Task ↔ StreamEvent` | Só `api/events` + `models` |
| 1.7 | Ativar `TASK_E06` (remover `xfail` do Cap 0.6) | Verde |

- **Plano A:** estender `StreamEvent` (escolhido — resposta §A.5).
- **Plano B:** se `slots` quebrar algum caller → `@dataclass(slots=False)` só em `StreamEvent`, ou `meta: dict` genérico no lugar dos 3 campos.
- **Plano C:** `TaskEvent` separado + union no `parse_ndjson_line` — **último recurso**, duplica contrato.

**RIT:** testes in-file primeiro (`__main__ --test`), depois sonda de contrato (1.7), depois integração com `cli.py`.

**Regressão Cap 1 (dura):** `python -m engine.api.events --test` (existentes + 14 novos) verde; `orn think "oi"` e `orn think --search ...` produzem stream idêntico ao estado anterior (comparar `to_ndjson` byte-a-byte de um evento `chunk`).

**Sondas:** `python -m engine.api.events --test`, `python -m engine.tasks.events_adapter --test`.

---

### CAPÍTULO 2 — Server dono (TaskStore + TaskRunner + API)

**Objetivo:** o motor. Server passa a ser a **fonte única**.

| # | Tasklist | Done |
|---|---|---|
| 2.1 | `engine/tasks/server_store.py` — persistência JSON em `~/.orn/tasks/` (delegado, §2.1.3.1: **sem sqlite aqui**) | `save/load/list/delete`, backup `.bak` |
| 2.2 | `engine/tasks/runner.py` — `TaskRunner` espelhando `SiCDoxExecutive._dispatch` (route dict `{phase: handler}`, retorna `GoalResult`-like) | Fase desconhecida → erro explícito |
| 2.3 | `engine/tasks/server_bridge.py` — ponte `runner + store → StreamEvent` | Só emite via `events_adapter` |
| 2.4 | `engine/tasks/facade.py` — `TaskFacade` espelhando `InferenceFacade`; modos `server`/`local`/`ephemeral` | `_resolve()`, `_fallback_local()`, `status()` |
| 2.5 | Estender `engine/tools/server_client.py` com `task_send(cmd, **kw)` e `task_stream(task_id)` | Só aditivo |
| 2.6 | CLI: `orn task start|stop|status|list|pause` — **só comandos de controle** | Cada um passa pelo `TaskFacade` |
| 2.7 | `--dry-run` por padrão em `task start` (ProDeNov 5.3); `--apply` para efetivar | UX segura |
| 2.8 | `engine/tasks/err_table.py` preenchida com códigos reais (ver §C) | Imprime no boot se `ORN_DEBUG=1` |

- **Plano A:** stream NDJSON incremental do server.
- **Plano B:** se `server_client` não suportar stream → polling `task_stream` a cada 1s (o contrato de evento não muda).
- **Plano C:** `--local` (in-process runner, sem HTTP) como fallback explícito; `--ephemeral` para testes descartáveis.

**RIT:** `runner` com fase fake (`echo`) verde → `server_bridge` emite `task_start/phase_start/phase_done/task_done` → CLI vê stream → `store` persiste → mata processo → `task status <id>` recupera → `task list` lista.

**Sondas (obrigatórias, 3.1.4/3.1.6):**
- `task probe --server` → imprime `server_online`, `store_path`, `task_count`, `last_event_kind`
- `task probe --task <id>` → estado, última fase, última transição, tempo
- `task doctor` → verifica `~/.orn/tasks/` gravável, JSON íntegro, `events` round-trip

**Regressão Cap 2:** `orn server status`, `orn server ask`, `orn think --direct`, `orn web start` intactos. `task --help` só ganha comandos, não perde.

**Riscos mapeados:**
- `TASK_E01` server offline em `task start` sem `--local`/`--ephemeral` → mensagem clara, **não** fallback silencioso (3.1.6 / 5.2).
- `TASK_E04` JSON corrompido em `~/.orn/tasks/` → backup `.bak` + recria.
- **Memory/processing:** não otimizar agora (decisão §A.3); só medir — `task probe --resources` já imprime `psutil` opcional se disponível, senão `-`.

---

### CAPÍTULO 3 — Web leitor (read-only)

**Objetivo:** painel de passageiro. Zero lógica de negócio nova.

| # | Tasklist | Done |
|---|---|---|
| 3.1 | `engine/web/tasks_proxy.py` — consome NDJSON do server, reemite 1:1 (SSE ou polling) | Só `api/events` + `server_client` |
| 3.2 | Endpoint `/tasks` (lista) e `/tasks/<id>/stream` | Reusa padrão de `web_proxy` |
| 3.3 | UI mínima: lista + fase atual + último evento | Read-only, sem escrita |
| 3.4 | `task probe --web` → `HTTP HEAD /tasks`, latência, contagem | Sonda |
| 3.5 | `TASK_W01 auth pendente` registrado na UI e na err_table | Transparência |

- **Plano A:** SSE reusando `stream_infer_events` (padrão de `web_proxy`).
- **Plano B:** polling 1s (`TASK_E03`).
- **Plano C:** UI só `curl /tasks` (JSON cru) — web "burro" mas honesto.

**RIT:** inicia task no CLI → web mostra `task_start` em ≤2s (A) ou ≤2s após tick (B) → `phase_done` aparece → `task_done` encerra.

**Regressão Cap 3:** `orn web start`/`web stop` intactos; `orn think` stream no web intacto; `iter_events_from_lines` (Cap 1) é o único parser usado — se mudar, muda nos dois lugares.

**Sonda:** `task probe --web --verbose` mostra: conexão, último evento, latência, erros da err_table.

---

### CAPÍTULO 4 — Hardening, Caos, Revisão, Preservação

**Objetivo:** fechar loop ProDeNov (5.6.4 revisão + §7 preservação) e avaliar escalabilidade **depois**.

| # | Tasklist | Done |
|---|---|---|
| 4.1 | Caos/Typhon: simular **cada** `TASK_E*` e confirmar fallback | 6/6 previsíveis, 6/6 com fallback |
| 4.2 | Reversibilidade: `task undo <id>` / backup antes de `apply` | Funciona após matar server no meio |
| 4.3 | `task --dry-run` cobre todos os comandos que mutam | 100% |
| 4.4 | Revisão manutenibilidade: docstrings, `# doxoade/engine/tasks/...` (§2.1.1), glossário interno (§5.6.5) | Passa |
| 4.5 | **Análise memória/processamento** (§A.3): medir 1 task × 100 fases, 10 tasks × 10 fases | Relatório `docs/Research/tasks_resources.md` |
| 4.6 | Hook de escalabilidade: `runner.py` preparado para fase paralela (sem implementar) | Interface `run_phase()` aceita `parallel: bool = False` |
| 4.7 | `docs/Research/tasks_postmortem.md` + `CHANGELOG.md` + `Dirty/` (ProDeNov 6.1.6) | Preservação |

- **Plano A:** tudo verde → v1 estável.
- **Plano B:** isolar falha por modo (server/local/web independentes); não bloquear release por 1 modo.
- **Plano C:** congelar feature, registrar dívida na `err_table`, abrir Cap 5.

**Regressão Cap 4:** suite completa (Cap 0-3) + `orn think`, `orn server`, `orn web`, `orn task --help`, `orn task list`.

**Proibido (§4.2):** sem capacidade de testar com segurança → só planejar, não codar.

---

## §C — Err table atualizada (v1)

| Código | Onde | Sintoma | Fallback | Sonda |
|---|---|---|---|---|
| `TASK_E01` | `facade` | server offline | `--local`/`--ephemeral` **explícito** (nunca silencioso) | `task probe --server` |
| `TASK_E02` | `events_adapter` | kind desconhecido | log + ignora | `task doctor` |
| `TASK_E03` | `web/tasks_proxy` | stream quebrou | polling 1s | `task probe --web` |
| `TASK_E04` | `server_store` | JSON corrompido | `.bak` + recria | `task doctor` |
| `TASK_E05` | `cli` | transição inválida | `task reset <id>` | `task probe --task <id>` |
| `TASK_E06` | `events` | **round-trip quebrado (§1.1)** | erro no boot | `python -m engine.api.events --test` |
| `TASK_W01` | web | auth pendente | read-only | UI warning |

`TASK_E06` é sonda de regressão permanente. Fecha em Cap 1.

---

## §D — Riscos & o que **não** fazer agora

- ❌ Não otimizar memória/processamento (Cap 4.5 mede primeiro).
- ❌ Não paralelizar fases (hook só em Cap 4.6).
- ❌ Não colocar `TaskStore` no cliente (decisão §A.2).
- ❌ Não usar sqlite fora de `task_persistence.py` (ProDeNov 2.1.3.1).
- ❌ Não adicionar comandos de task em `engine/cli.py` (complexidade 361).
- ⚠️ Se `tasks/cli.py` já tiver lógica de negócio além de Click → **migrar para facade** em Cap 2.4, com teste de regressão antes.

---

## §E — Próxima ação imediata

Executar **Cap 0.1 + 0.2**: você me envia

- `engine/tasks/cli.py`
- `engine/tasks/__init__.py`
- `engine/tools/server_client.py` (só o trecho de `query`/`status`/`HOST`/`PORT`)

Com isso eu:
1. Fecho o inventário real (comandos + eventos existentes).
2. Confirmo se §1.1 é dano instalado ou hipótese.
3. Escrevo **Cap 0.3 + 0.4 + 0.6** já no formato ProDeNov (§2.1.1, §2.1.2, `--test` in-file) — `err_table.py` e `diagnostics.py` stub, sem inventar lógica.
4. Commit `blitz: fase 0 inventário` após diff review.

Sem os 3 arquivos, Cap 0 fica em hipótese — e a partir daí o Blitz vira chute (viola ProDeNov 3.1.6).

Envie os 3 e eu abro Cap 0.3–0.6 direto.

---

blitz: fase 0 — inventário, err_table, diagnostics

- engine/tasks/err_table.py: 8 erros previstos (W5)
- engine/tasks/diagnostics.py: sondas + --test (TASK_E06 pré-fix)
- docs/Research/tasks_inventory.md: inventário + gap + Cap 0.7

Achados: TASK_E06 (events.py), TASK_E07 (facade port=).
Próximo: Cap 1 fix events.py + adapter.

---

blitz: fase 1 — eventos de tarefa + PAUSED + facade fix

- events.py: StreamEvent ganha task_id/phase/progress/meta;
  to_dict/from_raw cobrem 7 kinds (fecha TASK_E06)
- model.py: STATUS_TRANSITIONS liga PAUSED (RUNNING↔PAUSED↔ABORTED)
- events_adapter.py: runner emit(dict) → StreamEvent
- facade.py: port= → infer_port= (fecha TASK_E07)
- diagnostics.py: probe_corrupt() (TASK_E04 ativo)

Cap 0.3-0.5 inclusos neste commit (err_table, diagnostics, tasks_inventory.md).
