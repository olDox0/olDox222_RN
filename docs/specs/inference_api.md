# ORN — Inference API Specification
**CR:** 2026.02.19 | **AT:** 2026.02.19

---

## Visao Geral

A API de inferencia do ORN e interna -- nao expoe HTTP.
O ponto de entrada e SiCDoxBridge.ask(), chamado exclusivamente
pelo Executive. Nenhum outro modulo chama o bridge diretamente (OSL-17).

---

## SiCDoxBridge.ask()

  Assinatura:
    ask(prompt: str, max_tokens: int | None = None) -> str

  Pre-condicoes (OSL-5.1):
    prompt nao pode ser vazio -> ValueError

  Pos-condicoes (OSL-7):
    Retorno e string nao-vazia -> RuntimeError se vazio

  Efeitos colaterais:
    ctx.push("user", prompt)
    ctx.push("assistant", texto)

  Raises:
    ValueError         prompt vazio
    RuntimeError       resposta vazia do modelo
    FileNotFoundError  modelo .gguf nao encontrado
    NotImplementedError se _load() ainda e stub (pre-Fase 1)

---

## Formato do Prompt (ChatML Qwen)

  <|im_start|>system
  {system_prompt}
  <|im_end|>
  <|im_start|>user
  {conteudo_da_mensagem}
  <|im_end|>
  <|im_start|>assistant

  Stop tokens: ["<|im_end|>", "</s>"]
  echo: False

---

## Parametros de Chamada llama-cpp-python

  model_path    str   caminho absoluto ou relativo do .gguf
  n_ctx         int   janela de contexto total (2048 default)
  n_threads     int   threads CPU (4 default)
  n_gpu_layers  int   camadas na GPU (0 = CPU-only)
  verbose       bool  False (silencia output interno)
  max_tokens    int   limite da resposta (512 default)
  stop          list  tokens de parada do ChatML Qwen

---

## ContextWindow API

Gerencia o historico para o KV-cache sliding window.

  push(role, content):
    role: "user" | "assistant" | "system"
    Descarta turns antigos se token_est > max_tokens

  get_turns() -> list[dict]:
    Retorna copia da janela ativa

  clear():
    Limpa historico sem descarregar modelo

  stats() -> dict:
    { "turns": int, "token_est": int, "max_tokens": int }

---

## Limites e Politica de Memoria

  n_ctx           2048    janela total do KV-cache
  active_window   1024    tokens ativos na sliding window (50% do n_ctx)
  max_tokens       512    resposta maxima por chamada (25% do n_ctx)
  max_chars       3000    limite de contexto de arquivo injetado

  Regra de proporcao recomendada:
    active_window = n_ctx / 2
    max_tokens    = n_ctx / 4

---

## Extensao: generate_plan() -- Fase 4

  Assinatura planejada:
    generate_plan(user_intent: str, context_graph_snippet: str) -> str

  Descricao:
    Gera uma Meta-Acao harmonizada com o estado atual do Grafo TGF.
    Usa o grafo de conceitos do ConceptMapper como contexto.

  Prompt montado:
    CONTEXTO ATUAL (TGF):
    {context_graph_snippet}

    INTENCAO DO ARQUITETO: {user_intent}

  Fonte: archaeology layer llm_bridge.py (2026-02-01, layer 1)