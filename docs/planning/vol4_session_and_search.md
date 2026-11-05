# ORN — Sessão 2026.11.04: Session REPL + Plano de Busca de Símbolos

**Volume:** 4 (planejamento) | **Data:** 2026-11-04
**Hardware:** Celeron N2808 (2 threads, sem AVX) | Windows | Python 3.12
**Servidor:** online, backend `orn.dll` nativo ativo
**Modelo:** Qwen2.5-Coder-0.5B-Instruct-Q2_K

---

## 1. Contexto

Sessão de testes de campo sobre `orn fix` e `orn session`. Objetivo original:
validar o fluxo interativo (dry-run → confirmação → apply) e a experiência
de edição dentro de REPL.

Resultado: **4 bugs identificados**, sendo 2 triviais (correção imediata) e
2 que motivam a Fase 5 do roadmap (busca de símbolos e contexto cirúrgico).

---

## 2. Bugs Identificados

### B-001 — Session REPL não reconhece comandos com `\` (backslash)
**Severidade:** Média
**Reprodução:**
```
orn[📄 teste_fix.py]> \help
  Modo direto — carregando modelo...
  def solve(data: object) -> object:
      """Fallback determinístico..."""
      return data
```

**Esperado:** mensagem de ajuda (igual `/help`)
**Real:** string `\help` foi enviada ao modelo como pergunta livre → o
modelo devolveu fallback degenerado.

**Causa raiz:** `session_cmd` só reconhece `cmd in ("/exit", "/quit", ":q")`
e `cmd.startswith("/")`. Tudo mais cai no fallback `result = ex.process_goal(intent="think", ...)`.

**Correção:** aceitar `/cmd`, `\cmd` e `cmd` puro para um conjunto de
comandos conhecidos. Comando não reconhecido → mostrar ajuda, não chamar
o modelo.

```python
cmd_raw = input(...).strip()
cmd = cmd_raw.replace("\\", "/", 1) if cmd_raw.startswith("\\") else cmd_raw
known_commands = {"/help", "/open", "/fix", "/apply", "/diff",
                  "/undo", "/status", "/exit", "/quit", "/clear"}
base = cmd.split()[0].lower() if cmd else ""
if base in known_commands or base.rstrip(":").replace("/", "") in {
    "help", "open", "fix", "apply", "diff", "undo", "status",
    "exit", "quit", "clear"
}:
    # normaliza para /base
    cmd = "/" + base.lstrip("/").lstrip("\\")
```

### B-002 — `\fix <instrução>` não executa o fix
**Severidade:** Média (mesma raiz de B-001)
**Reprodução:**
```
orn[📄 teste_fix.py]> \fix preciso que voce modularize esse sistema
  def solve(data: object) -> object:  ...
```
**Esperado:** entrar no fluxo de patch (dry-run → confirmação).
**Real:** string inteira enviada ao modelo como `think`.

**Correção:** mesma de B-001. Após normalização, `\fix ...` vira `/fix ...`
e cai no ramo correto.

### B-003 — `orn fix` truncou o diff no meio de uma expressão
**Severidade:** Alta (patch inutilizável, mesmo com confirmação)
**Reprodução:**
```
$ orn fix engine\cli.py -i "veja o def session_cmd(initial_file): e melhore o help dela"
@55
- def _fmt_ms(value: float) -> str:
-     value = float(value or 0)
-     if value >= 1000:
-         return f"{value / 1000.0:.3f}s"
-     return f"{value:.3f}ms"
+ def _fmt_ms(value: float) -> str:
+     value = float(value or 0)
+     if value >= 1000:
+         return f          ← CORTADO AQUI
```

**Esperado:** diff completo da substituição.
**Real:** truncado em `return f` (meio do f-string).

**Causa raiz:** `_run_fix` passa `max_tokens=context.get("max_tokens") or 256`.
256 tokens não cabe substituir `_fmt_ms` (5 linhas) + contexto. O modelo
emite até `return f` e o stop token `<|im_end|>` chega antes da conclusão.

**Correção:** default mais alto + adaptativo:
```python
# engine/core/executive.py — _run_fix
default_tokens = 512
if instruction and "melhore" in instruction.lower():
    default_tokens = 768
max_tokens = context.get("max_tokens") or default_tokens
```
Alternativa melhor (Fase 5): estimar a partir do trecho-alvo (B-005).

### B-004 — Dupla inferência em `orn fix`
**Severidade:** Alta (já reportado em sessão anterior, ainda não validado)
**Reprodução:** (sessão 2026-11-04, sessão anterior)
```
Patch simulado (dry-run): [OK]
Aplicar este patch? [y/N]: y
  [ERRO] Modelo gerou resposta, mas não foi possível extrair...
```

**Esperado:** aplicar o **mesmo patch** exibido.
**Real:** re-chamada ao modelo gerou saída diferente → parser falhou.

**Status:** correção proposta (`raw_output_override` em `generate_and_apply`
e `context["raw_output_override"]` em `_run_fix`) já especificada no relatório
anterior. **Pendente de validação nesta sessão** — o patch truncado (B-003)
mascarou o sintoma.

---

## 3. O que já funciona (regressão OK)

| Comando | Estado |
|---|---|
| `orn fix --help` | ✅ |
| `orn session --help` | ✅ |
| `orn-server start --bg` | ✅ (mas está rodando com backend nativo mesmo com `lib_bin/` vazio — investigar em outro momento) |
| `orn-server stop` | ✅ (kill por PID) |
| `orn fix` mostra diff no formato `@N` | ✅ |
| Confirmação `Aplicar? [y/N]` | ✅ |
| Cancelamento (`n`) | ✅ |

---

## 4. Correções imediatas (quick wins, ~15min)

### 4.1 Session parser tolerante
**Arquivo:** `engine/cli.py`, função `session_cmd`
**Mudança:** aceitar `/`, `\` e comando puro; comandos desconhecidos
mostram ajuda em vez de chamar o modelo.

### 4.2 max_tokens adaptativo em `_run_fix`
**Arquivo:** `engine/core/executive.py`, `_run_fix`
**Mudança:** `default_tokens = 512` (era 256); se instrução menciona
"melhore" / "refatore" / "modularize", `768`.

### 4.3 Validação de dupla inferência
**Arquivo:** `engine/cli.py` (`fix` e `session_cmd`) + `engine/tools/diff_engine.py`
**Mudança:** implementar `raw_output_override` (relatório anterior).
Depois disso, rodar:
```
orn fix teste_fix.py -i "adicione tratamento para divisao por zero retornando 0"
# aceitar, verificar com: type teste_fix.py
```

---

## 5. Plano: Sistema de Busca de Símbolos e Contexto Cirúrgico

### 5.1 Motivação

Hoje `orn fix` manda **o arquivo inteiro** ao modelo. Num Celeron N2808
com 0.5B Q2_K:

- Prompt grande → tempo de prompt_eval alto (penaliza em 1.4 t/s)
- Mais contexto = mais alucinação (o modelo ignora a parte relevante)
- Patch truncado (B-003) porque o output precisa competir com input grande

Instruções como `"melhore o help de session_cmd"` são cirúrgicas — o
`session_cmd` tem ~40 linhas em um arquivo de 900+. Enviar 900 linhas
para alterar 40 é desperdício em hardware limitado.

### 5.2 Objetivo

Antes de chamar o LLM:

1. **Resolver** o símbolo-alvo (nome de função, classe, método) na instrução
2. **Extrair** o escopo exato via AST
3. **Analisar** dependências diretas do símbolo (chamadas, imports usados)
4. **Montar prompt cirúrgico** com o trecho-alvo + fronteiras, não o arquivo todo

### 5.3 Arquitetura proposta

```
engine/tools/
├── symbol_indexer.py    ← AST → SymbolIndex (nome, tipo, linhas, assinatura)
├── symbol_resolver.py   ← instrução → SymbolMatch (arquivo, linha_ini, linha_fim)
└── dep_graph.py         ← SymbolIndex → grafo de dependências intra-arquivo
```

### 5.4 Contratos

```python
# engine/tools/symbol_indexer.py
@dataclass
class Symbol:
    name:         str
    kind:         Literal["function", "method", "class", "async_function"]
    file:         Path
    start_line:   int
    end_line:     int
    signature:    str            # "session_cmd(initial_file: str | None)"
    docstring:    str
    parent:       str | None     # classe-mãe, se método
    body_hash:    str            # sha1 do corpo (cache)

class SymbolIndexer:
    def build(self, file: Path) -> list[Symbol]: ...
    def rebuild_from_dir(self, root: Path) -> dict[Path, list[Symbol]]: ...
    def persist(self, cache_path: Path) -> None: ...
    def load(self, cache_path: Path) -> dict[Path, list[Symbol]]: ...

# engine/tools/symbol_resolver.py
@dataclass
class SymbolMatch:
    symbol:       Symbol
    score:        float          # 0..1
    reason:       str            # "name exact", "name partial", "docstring match"

class SymbolResolver:
    def resolve(
        self, instruction: str,
        index: dict[Path, list[Symbol]],
        *, scope: Path | None = None,
    ) -> list[SymbolMatch]: ...
    # heurísticas:
    #   1. procurar tokens da instrução que matcham `symbol.name`
    #   2. preferir symbols com `def` explícito na instrução
    #   3. penalizar symbols cujo body_hash não aparece em cache recente

# engine/tools/dep_graph.py
@dataclass
class DepEdge:
    source: str          # nome do símbolo
    target: str          # nome chamado / importado
    kind:   Literal["call", "import", "inherit"]

class DepGraph:
    def build(self, file: Path) -> list[DepEdge]: ...
    def used_by(self, symbol: str, edges: list[DepEdge]) -> set[str]: ...
```

### 5.5 Integração com `_run_fix`

```python
# pseudocódigo de _run_fix (após Fase 5)
def _run_fix(self, payload, context):
    target_path = Path(payload)
    instruction = context["instruction"]

    index = SymbolIndexer().load(cache_path) or SymbolIndexer().build(target_path)
    matches = SymbolResolver().resolve(instruction, index, scope=target_path)

    if matches:
        best = matches[0].symbol
        snippet = extract_lines(target_path, best.start_line, best.end_line)
        # contexto cirúrgico: função alvo + assinaturas das vizinhas + imports
        prompt_context = build_surgical_context(
            target_path, best, max_snippet_lines=80
        )
        max_tokens = estimate_tokens(snippet) * 2  # folga para o diff
        raw = _infer(build_prompt(prompt_context, instruction), max_tokens)
    else:
        # fallback: fluxo atual (arquivo todo) com max_tokens=1024
        raw = _infer(build_prompt(content, instruction), 1024)

    hunks = parse_diff(raw, original_content=content)
    ...
```

### 5.6 Faseamento

| Fase | Escopo | Estimativa | Critério de aceite |
|---|---|---|---|
| **F5.1** | `symbol_indexer` + `symbol_resolver` (sem dep_graph) | 1 sessão | `orn fix arq.py -i "melhore session_cmd"` acha `session_cmd` |
| **F5.2** | `dep_graph` + contexto de vizinhanças | 1 sessão | prompt inclui imports usados pela função-alvo |
| **F5.3** | Cache de índice em `data/symbol_cache.json` | 0.5 sessão | segunda execução não re-parseia |
| **F5.4** | Comando CLI `orn grep <símbolo>` | 0.5 sessão | listar arquivos/linhas de um símbolo |
| **F5.5** | `_run_audit` também usa resolver | 1 sessão | `orn audit arq.py -f session_cmd` foca cirurgicamente |

### 5.7 Ganhos esperados no N2808

| Métrica | Hoje (`cli.py` inteiro) | Com F5.1+ |
|---|---|---|
| Prompt tokens | ~12.000 | ~800 |
| Prompt eval | ~8s | ~0.5s |
| Geração (256 tokens) | ~180s | ~180s (não muda) |
| Probabilidade de truncamento | Alta (B-003) | Baixa |
| Precisão do patch | Baixa | Alta |

**Atenção:** geração é o gargalo dominante (1.4 t/s), então o ganho
principal é **qualidade do patch**, não velocidade. Mas o tempo de
`prompt_eval` cai drasticamente e o patch fica cirúrgico.

### 5.8 Decisões em aberto

1. **Cache de índice:** persistir como JSON em `data/symbol_cache.json`
   ou reconstruir on-demand? (recomendo cache com mtime para invalidação)
2. **Resolução de ambiguidade:** se `session_cmd` aparece em dois arquivos,
   preferir o `scope` passado? Perguntar ao usuário? (recomendo preferir
   scope, com fallback a erro explícito)
3. **Docstring matching:** vale indexar docstrings e usar como sinal
   secundário? (recomendo sim, custo baixo)
4. **Integração com `orn gen`:** o resolver pode ser usado em `orn gen`
   para "gere código que combine com X"? (fora do escopo da F5)

---

## 6. Pendências desta sessão

- [ ] Corrigir B-001 e B-002 (parser de session) — **quick fix, 15min**
- [ ] Corrigir B-003 (max_tokens adaptativo) — **quick fix, 10min**
- [ ] Validar B-004 (raw_output_override) — **pendente do relatório anterior**
- [ ] Rodar `orn fix teste_fix.py -i "..."` e verificar `type teste_fix.py`
- [ ] `doxoade save "Fase 4 stable — fix e session validados"` (após fixes)
- [ ] Iniciar F5.1 (symbol_indexer) em sessão dedicada

---

## 7. Referências

- `docs/History/vol3_atualizacoes_0300.md` (Fase 3 — brain)
- Relatório anterior: `orn fix` dry-run vs. apply (raw_output_override)
- `engine/diff/format.py` — parser de hunks (já robusto)
- `engine/diff/surgeon.py` — aplicador com preflight (já robusto)
- `docs/Protocols/OSL.md` — OSL-17 (responsabilidade única do resolver)

---

### Limitação conhecida — Fase 5

`orn fix` só aplica patches no formato:
  - @N + linhas -/+ (line-hunk)
  - [SEARCH]/[REPLACE]/[END]
  - Substituição de FunctionDef/ClassDef inteira (AST)

Casos não suportados pelo parser atual:
  - "adicionar código ao final do arquivo" (sem função-alvo)
  - "renomear variável" (sem contexto de hunk)
  - "extrair módulo" (multi-arquivo)
  - instruções vagas que não geram `@N` nem `def`/`class`

Solução proposta (F5.2 / F5.3):
  1. `parse_diff` retornar `fallback_candidate: str | None` quando o raw
     é Python sintaticamente válido mas sem hunk
  2. CLI pergunta: "Modelo devolveu código sem alvo. [A]dicionar ao final /
     [S]ubstituir inteiro / [C]ancelar?"
  3. Só aceita se confirmação explícita (segurança)
