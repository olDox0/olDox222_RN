# ORN — Fase 5 Completa: Fix Cirúrgico

**Data:** 2026-11-12 | **Status:** ✅ Concluída | **Commits:** `6fb3bc0`, `d23d903`, +mensagem

---

## O que F5 entregou

### F5.1 — Indexação de símbolos
- `engine/tools/symbol_indexer.py` (~400 linhas, 39 testes embutidos)
  - AST → `Symbol[]` com signature, docstring, parent, body_hash
  - Cache JSON com mtime/size invalidation
- `engine/tools/symbol_resolver.py` (~470 linhas, 25 testes embutidos)
  - Instrução → `SymbolMatch` com heurística two-tier
  - Stopwords PT-BR com fallback (dividir/extrair/separar mantidos quando exact)

### F5.2 — Guards defensivos (8 camadas)

| Guard | O que rejeita | Onde |
|---|---|---|
| A | Modelo copiou system prompt | `_run_fix` |
| B | Instrução cita símbolo inexistente no alvo | `_try_surgical_path` |
| C | Output < 30% do tamanho original | `_try_surgical_path` |
| 0 | Marcadores de template (`@N`, "linha antiga") | `_parse_ast_replacements` |
| 1 | `print()` ou `if __name__` no top-level | `_parse_ast_replacements` |
| 2 | Duplicatas de definição (modelo quebrado) | `_parse_ast_replacements` |
| 3 | Método sem indentação (destruiria classe) | `_parse_ast_replacements` |
| 3b | Idem, no fallback block | `_try_surgical_path` |
| no_op | `removed == added` após normalização | `_apply_and_finalize` |

### F5.3 — Cache de símbolos
- `load_or_build()`: ~100ms → ~5ms em hit
- `orn symbol cache --show/--clear/--rebuild`
- Cache path: `data/symbol_cache.json`

### F5.4 — Busca de símbolos
- `orn grep <símbolo>` com `--pattern`, `--kind`, `--path`, `--json`, `--limit`
- `skip_dirs` expandido: `lixao/`, `thirdparty/`, `experiments/`, `data/`, `docs/` excluídos
- `build_dir` aceita arquivo único além de diretório

### F5.5 — Diagnóstico via `-v`
- `DiffResult.surgical_trace: dict` propagado no metadata
- `-v` em falha mostra: `outcome`, `matches` (com score/conf), `resolved`, `raw` (800 chars)
- **Torna todo comportamento do modelo observável** — o "ver o bruto" que motivou a sessão

### F5.6 — Templates determinísticos
- `engine/tools/fix_templates.py` (18 testes)
- Docstring via AST (Sphinx pattern)
- Comentário no topo (não duplica docstring existente — F5.9)
- Rename com word boundary (`_fmt_ms` ≠ `_fmt_ms_extra`)
- **Sem chamar modelo** — instantâneo e determinístico

### F5.7 — Block-only prompt
- `@N` removido (Qwen 0.5B copia template literalmente — evidência no trace)
- `_parse_ast_replacements` convertido em parser primário
- `build_prompt_surgical` simplificado (42 linhas)

### F5.8 — Fixes de uso real
- `confidence=medium` aceito quando `pick_best` retornou (margem ≥ 0.20)
- `_extract_comment_text` retorna `(text, source)` para não duplicar docstring
- Guard 3 + 3b em métodos

### F5.9 — Fallback controlado
- Fallback whole-file recusa quando surgical identificou símbolo (low/medium)
- Mensagem honesta em `--symbol` (`'Match com confiança apenas 'medium''` em vez de `"Use --symbol-auto"` que mentia)

---

## Fluxo final

```
orn fix arquivo.py -i "instrução" [--symbol|--symbol-auto] [-v]

  Prioridade 1 ── hunks_override (fase 2 do surgical)
  Prioridade 2 ── raw_output_override (fase 2 do whole-file)

  Prioridade 3 ── surgical (--symbol ou --symbol-auto):
    │
    ├─ resolve símbolo (índice + cache)
    ├─ filtra para arquivo-alvo (F5.5c)
    │
    ├─ Guard B: instrução cita símbolo inexistente → erro
    ├─ Guard medium/low: símbolo encontrado, confiança baixa → erro
    │
    ├─ Template determinístico (docstring/comment/rename) → AST, sem modelo
    ├─ Símbolo > 100 linhas → erro (Qwen 0.5B não escala)
    │
    ├─ Modelo com block prompt
    │   ├─ Guard A: copiou template → erro
    │   ├─ parse_diff (@N) prioritário
    │   ├─ Guard 3: método sem indent → erro
    │   └─ Guard C: output < 30% → erro
    │
    └─ Block format via _parse_ast_replacements + guards 0/1/2

  Prioridade 4 ── whole-file (instruções sem símbolo):
    └─ fallback com build_prompt + parse_ast
```

---

## Cobertura

| Módulo | Testes | Comando |
|---|---|---|
| `symbol_indexer` | 39 | `python -m engine.tools.symbol_indexer --test` |
| `symbol_resolver` | 25 | `python -m engine.tools.symbol_resolver --test` |
| `fix_templates` | 18 | `python -m engine.tools.fix_templates --test` |
| **Total** | **82+** | |

---

## Decisões travadas

1. **`@N` abandonado em prompt cirúrgico** — Qwen 0.5B copia template. Block format é o caminho.
2. **Fallback whole-file é perigoso** — recusa quando surgical identificou símbolo (mesmo com confiança baixa).
3. **Método sem indent = destrutivo** — Guard 3/3b rejeitam antes do usuário ver patch.
4. **Template antes do limite de tamanho** — `_run_fix` (147 linhas) aceita `top_comment` via template, mas recusa via modelo.
5. **`confidence=medium` aceito** — desde que `pick_best` retornou com margem ≥ 0.20.

---

## Limitações conhecidas (Qwen 0.5B, não do sistema)

| Instrução | Comportamento |
|---|---|
| `melhore X` (vago) | Cosmético (`else:` adicionado, blanks) |
| `melhore X para Y` (específico) | 60-70% real |
| Múltiplas ações (`A e B e C`) | Confunde |
| Símbolos > 100 linhas | Erro `symbol_too_large` |
| `print()` no output | Guard 1 rejeita |
| Reescrita de classe inteira | `_parse_ast_replacements` mapeia `ClassDef` |

**O sistema não resolve o modelo. O sistema sobrevive ao modelo.**
