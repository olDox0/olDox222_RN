# ORN — Fase 5.1: Symbol Resolver

**Objetivo:** dado `orn fix arq.py -i "..."`, resolver o símbolo-alvo
na instrução e montar prompt cirúrgico (snippet em vez de arquivo).

## Problema observado (2026-11-05)

`orn fix engine/cli.py -i "melhore session_cmd"` → modelo pegou `_fmt_ms`.
Causa: 900 linhas no prompt. Solução: extrair só `session_cmd` (~40 linhas).

## Escopo (F5.1 apenas)

[ ] engine/tools/symbol_indexer.py
[ ] engine/tools/symbol_resolver.py
[ ] patch _run_fix: usar resolve() quando match confiante
[ ] patch _run_audit: idem (audit cirúrgico)
[ ] testes: test_symbol_indexer.py, test_symbol_resolver.py

## Fora de escopo (F5.2+)

- Fallback para "adicionar código"
- Dep graph (imports usados pela função)
- Cache persistente (F5.3)
- Multi-arquivo (F5.4)

## Critérios de aceite

1. `orn fix cli.py -i "melhore session_cmd"` → prompt < 1200 tk
2. `orn fix cli.py -i "crie função foo"` → fallback (arquivo inteiro)
3. `orn fix cli.py -i "renomeie session_cmd para repl_cmd"` → detecta
   ambiguidade, lista match, pede confirmação
4. `pytest tests/test_symbol_*.py` verde
