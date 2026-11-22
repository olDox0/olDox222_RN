Beleza. Decisões travadas. Antes de codar `model.py`/`store.py`, faço o **passo 0** como você pediu: revisão, ajustes no desenho e checklist do que preciso confirmar no código existente — porque DRAFT virar o ponto de retry muda o protocolo e "workspace no sandbox" muda onde os artefatos moram.

---

## 0.1 Protocolo ajustado

Com **retry→DRAFT** e **DRAFT obrigatório**, o grafo fica assim:

```
        ┌──────────────────────────────────────────────────────┐
        │                                                      │
        ▼                                                      │
   ┌────────┐    ┌────────┐    ┌────────────┐    ┌─────────┐    │
   │  PLAN  │───▶│ DRAFT  │───▶│ IMPLEMENT  │───▶│ SANDBOX │────┘ fail (até max_retries)
   └────────┘    └────────┘    └────────────┘    └────┬────┘
                                                       │ ok
                                                       ▼
                                                  ┌─────────┐
                                                  │ PRESENT │──▶ DONE
                                                  └─────────┘
```

- **PLAN** roda **uma vez**. Se sandbox falhar, o plano continua válido.
- **DRAFT** é o ponto de retry. Recebe `feedback` (stderr do sandbox + erro atual) e regenera o código do zero.
- **IMPLEMENT** é polish determinístico-ish: pega o draft, aplica `apply_code_hook`, garante type hints, valida com `SiCDoxValidator`. Se falhar validação, **volta pra DRAFT** também (mesmo contador de retry).
- **SANDBOX**: executa código do IMPLEMENT. `ok → PRESENT`; `fail → DRAFT` com `feedback`.
- **PRESENT** determinístico.

Contador `attempts` incrementa **só** quando volta pra DRAFT. `max_retries=2` significa até 3 passadas pelo DRAFT.

---

## 0.2 "Workspace no sandbox" — interpretação

Como `SandboxController.run(code, args, timeout, lang)` recebe **código como string** (confirmei pelo uso em `cli.py::sandbox_run`), não há filesystem compartilhado. Então:

- Os artefatos ficam em disco em `~/.orn/tasks/<id>/artifacts/` — **mas são read-only do ponto de vista de execução**.
- O `SANDBOX` sempre passa o código **inline** pro `SandboxController`/`QemuDaemon`. Nada é executado a partir da árvore real.
- Não há `workspace/` espelhando o projeto real. Se uma tarefa precisar criar múltiplos arquivos, o MVP trata **um arquivo por tarefa** (o artifact `implement.py` ou `implement.c`). Multi-arquivo fica pra Fase 2.

Isso simplifica o MVP e respeita "no sandbox por segurança". Se você quiser suportar `workspace/` multi-arquivo depois, é só o `sandbox_step` concatenar ou zipar — o `store` já vai estar preparado porque cada artifact tem `path` opcional.

---

## 0.3 Layout de diretórios

```
engine/tasks/
  __init__.py
  model.py            # TaskSpec, TaskArtifact, Task, TaskStatus, Phase
  store.py            # TaskStore (JSON atômico + NDJSON de eventos)
  prompts.py          # build_*_prompt por fase
  runner.py           # TaskRunner (máquina de estados)
  sandbox_step.py     # _phase_sandbox isolado (troca de backend por lang)
```

Persistência (por padrão relativa ao CWD, override por `--tasks-root`):

```
.orn/tasks/
  <task_id>/
    state.json          # snapshot atômico do Task
    events.ndjson       # append-only
    artifacts/
      plan.json         # plano estruturado (passos, arquivos, riscos, sucesso)
      plan.md           # versão humana (gerada no PRESENT)
      draft.py
      implement.py
      sandbox.log
      present.md
```

`task_id` = `YYYYMMDD-HHMMSS-<6hex>` (ordenável e único).

---

## 0.4 Persistência — JSON estruturado no PLAN

Você pediu JSON. Então o PLAN pede ao modelo **JSON** e valida com `json.loads` antes de aceitar:

```json
{
  "understanding": "string",
  "files": [
    {"path": "solver.py", "action": "create|modify", "purpose": "string"}
  ],
  "io_contracts": [
    {"symbol": "solve", "kind": "function",
     "inputs": [{"name": "n", "type": "int"}],
     "outputs": [{"type": "int"}],
     "errors": ["ValueError"]}
  ],
  "risks": ["string"],
  "success_criteria": ["string"]
}
```

Salvo em `artifacts/plan.json`. O `plan.md` é **derivado** no PRESENT (sem nova chamada ao modelo). Se o modelo não devolver JSON válido, o `_phase_plan` tenta 1 vez com "responda APENAS JSON", e se falhar de novo → `TaskStatus.FAILED` (plano inválido não vale a pena continuar).

`draft.py` e `implement.py` continuam texto puro (código), com metadados no `state.json`.

---

## 0.5 O que preciso confirmar no código antes do passo 1

Só coisas que **bloqueiam** o model/store. Vou verificar no código real (não no relatório, que tem trechos truncados):

1. **`SandboxController.run`** — assinatura exata e se aceita `lang="python"` (o `cli.py` mostra `SandboxController().run(code, args=..., timeout=..., lang=...)`, mas quero ver o `__init__` pra saber se precisa configurar workspace).
2. **`QemuDaemon.run`** — idem, e se `d.start(timeout=…)` bloqueia até daemon ficar pronto ou retorna imediato.
3. **`SiCDoxValidator.validar_output`** — retorno `(bool, str)`? Alguma política de quê considera "inválido" pra código?
4. **`apply_code_hook`** — `run_isolated=True` executa o código? Se sim, no IMPLEMENT eu quero `run_isolated=False` pra não duplicar execução (o SANDBOX é a única fase que executa). Preciso confirmar assinatura e comportamento.
5. **`Display`** — métodos exatos (`banner`, `section`, `kv`, `code_block`, `thinking`, `separator`, `success/warn/error/info`). Uso no `--stream` do passo 6.
6. **`SiCDoxBridge.ask`** — aceita `max_tokens=None`? Retorna `str` sempre ou pode levantar? Preciso do contrato pra `_ask` no runner.
7. **`chronos_recorder`** — quero plugar `task run` no `chronos`? Se sim, o runner precisa de hook. MVP: **não**; deixo pra depois.
8. **`pydantic`** está disponível? (vi `dataclass` no `events.py`, `blackboard.py`). Se sim, uso `pydantic.BaseModel` no `model.py` pra serialização JSON grátis. Se não, fico em `dataclass` + `to_dict/from_dict` como no `events.py`.

---

## 0.6 Riscos identificados

- **`engine/cli.py` já tem complexidade 361.** Vou adicionar `task` group no passo 2 (runner), mas com **toda a lógica no `runner.py`** — o CLI só faz wiring de opções → `TaskSpec` → `TaskRunner`. Nenhuma fase nova no `cli.py`.
- **`apply_code_hook` pode rodar isolado** e duplicar a fase SANDBOX. Se confirmar que executa, uso `run_isolated=False` no IMPLEMENT e deixo a execução **só** no SANDBOX. Isso mantém o protocolo com uma única porta de execução.
- **JSON no PLAN** pode falhar com modelo pequeno (0.5B). Mitigação: prompt curto + exemplo mínimo + 1 retry. Se falhar de novo, `FAILED` com motivo claro — não vale continuar sem plano.
- **Retry no DRAFT** custa mais tokens (regenera do zero). Mas você pediu e faz sentido pro modelo em uso: draft pequeno é mais barato que "implement parcial com feedback" que costuma degenerar. Aceito.
- **`SandboxController` pode não ter timeout robusto** para código em loop infinito. MVP aceita o `timeout` do próprio controller; se ele não matar o processo, é bug pré-existente do sandbox — não é regressão nossa.
- **`.orn/tasks/` no CWD**: se o usuário rodar `orn task run` fora de um projeto, cria `.orn/tasks/` no diretório corrente. Aceitável — mas vou documentar no `--help`.

---

## 0.7 Checklist do passo 0 → passo 1

Antes de escrever `model.py`:

- [ ] Confirmar os 8 itens da seção 0.5 lendo o fonte real.
- [ ] Decidir `pydantic` vs `dataclass` (depende do item 8).
- [ ] Fechar assinatura de `TaskStore` (métodos exatos: `new`, `load`, `save`, `append_event`, `save_artifact`, `list`, `delete`).
- [ ] Fechar schema do `state.json` (versão `schema: 1` pro futuro).
- [ ] Definir transições válidas de `TaskStatus` (não deixar `RUNNING → PENDING`, etc.).

Depois disso, **passo 1** entrega:
- `engine/tasks/model.py` com `TaskSpec`, `TaskArtifact`, `Task`, `TaskStatus`, `Phase`, `to_dict/from_dict`.
- `engine/tasks/store.py` com `TaskStore` (JSON atômico + NDJSON append).
- `_run_tests` em `store.py` no estilo `events.py` (`python -m engine.tasks.store --test`).

---

