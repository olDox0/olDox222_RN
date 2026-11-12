# ORN × Doxly — Integração IDE

**Status:** 📋 Planejado | **Depende de:** F5 (fix cirúrgico), F6.7 (Consult/RAG)
**Alvo:** Doxly (fork de LiteXL) + ORN server em port 8371

---

## 1. Motivação

Hoje o fluxo é:
1. Usuário abre terminal
2. Roda `orn fix arquivo.py -i "..."` 
3. Copia patch manualmente
4. Cola no editor
5. Salva

**Isso quebra o flow de edição.** Objetivo: o usuário seleciona código no IDE, aperta
`Alt+I`, digita instrução, vê o diff inline, clica **Aplicar** ou **Rejeitar**.

**Princípio:** o IDE é cliente fino. Toda inteligência (símbolo, guard, template,
modelo) fica no ORN. O IDE só pede e aplica.

---

## 2. Arquitetura

```
┌─────────────────────────────────────────────────┐
│  Doxly (LiteXL fork)                            │
│                                                 │
│  ┌──────────────────────┐   ┌────────────────┐  │
│  │ Frameless titlebar   │   │ Keybindings    │  │
│  │ [🤖 AI] botão        │   │ Alt+I          │  │
│  └──────────┬───────────┘   │ Ctrl+Shift+I   │  │
│             │               │ Ctrl+Enter     │  │
│             ▼               └───────┬────────┘  │
│  ┌──────────────────────────────────▼─────────┐ │
│  │  plugins/ai_bridge.lua                     │ │
│  │  ┌──────────────────────────────────────┐  │ │
│  │  │ ai.ask(prompt, opts, cb)             │  │ │
│  │  │ ai.fix_selection(buf, instr, cb)     │  │ │
│  │  │ ai.show_diff_panel(hunks, cb)        │  │ │
│  │  │ ai.consult_search(q, cb)             │  │ │
│  │  └──────────────┬───────────────────────┘  │ │
│  │                 │ process.start()           │ │
│  └─────────────────┼───────────────────────────┘ │
│                    │                             │
└────────────────────┼─────────────────────────────┘
                     │ shell
                     ▼
        ┌────────────────────────────┐
        │  orn-server ask --stream   │
        │  orn fix --json-output     │
        │  orn consult search --json │
        └────────────┬───────────────┘
                     │ TCP 8371 (loopback)
                     ▼
        ┌────────────────────────────┐
        │  orn-server (persistente)  │
        │  • modelo em RAM           │
        │  • cache de símbolos       │
        │  • surgical / guards       │
        └────────────────────────────┘
```

**Decisão travada:** comunicação via `process.start()` (subprocess) em vez de TCP
direto do Lua. Razões:
- LiteXL 2.x tem `process.start()` com stdout pipe assíncrono
- Não requer `luasocket` (C extension)
- `orn-server` já existe e mantém modelo em RAM — startup é ~5s (não 80s)
- Se virar gargalo, F7.x adiciona `luasocket` via C extension

---

## 3. CLI additions necessárias

Antes do plugin, 3 flags no ORN CLI:

### 3.1 `orn-server ask --stream --json`

```bash
orn-server ask "adicione docstring" --stream
```

Saída NDJSON:
```jsonl
{"event":"start","model":"smollm"}
{"event":"chunk","delta":"def "}
{"event":"chunk","delta":"foo"}
{"event":"done","output":"def foo():\n...","elapsed_s":7.2,"tokens":248}
{"event":"error","error":"..."}   # opcional
```

**Já existe** em `orn-server` (streaming TCP). Só falta expor no CLI.

### 3.2 `orn fix --json-output`

```bash
orn fix arquivo.py -i "..." --symbol-auto --json-output
```

Saída JSON única:
```json
{
  "success": true,
  "applied": false,
  "hunks": [
    {"line": 55, "removed": ["def _fmt_ms(value: float) -> str:"], "added": [...]}
  ],
  "surgical_trace": {"outcome": "ok_block_format", "resolved": "_fmt_ms", ...},
  "symbol_mode": "auto"
}
```

**Novo.** Adiciona `--json-output` como alias estruturado do display atual.

### 3.3 `orn consult search --json` (já existe)

```bash
orn consult search "context manager" --json
```

```json
[{"path": "...", "title": "...", "snippet": "...", "category": "..."}]
```

**Já implementado** (F5.x).

### 3.4 `orn-server cancel <request_id>`

```bash
orn-server cancel 42
```

Cancela inferência em andamento. Necessário quando usuário fecha painel antes da resposta.

**Novo.** `orn-server` precisa de ID por request (streaming) e thread-safe cancellation.

---

## 4. Componentes UI

### 4.1 Frameless button (`[🤖 AI]`)

**Onde:** titlebar customizada do Doxly (canto direito, ao lado dos botões de janela).
**Ação:** abre `ai_prompt` panel (mode chat).
**Implementação:**
- C (titlebar widget) se frameless for nativo → 1 botão de ~20px
- Ou Lua, se frameless for Lua-based

**Contrato:** button click → `core.command.perform("ai:prompt")` → plugin Lua recebe.

### 4.2 `ai_prompt` panel (floating overlay)

**Layout:**
```
┌───────────────────────────────────────────┐
│  🤖 ORN — pergunte ou peça alteração      │
│  ─────────────────────────────────────    │
│  ┌──────────────────────────────────────┐ │
│  │ > _                                  │ │
│  │                                      │ │
│  └──────────────────────────────────────┘ │
│  [Enter] enviar  [Esc] cancelar           │
│  ─────────────────────────────────────    │
│  Contexto: [✓] seleção  [ ] arquivo       │
│            [✓] consult  [ ] projeto       │
└───────────────────────────────────────────┘
```

**Comportamento:**
- `Enter` → `ai.ask(prompt, opts, callback)`
- `Esc` → fecha painel
- Streaming: texto aparece linha por linha no painel
- Se instrução pede alteração (heurística: "adicione/mude/troque/substitua"):
  resposta vira `ai.show_diff_panel(hunks, callback)`

**Modos:**
| Seleção ativa | Modo | Comando CLI |
|---|---|---|
| Sim | `surgical` | `orn fix --symbol-auto` na seleção |
| Não | `whole-file` | `orn think` ou `orn fix` no arquivo |

### 4.3 `diff_panel` (floating)

**Layout:**
```
┌─────────────────────────────────────────────┐
│  🤖 Patch proposto — engine/cli.py          │
│  ══════════════════════════════════════════ │
│  @55                                        │
│  - def _fmt_ms(value: float) -> str:        │
│  -     value = float(value or 0)            │
│  + def _fmt_ms(value: float) -> str:        │
│  +     """Formata ms como 'Xs' ou 'Xms'."""│
│  +     value = float(value or 0)            │
│                                             │
│  @102                                       │
│  -     return f"{value:.3f}ms"              │
│  +     return f"{value:.3f}ms"  # vazio ok  │
│  ══════════════════════════════════════════ │
│  [Ctrl+Enter] Aplicar  [Esc] Rejeitar       │
│  Hunk 1/2 — [Tab] próximo  [Shift+Tab] ant. │
└─────────────────────────────────────────────┘
```

**Comportamento:**
- Cor: `-` vermelho, `+` verde, contexto cinza
- Navegação hunk-a-hunk com `Tab`/`Shift+Tab`
- Aplicar hunk individual ou todos
- `Ctrl+Enter` aplica tudo, `Esc` rejeita
- Undo após aplicar: `Ctrl+Z` do editor (aplicação usa `doc:insert`/`doc:remove`)

**Implementação Lua:**
- `View:extend()` custom com `Doc` interno (aproveita syntax highlighting)
- Ou `CommandView` simples (texto sem highlight, MVP)

### 4.4 `consult_panel` (opcional)

**Atalho:** `Ctrl+Shift+D` (D de docs)
**Ação:** busca FTS5 instantânea, sem LLM
**Layout:** lista de resultados com `path` + `snippet`
**Click:** abre arquivo na linha correspondente

---

## 5. Atalhos

| Atalho | Contexto | Ação |
|---|---|---|
| **Alt+I** | Seleção ativa | `ai:fix_selection` → surgical fix → diff_panel |
| **Alt+I** | Sem seleção | `ai:prompt` → chat mode |
| **Ctrl+Shift+I** | Qualquer | `ai:prompt` → chat mode com contexto do arquivo |
| **Ctrl+Shift+D** | Qualquer | `ai:consult` → painel de docs FTS5 |
| **Ctrl+Enter** | diff_panel | Aplicar patch |
| **Esc** | diff_panel / prompt | Fechar/rejeitar |
| **Tab / Shift+Tab** | diff_panel | Próximo/anterior hunk |
| **Ctrl+. ** | prompt | Toggle opções (consult, contexto) |

**Colisões:** verificar com Doxly keymap atual. Se `Alt+I` colidir, usar `Alt+K` ou `F2`.

---

## 6. Contratos (Lua ↔ CLI)

### 6.1 `ai.ask(prompt, opts, callback)`

```lua
--- @param prompt string
--- @param opts table {
---   context: "none"|"selection"|"file"|"project",
---   consult: boolean,  -- RAG via Consult
---   max_tokens: integer,
---   stream: boolean,
--- }
--- @param callback function(event, data)
---   event ∈ "start" | "chunk" | "done" | "error"
---   data = string (chunk) ou table (done/error)
function ai.ask(prompt, opts, callback)
```

Internamente: `process.start { "orn-server", "ask", prompt, "--stream", "--json", ... }`.

### 6.2 `ai.fix_selection(buffer, instruction, callback)`

```lua
--- @param buffer core.docview — doc ativo
--- @param instruction string — texto do prompt
--- @param callback function(result)
---   result = {success, hunks, error}
function ai.fix_selection(buffer, instruction, callback)
```

**Problema:** `orn fix file.py` lê do disco. Se o buffer tem edições não salvas, o patch é gerado contra disco → aplicação no buffer pode falhar.

**Solução:** salvar buffer silenciosamente (`doc:save()`) antes de chamar, ou usar stdin:
```bash
orn fix --stdin -i "..." <<< "$(cat buffer)"
```

**Decisão F7:** adicionar `--stdin` ao `orn fix`. Mais simples que sincronizar buffer.

### 6.3 `ai.show_diff_panel(hunks, on_apply, on_reject)`

```lua
--- @param hunks table[] — [{line: int, removed: string[], added: string[]}]
--- @param on_apply function(hunks_applied: table[])
--- @param on_reject function()
function ai.show_diff_panel(hunks, on_apply, on_reject)
```

Aplicação no buffer: `doc:remove(line, len)` + `doc:insert(line, text)`.

---

## 7. Faseamento

### F7.1 — CLI additions
**Escopo:** 3.1 (stream), 3.2 (json), 3.4 (cancel) + `--stdin` no fix.
**Critério:** `orn-server ask "x" --stream` retorna NDJSON válido; `orn fix --json-output` retorna hunks estruturados.

### F7.2 — Plugin MVP (chat only)
**Escopo:** `ai_bridge.lua` com `ai.ask` + `ai_prompt` panel + framing button (se título permitir sem rebuild C).
**Critério:** clicar botão AI → digitar → ver resposta streaming no painel.

### F7.3 — Selection + Alt+I + diff panel
**Escopo:** `ai.fix_selection` + `diff_panel` com apply/reject.
**Critério:** selecionar `_fmt_ms`, Alt+I, "adicione docstring" → diff mostra AST docstring → Ctrl+Enter aplica → buffer atualizado + undo funciona.

### F7.4 — Consult integration
**Escopo:** `--consult` no fix, `Ctrl+Shift+D` para search.
**Critério:** instrução vaga + Ctrl+. toggle consult → resposta com citação de fonte.

### F7.5 — Diff panel syntax highlighting
**Escopo:** usar `Doc` interno com tokenizer do Doxly.
**Critério:** diff de Python tem cores de sintaxe (não só -/+ vermelho/verde).

### F7.6 — Hunk-level apply
**Escopo:** aplicar hunks individuais (Tab navigation).
**Critério:** diff com 3 hunks → aceitar 2, rejeitar 1 → buffer reflete só as 2.

### F7.7 — Project context
**Escopo:** "contexto: projeto" envia `orn grep` + imports. Melhora instruções vagas.
**Critério:** "onde está a validação X?" → resposta referencia arquivo certo.

---

## 8. Riscos

| Risco | Mitigação |
|---|---|
| LiteXL sem `process.start` async | Verificar versão; fallback `io.popen` (bloqueante, mas funciona) |
| Frameless button em C (rebuild) | Se título for C, PR mínimo (~20 linhas); ou menu Lua como fallback |
| Latência ~7s (0.5B N2808) | Streaming visível; `Ctrl+.` para cancelar via `orn-server cancel` |
| Buffer não salvo vs disco | `--stdin` no `orn fix` (F7.1) |
| Modelo inventa `else:` cosmético | Templates AST já interceptam; usuário cancela diff se cosmético |
| `Alt+I` colide com editor | Mapear keymap do Doxly antes; `ai.ask` também via menu/palette |
| Multi-file ambiguidade | F7.7 com `--project` context; preview mostra arquivo alvo |
| Patch destrutivo em método | Guards 3/3b do F5 rejeitam antes do painel aparecer |

---

## 9. Testes

### Unit (Lua)
- `ai_bridge.spec.lua` — mock `process.start`, verifica callbacks para chunk/done/error
- `diff_panel.spec.lua` — mock hunks, verifica Tab/Shift+Tab, Ctrl+Enter aplica

### Integration (Python + CLI)
- `orn-server ask "x" --stream` retorna ≥1 chunk + 1 done
- `orn fix teste.py -i "..." --json-output` retorna hunks com `line >= 1`
- `orn-server cancel <id>` mata inferência em <500ms

### End-to-end (manual, N2808)
1. Abrir Doxly em `engine/cli.py`
2. Selecionar `_fmt_ms` (5 linhas)
3. Alt+I → "adicione docstring" → Enter
4. Ver streaming ~2s
5. Ver diff_panel com docstring proposta
6. Ctrl+Enter → aplicar
7. Ctrl+Z → reverter
8. Repetir com `Alt+I` sem seleção → chat mode

**Critério de sucesso:** 6/7 passos OK, undo funciona em 100%.

---

## 10. Decisões em aberto

### 10.1 Frameless button: C ou Lua?

Depende de como Doxly implementou o frameless. Verificar `src/window.c` ou `data/core/init.lua`.
- Se titlebar é C → PR pequeno ao fork Doxly
- Se titlebar é Lua → só plugin, zero fork

**Decisão pós-F7.2 (após inspeção).**

### 10.2 Diff panel: `Doc` customizado ou `CommandView`?

- **`Doc`**: syntax highlight nativo, mas precisa implementar `View` custom (~200 linhas Lua)
- **`CommandView`**: 20 linhas, sem highlight, cores manuais

**Decisão:** `CommandView` no F7.3 (MVP rápido), `Doc` no F7.5 (refinamento).

### 10.3 Streaming: NDJSON ou Server-Sent Events?

`orn-server` já fala NDJSON (uma linha JSON por evento). Plugin Lua lê `stdout` linha-a-linha. **NDJSON, sem mudar nada no server.**

### 10.4 Aplicação: `doc:insert` ou salvar via CLI?

- **`doc:insert`**: undo nativo do editor, mais clean
- **Salvar + reload**: perde undo, mais simples

**Decisão:** `doc:insert` (undo é crítico para UX).

### 10.5 Consult panel: atalho dedicado ou toggle no prompt?

- **Dedicado** (`Ctrl+Shift+D`): fluxo separado, descoberta clara
- **Toggle** (`Ctrl+.` no prompt): menos atalhos, mais compacto

**Decisão:** ambos. `Ctrl+Shift+D` para busca direta; `Ctrl+.` no prompt para RAG.

---

## 11. Não escopo (F7+)

- **Agent mode** (multi-file edit autônomo): F8+
- **Auto-complete inline** (copilot-style): F8+, precisa modelo maior
- **Chat persistente com histórico longo**: F8+, precisa VectorDB
- **Cloud sync**: nunca (filosofia ORN local-first)

---

## 12. Entregável final

`plugins/ai/` no repo Doxly:
```
plugins/ai/
├── init.lua              ~50 linhas  (registro, atalhos)
├── ai_bridge.lua         ~200 linhas (process.start, parsing)
├── ai_prompt.lua         ~150 linhas (overlay de input)
├── diff_panel.lua        ~300 linhas (View custom, apply/reject)
├── consult_panel.lua     ~100 linhas (lista FTS5)
└── config.lua            ~30 linhas  (endpoint, tokens, defaults)
```

**Total:** ~830 linhas Lua + 4 alterações CLI (Python) + talvez 1 PR C.

**Tempo estimado:** 3-4 sessões (uma por F7.1–F7.4).

---

## 13. Checklist de pré-requisitos

Antes de começar F7.1:

- [ ] F5 fechada (✅ commit `6fb3bc0` + `d23d903`)
- [ ] `orn-server` estável em `--bg` por 1 semana
- [ ] F6.7 (Consult/RAG) implementado ou em progresso
- [ ] Doxly compilando localmente (para testar C changes se necessário)
- [ ] Keymap `Alt+I` verificado livre em Doxly

---

*Planejado em 2026-11-12 · Após uso real de F5 por 1 semana.*
```

## Documento complementar — `docs/planning/vol7_ux_mockup.md`

```cmd
notepad docs\planning\vol7_ux_mockup.md
```

```markdown
# ORN × Doxly — UX Mockup

## Estado 1: Edição normal

```
┌─────────────────────────────────────────────────┐
│  File  Edit  View  Search           [🤖 AI] [_][□][X] │
├─────────────────────────────────────────────────┤
│  1  def _fmt_ms(value: float) -> str:           │
│  2      value = float(value or 0)               │
│  3      if value >= 1000:                       │
│  4          return f"{value / 1000.0:.3f}s"     │
│  5      return f"{value:.3f}ms"                 │
│                                                 │
│  engine/cli.py                     Ln 3, Col 5  │
└─────────────────────────────────────────────────┘
```

## Estado 2: Seleção + Alt+I

```
┌─────────────────────────────────────────────────┐
│  File  Edit  View  Search           [🤖 AI] [_][□][X] │
├─────────────────────────────────────────────────┤
│  1  def _fmt_ms(value: float) -> str:           │
│  2  ▓▓▓▓ value = float(value or 0)              │ ← seleção
│  3  ▓▓▓▓ if value >= 1000:                      │
│  4  ▓▓▓▓     return f"{value / 1000.0:.3f}s"    │
│  5  ▓▓▓▓ return f"{value:.3f}ms"                │
│                                                 │
│         ┌───────────────────────────────┐       │
│         │ 🤖 O que fazer com seleção?   │       │
│         │ > _                           │       │
│         └───────────────────────────────┘       │
└─────────────────────────────────────────────────┘
```

## Estado 3: Streaming (após "adicione docstring")

```
┌─────────────────────────────────────────────────┐
│         ┌───────────────────────────────┐       │
│         │ 🤖 Gerando patch... 3/8 linhas│       │
│         │ ███░░░░░░░░░░░░░  2.3s        │       │
│         │ [Esc] cancelar                │       │
│         └───────────────────────────────┘       │
└─────────────────────────────────────────────────┘
```

## Estado 4: Diff panel

```
┌─────────────────────────────────────────────────┐
│  ┌────────────────────────────────────────────┐ │
│  │ 🤖 Patch proposto — _fmt_ms                │ │
│  │ ────────────────────────────────────────── │ │
│  │  @55                                       │ │
│  │  - def _fmt_ms(value: float) -> str:       │ │
│  │  -     value = float(value or 0)           │ │
│  │  + def _fmt_ms(value: float) -> str:       │ │
│  │  +     """Formata ms como 'Xs' ou 'Xms'.""" │ │
│  │  +     value = float(value or 0)           │ │
│  │  ────────────────────────────────────────── │ │
│  │  [Ctrl+Enter] Aplicar   [Esc] Rejeitar     │ │
│  │  1 hunk — confiança: high                  │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

## Estado 5: Consult (Ctrl+Shift+D)

```
┌─────────────────────────────────────────────────┐
│  ┌────────────────────────────────────────────┐ │
│  │ 🔍 Consult — "context manager"             │ │
│  │ > _                                        │ │
│  │ ────────────────────────────────────────── │ │
│  │ [1] python/cheatsheet/context_managers     │ │
│  │     @contextmanager usage...               │ │
│  │ [2] python_basic_py4e/ch11_regex           │ │
│  │     Regex with context managers...         │ │
│  │ [3] python_basic_byteofpython/io           │ │
│  │     File IO and `with` statement...        │ │
│  │ ────────────────────────────────────────── │ │
│  │ [Enter] abrir   [Alt+I] fix com contexto   │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

## Estado 6: Undo pós-aplicação

```
┌─────────────────────────────────────────────────┐
│  File  Edit  View  Search           [🤖 AI] [_][□][X] │
├─────────────────────────────────────────────────┤
│  1  def _fmt_ms(value: float) -> str:           │
│  2      """Formata ms como 'Xs' ou 'Xms'."""    │ ← novo
│  3      value = float(value or 0)               │
│  4      if value >= 1000:                       │
│  5          return f"{value / 1000.0:.3f}s"     │
│  6      return f"{value:.3f}ms"                 │
│                                                 │
│  ⏱ undo: ai:apply (Ctrl+Z para reverter)        │
│  engine/cli.py                     Ln 2, Col 5  │
└─────────────────────────────────────────────────┘
```

## Princípios de UX

1. **Nunca modal**: painéis são flutuantes, editor continua editável atrás
2. **Sempre undoable**: aplicar = `doc:insert`, `Ctrl+Z` reverte
3. **Sempre cancelável**: `Esc` a qualquer momento
4. **Nunca bloqueante**: streaming mostra progresso; usuário pode continuar lendo
5. **Transparente**: mostra `symbol_mode`, `confidence`, `outcome` (herança de `-v`)
