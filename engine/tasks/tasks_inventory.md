# FASE 0 — Inventário fechado + gap analysis + Blitz v2

## 1. Inventário real (Cap 0.1 + 0.2 → done)

### `engine/tasks/cli.py`

**Comandos existentes (5):**

| Comando | Fluxo | Observação |
|---|---|---|
| `task run <goal>` | `store.new(spec)` → `runner.run(task.id)` **in-process** | Bloqueia, emite via callback `emit(dict)` |
| `task list [--status]` | `store.list(status=)` | Read-only |
| `task show <id> [--code]` | `store.load(id)` | Read-only |
| `task resume <id>` | `store.load` → `runner.run` | Bloqueia |
| `task abort <id>` | `can_transition_status` → `set_status(ABORTED)` | Única mutação de controle |

**Comandos ausentes para a metáfora do carro (§A.2):** `start`, `stop`, `pause`, `status`.

**`TaskStatus` (enum):** `PENDING`, `RUNNING`, `DONE`, `BLOCKED`, `ABORTED` (confirmado por uso; `FAILED` provável).

**Fases (5, série):** `plan → draft → implement → sandbox → present` (docstring de `task_group`).

**`Task` (contrato observável):** `.id`, `.status`, `.current_phase`, `.attempts`, `.created_at`, `.errors`, `.spec`, `.artifact(name)` → `{content, code, lang}`.

**`TaskSpec`:** `goal`, `language`, `max_retries`, `max_tokens`, `timeout_s`.

**`TaskStore`:** `(root=)`, `.new(spec)`, `.load(id)`, `.save(task)`, `.list(status=)`, `DEFAULT_ROOT`.

**`build_default_runner(store, emit=callable)` → runner**, com `runner.run(task_id) -> Task` **síncrono e bloqueante**.

**`_create_event_emitter()` → `emit(ev: dict)`** com chaves:
`event`, `phase`, `attempt`, `task_id`, `code_len`, `attempts`, `reason`, `status`.
Kinds usados: `task_start`, `phase_start`, `phase_done`, `phase_error`, `task_done`.

### `engine/tools/server_client.py`

**Protocolo:** TCP cru, JSON delimitado por `\n`, **request/response único** (não streaming).

**API:** `is_server_online`, `status`, `query`, `ask`, `decide`, `_raw_query`, `_sandbox_call`, `sandbox_run`, `sandbox_shell`, `sandbox_status`. `HOST=127.0.0.1`, `PORT=8371`.

**Padrão de dispatch:** `_sandbox_call` envia `{"sandbox": "<cmd>", ...}` — **dispatch por chave primária**. É exatamente o slot onde `{"task": "<cmd>", ...}` cabe.

### `engine/tasks/__init__.py`

Só docstring. Confirma pipeline `plan → draft → implement → sandbox → present`.

---

## 2. Gap analysis — o que muda no plano

| Aspecto | Hoje | Alvo (§A) | Gap | Cap |
|---|---|---|---|---|
| **Dono do estado** | CLI (in-process) | Server | `TaskFacade` com `mode: local \| server` | 2 |
| **Dono do runner** | CLI | Server | Handler `{"task": ...}` no server | 2 |
| **Evento de tarefa** | `dict` cru | `StreamEvent` estendido | §1.1 fix + adapter `dict → StreamEvent` | 1 |
| **Streaming CLI** | `emit(dict)` em run bloqueante | NDJSON incremental | `task_stream` em `server_client` **ou** reuso de `stream_infer_events` | 2 |
| **Streaming server** | `query` one-shot; `web_proxy.stream_infer_events` existe | Protocolo de task streaming | **Sonda Cap 2.0 obrigatória** (não sei se `stream_infer_events` usa socket separado) | 2 |
| **Comandos** | run/list/show/resume/abort | + start/stop/pause/status | 4 comandos novos | 2 |
| **Persistência** | `TaskStore` por workspace | `server_store` singleton (lock) | Migração + `.bak` | 2 |
| **Contrato `events.py`** | §1.1 confirmado: `to_dict`/`from_raw` **descartam** kinds de task | Cobertura completa | Fix aditivo | 1 |

**Achados extras (registrar, não agir agora):**
- `server_client.ask()` inlina `apply_code_hook` com `ServerBridge`/`DummyValidator` falsos — cheiro arquitetural, fora de escopo.
- `_sandbox_call` default `wait=600s` — tasks longas precisarão de timeout explícito ou streaming.
- `stream_infer_events` existe mas **não é usado** por `server_client` — protocolo de streaming é caixa preta até Cap 2.0.

---

## 3. Blitzplan v2 — correções

### CAP 0 — Fundação (ajustado)

| # | Task | Status |
|---|---|---|
| 0.1 | Inventário `tasks/cli.py` + `__init__.py` | ✅ esta resposta |
| 0.2 | Inventário `server_client.py` | ✅ esta resposta |
| 0.3 | `engine/tasks/err_table.py` stub | **rascunho §4.1 abaixo** |
| 0.4 | `engine/tasks/diagnostics.py` stub com `--test` | **rascunho §4.2 abaixo** |
| 0.5 | `docs/Research/tasks_inventory.md` + gap table | **rascunho §4.3 abaixo** |
| 0.6 | Test `TASK_E06` (regression guard §1.1) | especificado §4.1 |
| **0.7 (novo)** | Sonda `web_proxy.stream_infer_events`: framing, host/port, se suporta NDJSON contínuo | bloqueia Cap 2 — **preciso do arquivo** |
| **0.8 (novo)** | Decidir `task_stream` — reusar `stream_infer_events` (A) / novo socket (B) / polling (C) | depende de 0.7 |

### CAP 1 — Contrato de eventos (ajustado)

Fix real de §1.1: `to_dict`/`from_raw` ganham branches para os 7 kinds. Adapter `dict → StreamEvent` em `tasks/events_adapter.py` para o emitter atual aceitar ambos durante migração. Teste `TASK_E06` fecha `xfail`.

### CAP 2 — Server dono (ajustado — **maior mudança**)

- **2.0** Sonda `stream_infer_events` (fecha 0.7/0.8).
- **2.1** `server_store.py` com **lock de arquivo** (não havia no plano original — CLI hoje cria `TaskStore` a cada comando, sem contenção; server singleton precisa).
- **2.2** Handler no server: dispatch `{"task": "run|status|stop|pause|list|show", ...}` seguindo padrão de `{"sandbox": ...}`.
- **2.3** `TaskFacade` com `mode: "local" | "server"`; **`local` = comportamento atual bit-a-bit** (regressão zero).
- **2.4** `server_client.task_send/task_stream` (aditivo; não tocar `query`/`ask`).
- **2.5** Comandos CLI: `start` (= `run --server`), `stop` (→ `abort` via facade), `pause` (→ novo estado? **decisão pendente** — `TaskStatus` atual não tem `PAUSED`), `status` (poll live).
- **2.6** `--dry-run` default em `start`; `--apply` para efetivar.

**Decisão pendente nova (§A.3b):** `pause` exige `TaskStatus.PAUSED`? Se sim, é mudança no enum + `can_transition_status` — **Cap 1.5** absorve. Se não, `pause` = `abort` com `resume` posterior (semântica diferente). Recomendo **adicionar `PAUSED`** (a metáfora do carro exige).

### CAP 3 — Web (ajustado)

Sem mudanças estruturais. UI ganha renderização de `phase`, `attempt`, `code_len` (o emitter atual já expõe estes campos — só não são usados no web ainda).

### CAP 4 — Hardening

Sem mudanças. Adicionar regressão "modo `local` idêntico ao pré-migração".

---

## 4. Rascunho dos artefatos Cap 0.3–0.5 (texto, para aprovação **antes** de virar arquivo)

### 4.1 `engine/tasks/err_table.py` — rascunho

```
# doxoade/engine/tasks/err_table.py
"""
Tabela de erros previstos do sistema de tarefas (ProDeNov 5.4 / TYPHON).
Cada entrada responde W5: onde, quando, o quê, quem, por quê, origem, consequência.
Fonte única de verdade para fallbacks e para a sonda TASK_E06.
"""

ERROS = {
  "TASK_E01": {  # server offline
    "onde": "tasks/facade.py",
    "quando": "start/resume sem server online e sem --local/--ephemeral",
    "o_que": "conexão recusada em 127.0.0.1:8371",
    "quem": "operador",
    "porque": "servidor não iniciado",
    "origem": "is_server_online() == False",
    "consequencia": "bloqueia execução server-side",
    "fallback": "exigir --local ou --ephemeral explícito (sem fallback silencioso)",
  },
  "TASK_E02": { ... kind desconhecido em events_adapter ... },
  "TASK_E03": { ... web stream quebrado → polling ... },
  "TASK_E04": { ... JSON corrompido em server_store → .bak + recria ... },
  "TASK_E05": { ... transição inválida → task reset <id> ... },
  "TASK_E06": {
    "onde": "engine/api/events.py",
    "o_que": "to_ndjson/parse_ndjson_line não faz round-trip de kinds de tarefa",
    "origem": "EventKind declara 7 kinds sem branch em to_dict/from_raw",
    "consequencia": "StreamEvent de tarefa é descartado silenciosamente",
    "fallback": "erro no boot se ORN_DEBUG=1",
  },
  "TASK_W01": { ... web sem auth (aceito v1) ... },
}
```

### 4.2 `engine/tasks/diagnostics.py` — rascunho

```
# doxoade/engine/tasks/diagnostics.py
"""
Sondas de saúde do sistema de tarefas (ProDeNov 3.1.6 / 3.1.8).
--test: roda checks in-file (3.1.9).
"""
def check_health() -> dict:
    # {"cli": bool, "server": bool, "store_writable": bool,
    #  "events_contract": bool, "tasks_module": bool}

def probe_task(task_id: str) -> dict:
    # estado, fase, última transição, tempo (delega a TaskStore)

def probe_server() -> dict:
    # is_server_online, status(), latência

def _run_tests() -> int:  # __main__ --test
    # 4 checks mínimos de Cap 0
```

### 4.3 `docs/Research/tasks_inventory.md` — rascunho

Conteúdo = §1 + §2 desta resposta, datado, com seção "Pendências: Cap 0.7 (`stream_infer_events`), Cap 1.5 (`TaskStatus.PAUSED`), Cap 2.0 (framing do streaming)".

---

## 5. Decisões que preciso fechar **agora**

1. **`pause` → `TaskStatus.PAUSED`?** (adiciona enum + `can_transition_status` em Cap 1.5). Recomendo **sim**.
2. **Aprovar §4.1–4.3 como estão** para eu escrever os arquivos e commitar `blitz: fase 0 inventário`.
3. **`engine/web/web_proxy.py`** — pode enviar? Sem ele, **Cap 0.7 fica `xfail`** e Cap 2 começa no Plano B (polling 1s).

Se aprovar 1+2 e enviar `web_proxy.py`, eu:
- escrevo `err_table.py` + `diagnostics.py` + `tasks_inventory.md`;
- rodo `python -m engine.tasks.diagnostics --test` e `python -m engine.tasks.err_table`;
- fecho Cap 0 e abro Cap 1.1–1.4 (fix de `events.py` + 14 testes + `TASK_E06` verde).
