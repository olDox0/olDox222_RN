# ORN — Pipeline Workflow
**CR:** 2026.02.19 | **AT:** 2026.02.19

---

## Pipeline MVP: orn think

Descricao passo-a-passo do fluxo completo do comando think (Fase 1, ATIVO).

  ENTRADA: orn think "como funciona KV-cache?" [--file contexto.py]
      |
      v
  [cli.py / think()]
    - Junta args em full_prompt
    - Display.banner() + Display.thinking(full_prompt)
    - Instancia SiCDoxExecutive
      |
      v
  [executive._run_think(payload, context)]
    - Verifica context["context_file"]:
        Se presente -> _read_file_safe(path, max_chars=3000)
        Monta full_prompt com [CONTEXTO DO ARQUIVO] + [PERGUNTA]
    - Chama _get_bridge() (lazy load SiCDoxBridge)
      |
      v
  [bridge.ask(full_prompt)]
    - Valida prompt nao-vazio (ValueError se vazio)
    - _ensure_loaded() -> _load() se _llm is None:
        Verifica model_path.exists() (FileNotFoundError se ausente)
        Llama(model_path, n_ctx=2048, n_threads=4, n_gpu_layers=0, verbose=False)
    - ctx.push("user", full_prompt)
    - _build_prompt() -> ChatML com system_prompt + janela ativa
    - _call_engine(prompt, max_tokens=512):
        llm(prompt, stop=["<|im_end|>","</s>"], echo=False)
        Retorna output["choices"][0]["text"]
    - Valida resposta nao-vazia (RuntimeError se vazia)
    - ctx.push("assistant", texto)
    - Retorna texto
      |
      v
  [validator.validar_output(output)]
    - Verifica que e string (nao None)
    - Verifica que nao e whitespace
    - Se lang="python": ast.parse() (Fase 2+)
    - Retorna (True, "") ou (False, motivo)
      |
      v
  [board.post_hypothesis("think", resumo, confidence=1.0)]
      |
      v
  [GoalResult(success=True, intent="think", output=texto, metadata={elapsed_s})]
      |
      v
  [cli.py]
    - Se result.success: Display.code_block(result.output)
    - Se nao: Display.error(err) + sys.exit(1)
    - Display.info(f"Tempo: {elapsed_s}s")
    - executive.shutdown()  <- OSL-3: liberacao deterministica

---

## Controle de Erros no Pipeline

  Origem              Tipo                  Tratamento
  ------------------- --------------------- ----------------------------------
  prompt vazio        ValueError            GoalResult(success=False)
  modelo ausente      FileNotFoundError     GoalResult(success=False) + mensagem
  resposta vazia      RuntimeError          GoalResult(success=False)
  output invalido     validar_output False  GoalResult(success=False) + motivo
  excecao inesperada  Exception             GoalResult(success=False, [ERRO INTERNO])

Nenhuma excecao propaga para a CLI como traceback nao tratado (OSL-15).

---

## Pipeline Fase 2: orn audit (planejado)

  ENTRADA: orn audit main.py [--func nome_funcao]
      |
      v
  [ConceptMapper.internalizar(file_path)]
    - ast.parse(source)
    - _walk(node) -> grafo de conceitos
    - Retorna dict com nos, relacoes, funcoes, classes
      |
      v
  [Executive._run_audit()]
    - Monta prompt estruturado com resumo do grafo
    - Atlas.summary() -> contexto do atlas para o LLM
    - Bridge.ask(prompt_de_auditoria)
    - Validator.validar_output(output)
    - Retorna GoalResult com relatorio textual
      |
      v
  [cli.py / audit()]
    - Display.lista("Problemas encontrados", issues)
    - Se output_format="json": print(json.dumps(result.metadata))

---

## Pipeline Fase 4: orn fix (planejado)

  ENTRADA: orn fix buggy.py [--apply]
      |
      v
  [_run_audit() -- auditoria completa]
      |
      v
  [Bridge.ask(prompt_de_correcao)]
    - Prompt inclui codigo original + problemas encontrados
    - Solicita patch especifico
      |
      v
  [Validator._validar_python(codigo_sugerido)]
    - ast.parse() obrigatorio para --apply
      |
      v
  [Se --apply]:
    - Backup automatico do arquivo original
    - Escreve correcao no arquivo
    - Display.success("Patch aplicado")
  [Se nao --apply]:
    - Display.code_block(patch_sugerido, lang="python")

---

## Politica de Memoria no Pipeline

Baseada no Relatorio de Prototipo (KV-cache como vilao silencioso):

  - Modelo carregado uma vez por sessao (lazy, na primeira chamada)
  - ContextWindow sliding window: turns antigos descartados automaticamente
  - Estimativa: palavras ~= tokens (Fase 1); tokenizer real na Fase 2
  - Limite ativo: 1024 tokens (active_window)
  - Janela total: 2048 (n_ctx, metade do maximo do modelo)
  - Contexto de arquivo: max 3000 chars antes da injecao no prompt
  - Shutdown por TTL: Executive chama bridge.shutdown() apos 300s inatividade
  - ContextWindow preservada apos shutdown (sessao retomavel)