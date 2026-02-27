# ORN — Core Architecture
**CR:** 2026.02.19 | **AT:** 2026.02.19

---

## engine/core/ — Modulos Centrais

Estes modulos sao carregados pelo Executive sob demanda (lazy loading, OSL-3).
Nenhum modulo de core importa de engine/tools/, engine/memory/ ou engine/ui/
diretamente -- toda comunicacao passa pelo Executive (OSL-17).

---

## SiCDoxExecutive (Zeus) — executive.py

Orquestrador central. Recebe goals da CLI e despacha para os modulos certos.

Responsabilidades:
  - Validar intent e payload (OSL-5.1)
  - Rotear para _run_think / _run_audit / _run_fix / _run_gen / _run_brain / _run_graph
  - Capturar excecoes internas e retornar GoalResult gracioso (OSL-15)
  - Carregar modulos filhos via _get_*() lazy loaders
  - Expor bridge_stats() para orn brain (OSL-12)

GoalResult (contrato de saida, OSL-7):
  success:  bool         -- True se pipeline completou sem erros criticos
  intent:   str          -- intent original recebido
  output:   str          -- texto gerado (resposta, codigo, analise)
  errors:   list[str]    -- erros nao-fatais do pipeline
  metadata: dict         -- elapsed_s, tokens estimados, etc

_run_think() (Fase 1 -- ATIVO):
  1. Injeta contexto de arquivo (--file, max 3000 chars, OSL-3)
  2. Bridge.ask(full_prompt)
  3. Validator.validar_output(output)
  4. Board.post_hypothesis(...)
  5. Retorna GoalResult

_run_audit(), _run_fix(), _run_gen(), _run_brain(), _run_graph():
  Stubs com NotImplementedError descritivo -- Fases 2-4.

---

## SiCDoxBridge (Hefesto) — llm_bridge.py

Interface com o modelo GGUF. Implementa a politica de memoria do relatorio
de prototipo: modelo e servico, nao dependencia.

BridgeConfig (parametros de memoria):
  model_path      Path    modelos/sicdox/Qwen2.5-Coder-0.5B.../
  n_ctx           2048    janela total do KV-cache (conservador)
  active_window   1024    tokens ativos na sliding window
  max_tokens      512     resposta maxima por chamada
  n_threads       4       CPU threads (desktop-safe)
  n_gpu_layers    0       CPU-only; aumentar se VRAM disponivel
  ttl_seconds     300     Executive chama shutdown() apos inatividade
  system_prompt   str     identidade e instrucoes do ORN

ContextWindow (sliding window, OSL-2):
  - push(role, content): adiciona mensagem, descarta turns antigos se necessario
  - Estimativa de tokens por palavras (Fase 1); tokenizer real na Fase 2
  - get_turns(): retorna copia -- nao expoe referencia interna (OSL-6)
  - clear(): limpa historico sem descarregar o modelo
  - stats(): para telemetria (OSL-12)

ask(prompt) -> str:
  1. Valida prompt nao-vazio (OSL-5.1)
  2. _ensure_loaded() -> _load() se necessario
  3. ctx.push("user", prompt)
  4. _build_prompt() -> ChatML com janela ativa
  5. _call_engine(prompt, max_tokens)
  6. Verifica resposta nao-vazia (OSL-7)
  7. ctx.push("assistant", texto)
  8. Retorna texto

_build_prompt() -- formato ChatML Qwen:
  <|im_start|>system\n{system_prompt}<|im_end|>
  <|im_start|>user\n{content}<|im_end|>
  <|im_start|>assistant\n

shutdown(): libera _llm = None. Idempotente. ContextWindow preservada.

ARCHAEOLOGY NOTE (2026-02-01):
  Recuperar generate_plan() na Fase 4:
    def generate_plan(self, user_intent, context_graph_snippet):
        prompt = f'CONTEXTO ATUAL (TGF):\n{context_graph_snippet}\n\n'
                 f'INTENCAO DO ARQUITETO: {user_intent}'
        return self._call_engine(self._build_prompt(), self._cfg.max_tokens)

---

## DoxoBoard (Hades) — blackboard.py

Memoria de hipoteses e links causais da sessao atual.

  post_hypothesis(source, content, confidence): registra hipotese
  add_causal_link(causa, efeito): registra relacao causal
  get_summary() -> dict: estado serializavel (OSL-6: retorna copia)
  clear(): limpa blackboard (usado por orn brain --clear)

---

## SiCDoxValidator (Anubis) — logic_filter.py

Valida todo output do LLM antes de chegar ao usuario.

  validar_output(output, lang=None) -> (bool, str):
    - output vazio ou whitespace -> (False, motivo)
    - lang="python" -> ast.parse() (OSL-18: stdlib)
    - retorna (True, "") se valido

---

## Atlas (Thoth) — atlas.py

Singleton. Carrega doxoade_atlas.json (mapa de conceitos AST -> IDs).
Usado pelo ConceptMapper para classificar nos do AST.

  Atlas.load(path) -> Atlas
  get(key, default) -> Any
  summary() -> str  (para injecao em prompts)