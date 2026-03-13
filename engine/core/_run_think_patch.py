# -*- coding: utf-8 -*-
"""
Trecho reformado de executive.py — SiCDoxExecutive.
Substitui _run_think() e adiciona _decompose_query().

Diferenças em relação à versão anterior:
  - Blackboard NÃO recebe histórico de Q&A.
  - Blackboard abre sessão ANTES da inferência e fecha DEPOIS.
  - _decompose_query() popula a lousa com rascunhos de raciocínio
    baseados em regras simples (sem chamada extra ao LLM).
  - board.build_synthesis_block() substitui board.build_context_block().
"""

# ------------------------------------------------------------------
# MVP — think (Fase 1) — versão reformada
# ------------------------------------------------------------------

def _run_think(self, prompt: str, context: dict) -> "GoalResult":
    """Pipeline completo do comando `orn think`.

    Etapas:
      1. Abre sessão no Blackboard (workspace limpo).
      2. Decompõe a query em rascunhos de raciocínio (regra-based).
      3. Injeta contexto de arquivo opcional (--file).
      4. Constrói prompt final = synthesis_block + task.
      5. Chama Bridge.ask().
      6. Valida output via Validator.
      7. Fecha sessão do Blackboard (descarta rascunhos).

    OSL-7: sessão fechada mesmo em caso de erro (finally).
    """
    bridge    = self._get_bridge()
    validator = self._get_validator()
    board     = self._get_board()

    # 1. Abre workspace limpo para esta query
    board.open_session(prompt)

    try:
        # 2. Popula lousa com rascunhos de raciocínio
        _decompose_query(board, prompt, context)

        # 3. Contexto de arquivo opcional (--file)
        if context.get("context_file"):
            file_content = _read_file_safe(context["context_file"])
            if file_content:
                board.post_draft(
                    source  = "context_file",
                    content = f"Arquivo '{context['context_file']}': {file_content[:120]}",
                    role    = "evidence",
                    weight  = 0.95,
                )

        # 4. Monta prompt final
        #    synthesis_block orienta o modelo; [TASK] é a query real.
        synthesis = board.build_synthesis_block()
        if synthesis:
            full_prompt = f"{synthesis}[TASK]\n{prompt}"
        else:
            full_prompt = prompt

        # 5. Inferência
        max_tokens = context.get("max_tokens")
        output = bridge.ask(full_prompt, max_tokens=max_tokens)

        # 6. Validação (OSL-7)
        valid, motivo = validator.validar_output(output)
        if not valid:
            return GoalResult(
                success=False, intent="think",
                errors=[f"Output inválido: {motivo}"],
            )

        return GoalResult(success=True, intent="think", output=output)

    finally:
        # 7. OSL-3: descarta workspace — sem acúmulo entre queries
        board.close_session()


# ------------------------------------------------------------------
# Decompositor de query — popula lousa sem chamar o LLM
# ------------------------------------------------------------------

def _decompose_query(board: "DoxoBoard", prompt: str, context: dict) -> None:
    """Preenche a lousa com rascunhos de raciocínio baseados em regras.

    Objetivo: orientar o modelo sobre o que é esperado,
    sem consumir tokens extras de inferência.

    Regras implementadas (extensíveis):
      - Detecta pedido de código → constraint de linguagem.
      - Detecta pedido de explicação → constraint de profundidade.
      - Detecta pedido de lista → format de lista numerada.
      - Injeta constraint de idioma (português, conciso).
      - Injeta scope do arquivo se fornecido.

    Args:
        board:   Lousa com sessão aberta.
        prompt:  Query original do usuário.
        context: Dict de contexto do Executive.
    """
    p = prompt.lower()

    # --- Constraint de idioma e tamanho (sempre) ---
    board.post_draft(
        source  = "decomposer",
        content = "Responda em português, de forma concisa e direta.",
        role    = "constraint",
        weight  = 1.0,
    )

    # --- Detecção de linguagem de programação ---
    _LANG_KEYWORDS: dict[str, str] = {
        "python": "python", "py ": "python",
        "c++": "c++", "cpp": "c++",
        " c ": "C", "em c,": "C", "em c.": "C",
        "batch": "batch script", "bat ": "batch script",
    }
    for kw, lang in _LANG_KEYWORDS.items():
        if kw in p:
            board.post_draft(
                source  = "decomposer",
                content = f"Código esperado em: {lang}.",
                role    = "constraint",
                weight  = 0.95,
            )
            break   # uma linguagem por vez

    # --- Tipo de tarefa ---
    if any(kw in p for kw in ("explique", "explica", "o que é", "como funciona", "define")):
        board.post_draft(
            source  = "decomposer",
            content = "Tarefa: explicação. Priorize clareza sobre completude.",
            role    = "decomp",
            weight  = 0.85,
        )
    elif any(kw in p for kw in ("crie", "escreva", "gere", "implemente", "faça", "cria")):
        board.post_draft(
            source  = "decomposer",
            content = "Tarefa: geração. Produza o artefato solicitado, sem prolixidade.",
            role    = "decomp",
            weight  = 0.85,
        )
    elif any(kw in p for kw in ("corrija", "conserte", "bug", "erro", "fix", "problema")):
        board.post_draft(
            source  = "decomposer",
            content = "Tarefa: correção. Identifique a causa e forneça o fix.",
            role    = "decomp",
            weight  = 0.85,
        )
    elif any(kw in p for kw in ("liste", "quais são", "enumere", "mostre os")):
        board.post_draft(
            source  = "decomposer",
            content = "Formato esperado: lista numerada, itens curtos.",
            role    = "format",
            weight  = 0.8,
        )

    # --- Escopo de arquivo (se --file fornecido) ---
    if context.get("context_file"):
        board.post_draft(
            source  = "decomposer",
            content = f"Resposta deve se referir ao arquivo: {context['context_file']}",
            role    = "angle",
            weight  = 0.9,
        )