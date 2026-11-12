# ORN — Fase 6: Estabilização e Dívida Técnica

**Início previsto:** após F5 fechada
**Escopo:** consolidar o que existe, resolver dívidas acumuladas

---

## F6.1 — Refactor `_run_fix` (OSL-4 violado)

**Problema:** `_run_fix` em `engine/core/executive.py` tem 147 linhas (OSL-4 recomenda ≤ 60).

**Causa:** patches incrementais (raw_output_override, symbol_mode, hunks_override, surgical_trace, guards) empilharam.

**Fix:**
```
_run_fix (15 linhas) — orquestra:
  ├─ _prepare_fix(payload, context) → FixContext
  ├─ _generate_fix(ctx) → DiffResult
  └─ _finalize_fix(result, ctx) → GoalResult
```

**Critério:** `orn fix` regressão limpa em todos os 8 cenários de F5.

---

## F6.2 — Telemetria Windows

**Problemas:**
- `rss_mb=0.0` em `orn-server status` (Windows sem `resource` e sem `psutil`)
- `lib_bin/` vazio: Vulcan procura em `.doxoade/vulcan/lib_bin/` mas `orn.dll` está em `native/`

**Fix:**
- Fallback `psutil` instalado (não obrigatório, mas detectado)
- Ou `ctypes.PSAPI` para RSS no Windows
- `_vulcan_boot` procura em `native/` também

---

## F6.3 — `__pycache__` volta em `doxoade save --apply`

**Problema:** `.gitignore` tem `__pycache__/` mas `doxoade save --apply` commita mesmo assim.

**Causa provável:** `doxoade save` usa `git add -A` ou `git add .` sem respeitar ignore em algum ponto.

**Fix:** investigar `doxoade/commands/save.py` — verificar se `git add` é feito com `--` e respeita `core.excludesFile`.

**Impacto:** cada `save` polui o repo com 28+ `.pyc`.

---

## F6.4 — MA'AT falsos positivos (`check_contracts`)

**Problema:**
```
[MISSING_ARGS] L146 → resolve (Faltam 5 argumento(s) obrigatório(s))
```
`resolve(instruction, index, *, scope=None, ...)` tem **2 args obrigatórios**, não 5.

**Causa:** MA'AT conta `*` (keyword-only separator) como required.

**Fix:** em `doxoade/commands/check_contracts.py`, ignorar `kwonlyargs` com default.

**Escopo:** 1-2 horas, 26 falsos positivos eliminados.

---

## F6.5 — `orn grep` sem cache em `build_dir`

**Problema:** `orn grep` em `engine/` reconstrói o índice a cada chamada (~500ms). Não usa `load_or_build`.

**Fix:**
```python
# Em symbol_indexer.build_dir, adicionar persist
# Ou em cli.grep, trocar build_dir por load_or_build_dir
```

**Critério:** segunda chamada de `orn grep` em `engine/` < 100ms.

---

## F6.6 — F5.10 preventivo (escopo em `_parse_ast_replacements`)

**Problema latente:** quando high-confidence, se o modelo devolver **classe inteira** em vez do método pedido, `_parse_ast_replacements` mapeia `ClassDef` → hunk que substitui a classe toda.

**Cenário:** `orn fix cli.py -i "melhore session_cmd"` com `_parse_ast_replacements` retornando `session_cmd` + `CodeDrawer` + outras classes.

**Fix:**
```python
def _parse_ast_replacements(text, original_content, target_name=None):
    ...
    if target_name and node.name != target_name:
        continue  # ignora símbolos fora do escopo
```

**Critério:** se modelo reescrever `class CodeDrawer` quando pediu método `upsert_snippet`, `_parse_ast_replacements` retorna `[]` (fallback pega o erro).

**Prioridade:** baixa — não apareceu em uso real. Só se virar recorrente.

---

## F6.7 — Consult/RAG (T6 do spec)

**Problema:** instruções vagas (`melhore X`) geram cosmético. Qwen 0.5B não tem contexto.

**Solução:** RAG via `ConsultBridge` + `consult_docs_fts5.db` populado.

**Escopo:** especificado em `docs/specs/consult_integration.md`, Fase T6.

**Pré-requisito:** `doxoade consult index` no repo do Doxoade.

**Critério de aceite:** `orn fix X -i "adicione logging" --consult` injeta 2 exemplos de docs, sucesso sobe 30%+.

---

## F6.8 — `__main__.py` wrapper redundante

**Problema:** `engine/__main__.py`, `engine/server/__main__.py`, `engine/web/__main__.py` têm **~200 linhas cada** de bootstrap Vulcan duplicado.

**Fix:** extrair para `engine/_bootstrap_vulcan.py` e importar.

**Critério:** 3 arquivos < 30 linhas cada.

---

## Priorização

| # | Fase | Impacto | Esforço |
|---|---|---|---|
| 1 | F6.3 (`__pycache__`) | Alto (poluição recorrente) | 1h |
| 2 | F6.2 (`rss_mb`, Vulcan) | Alto (telemetria honesta) | 2h |
| 3 | F6.1 (refactor `_run_fix`) | Médio (OSL-4) | 2h |
| 4 | F6.4 (MA'AT) | Médio (UX `save`) | 2h |
| 5 | F6.5 (`grep` cache) | Médio | 30min |
| 6 | F6.8 (`__main__`) | Baixo | 1h |
| 7 | F6.6 (F5.10 preventivo) | Baixo | 20min |
| 8 | F6.7 (Consult/RAG) | Alto (próxima fronteira) | Sessão |

**F6.1-F6.5 são 1 sessão.** F6.7 é sessão própria (depende de DB).
