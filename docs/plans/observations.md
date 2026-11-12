# Observações de uso real — 2026-11-12 a 2026-11-19

**Servidor:** online durante testes
**Modelo:** Qwen 0.5B Q2_K em N2808
**Backend:** orn.dll

## Legenda
- ✅ aplicado, mudança útil
- ⚠️ cosmético (usuário cancelou)
- ❌ falha do modelo (guards ativaram)
- 🐛 bug no sistema (comportamento inesperado)

## Sessão 1 — logic_filter.py

| # | Comando | Outcome | Tempo | Notas |
|---|---|---|---|---|
| A | docstring _validar_python | | | |
| B | comment topo validar_output | | | |
| C | validação None | | | |

## Sessão 2 — code_sandbox.py
...

## Padrões observados

### Funcionaram consistentemente
- docstring via template (sem modelo)
- rename via template (sem modelo)
- instruções com verbo concreto + alvo específico ("adicione validação de X")

### Falharam ou produziram cosmético
- `melhore X` (vago)
- instruções sem alvo explícito
- estruturas grandes (>30 linhas)

### Surpresas
- (anotar)
