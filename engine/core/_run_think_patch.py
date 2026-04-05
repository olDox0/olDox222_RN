# -*- coding: utf-8 -*-
"""
ORN — _run_think_patch.py
Trecho reformado de executive.py — SiCDoxExecutive.
Substitui _run_think() e adiciona _decompose_query().

Diferenças em relação à versão anterior:
  - Blackboard NÃO recebe histórico de Q&A.
  - Blackboard abre sessão ANTES da inferência e fecha DEPOIS.
  - _decompose_query() popula a lousa com rascunhos de raciocínio
    baseados em regras simples (sem chamada extra ao LLM).
  - board.build_synthesis_block() substitui board.build_context_block().

Alterações nesta revisão:
  - _decompose_query() completa: todos os branches de tipo de tarefa.
  - Detecção de linguagem movida para constante de módulo (_LANG_KEYWORDS).
  - Adicionados: geração de código, debug/correção, lista, comparação.
  - draft de formato (role="format") emitido quando linguagem é detectada.
  - draft de escopo do arquivo (role="evidence") quando --file é fornecido.
  - Hint de max_tokens injetado no context por tipo de tarefa.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.core.blackboard import DoxoBoard
    from engine.core.executive  import GoalResult


# ---------------------------------------------------------------------------
# Constantes de detecção — definidas no módulo, não dentro da função
# ---------------------------------------------------------------------------

# Linguagens: keyword (lowercase) → nome canônico para o draft
_LANG_KEYWORDS: dict[str, str] = {
    "python":   "Python",
    "py ":      "Python",
    ".py":      "Python",
    "c++":      "C++",
    "cpp":      "C++",
    " c ":      "C",
    "em c,":    "C",
    "em c.":    "C",
    "em c:":    "C",
    "batch":    "Batch Script",
    "bat ":     "Batch Script",
    ".bat":     "Batch Script",
    ".cmd":     "Batch Script",
}

# Tipo de tarefa: conjunto de keywords por intenção
_KW_EXPLAIN  = frozenset({
    "explique", "explica", "o que é", "o que sao", "como funciona",
    "como funcionam", "define", "definir", "definição", "me diga",
    "me conte", "descreva", "descrever",
})
_KW_CODEGEN  = frozenset({
    "escreva", "escrever", "crie", "criar", "gere", "gerar",
    "implemente", "implementar", "codifique", "codificar",
    "faça", "fazer", "construa", "construir", "monte", "montar",
    "desenvolva", "desenvolver",
})
_KW_DEBUG    = frozenset({
    "debug", "debugar", "debugue", "erro", "erros", "bug", "bugs",
    "falha", "crash", "corrige", "corrigir", "corrija", "conserta",
    "consertar", "conserte", "fix", "problema", "não funciona",
    "nao funciona", "não está", "nao esta",
})
_KW_LIST     = frozenset({
    "liste", "listar", "liste", "enumere", "enumerar",
    "quais são", "quais sao", "quais os", "quais as",
    "mostre os", "mostre as", "dê exemplos", "de exemplos",
    "exemplos de",
})
_KW_COMPARE  = frozenset({
    "compare", "comparar", "diferença", "diferenca", "diferenças",
    "diferencas", "vantagem", "desvantagem", "melhor", "pior",
    "versus", " vs ", " vs.", "qual a diferença", "quando usar",
})


# ---------------------------------------------------------------------------
# MVP — think (Fase 1) — versão reformada
# ---------------------------------------------------------------------------

def _run_think(self, prompt: str, context: dict) -> "GoalResult":
    """Pipeline completo do comando `orn think`."""
    bridge    = self._get_bridge()
    validator = self._get_validator()
    board     = self._get_board()

    board.open_session(prompt)

    try:
        # 1. HERMES: Interceptação Autônoma (Gaveteiro Fast-Track)
        # O sistema verifica se já conhece esse algoritmo ANTES de acordar a IA.
        router = self._get_drawer_router()
        if router:
            print("\n  [Hermes] 🔍 Consultando memória de longo prazo...")
            r_res = router.route(prompt, board)
            if r_res.hit:
                # SUCESSO! Código perfeito encontrado. Corta o LLM e devolve em 0 segundos.
                return GoalResult(
                    success=True,
                    intent="think",
                    output=f"📦[HERMES FAST-TRACK] Conhecimento resgatado da memória!\n\n```python\n{r_res.code}\n```"
                )

        # 2. Popula lousa com rascunhos de raciocínio (IA Padrão)
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
        synthesis = board.build_synthesis_block()
        if synthesis:
            full_prompt = f"{synthesis}[TASK]\n{prompt}"
        else:
            full_prompt = prompt

        # 5. Inferência Pesada
        max_tokens = context.get("max_tokens")
        output = bridge.ask(full_prompt, max_tokens=max_tokens)

        # 6. Hook de Código (Argos / Sandbox)
        try:
            from engine.thinking.code_hook import apply_code_hook
            output = apply_code_hook(
                output=output,
                task=prompt,
                bridge=bridge,
                validator=validator,
                max_retries=1,
                run_isolated=True
            )
        except Exception as e:
            output += f"\n\n[AVISO] CodeHook falhou: {e}"

        # 7. Validação final
        valid, motivo = validator.validar_output(output)
        if not valid:
            return GoalResult(success=False, intent="think", errors=[motivo])

        return GoalResult(success=True, intent="think", output=output)

    finally:
        board.close_session()


# ---------------------------------------------------------------------------
# Decompositor de query — popula lousa sem chamar o LLM
# ---------------------------------------------------------------------------

def _decompose_query(board: "DoxoBoard", prompt: str, context: dict) -> None:
    """Preenche a lousa com rascunhos de raciocínio baseados em regras.

    Objetivo: orientar o modelo sobre o que é esperado,
    sem consumir tokens extras de inferência.

    Regras (em ordem de prioridade de detecção):
      1. Constraint de idioma + brevidade  — sempre emitido.
      2. Detecção de linguagem de programação → constraint + format.
      3. Tipo de tarefa (exclusivo, primeiro match vence):
           a. Explicação  → clareza sobre completude.
           b. Geração     → apenas código, sem texto extra.
           c. Debug       → diagnosticar causa + solução mínima.
           d. Lista       → formato de lista numerada.
           e. Comparação  → tabela ou lista de pontos, prós/contras.
      4. Escopo de arquivo  — se --file fornecido no context.

    Args:
        board:   Lousa com sessão aberta.
        prompt:  Query original do usuário.
        context: Dict de contexto do Executive (vindo do CLI).
    """
    p = prompt.lower()

    # ------------------------------------------------------------------
    # 1. Constraint de idioma e brevidade (sempre — peso máximo)
    # ------------------------------------------------------------------
    board.post_draft(
        source  = "decomposer",
        content = "Responda em português, de forma concisa e direta.",
        role    = "constraint",
        weight  = 1.0,
    )

    # ------------------------------------------------------------------
    # 2. Detecção de linguagem de programação
    # ------------------------------------------------------------------
    detected_lang: str | None = None
    for kw, lang in _LANG_KEYWORDS.items():
        if kw in p:
            detected_lang = lang
            board.post_draft(
                source  = "decomposer",
                content = f"Código esperado em: {lang}.",
                role    = "constraint",
                weight  = 0.95,
            )
            break  # uma linguagem por vez

    # ------------------------------------------------------------------
    # 3. Tipo de tarefa (primeiro branch que bater vence)
    # ------------------------------------------------------------------

    if any(kw in p for kw in _KW_EXPLAIN):
        # Explicação: priorizar clareza, analogias permitidas
        board.post_draft(
            source  = "decomposer",
            content = "Tarefa: explicação. Priorize clareza sobre completude.",
            role    = "decomp",
            weight  = 0.85,
        )
        board.post_draft(
            source  = "decomposer",
            content = "Use exemplos práticos se ajudar a entender.",
            role    = "angle",
            weight  = 0.70,
        )

    elif any(kw in p for kw in _KW_CODEGEN):
        # Geração de código: só código, sem explicação em torno
        board.post_draft(
            source  = "decomposer",
            content = "Tarefa: geração de código. Retorne apenas o código pedido.",
            role    = "decomp",
            weight  = 0.85,
        )
        board.post_draft(
            source  = "decomposer",
            content = "Sem texto antes ou depois do bloco de código.",
            role    = "constraint",
            weight  = 0.80,
        )
        if detected_lang:
            board.post_draft(
                source  = "decomposer",
                content = f"Envolva o código em bloco markdown ```{detected_lang.lower()}.",
                role    = "format",
                weight  = 0.75,
            )

    elif any(kw in p for kw in _KW_DEBUG):
        # Debug/correção: diagnóstico + solução mínima
        board.post_draft(
            source  = "decomposer",
            content = "Tarefa: diagnóstico de erro. Identifique a causa raiz.",
            role    = "decomp",
            weight  = 0.85,
        )
        board.post_draft(
            source  = "decomposer",
            content = "Mostre a correção mínima necessária, sem refatorar o resto.",
            role    = "constraint",
            weight  = 0.80,
        )

    elif any(kw in p for kw in _KW_LIST):
        # Lista: formato numerado, itens curtos
        board.post_draft(
            source  = "decomposer",
            content = "Tarefa: listar itens. Use lista numerada.",
            role    = "decomp",
            weight  = 0.85,
        )
        board.post_draft(
            source  = "decomposer",
            content = "Cada item em uma linha. Sem parágrafos longos.",
            role    = "format",
            weight  = 0.75,
        )

    elif any(kw in p for kw in _KW_COMPARE):
        # Comparação: pontos lado a lado, prós e contras
        board.post_draft(
            source  = "decomposer",
            content = "Tarefa: comparação. Apresente prós e contras de cada opção.",
            role    = "decomp",
            weight  = 0.85,
        )
        board.post_draft(
            source  = "decomposer",
            content = "Use lista ou tabela curta. Conclua com uma recomendação direta.",
            role    = "format",
            weight  = 0.75,
        )

    # ------------------------------------------------------------------
    # 4. Formato de código genérico (linguagem detectada, tarefa não é
    #    geração pura — ex.: "explique em Python como funciona X")
    # ------------------------------------------------------------------
    if detected_lang and not any(kw in p for kw in _KW_CODEGEN):
        board.post_draft(
            source  = "decomposer",
            content = f"Se incluir código, use bloco markdown ```{detected_lang.lower()}.",
            role    = "format",
            weight  = 0.65,
        )

    # ------------------------------------------------------------------
    # 5. Escopo de arquivo (--file fornecido, antes do context_file do
    #    _run_think — aqui só anunciamos o escopo, o conteúdo vem depois)
    # ------------------------------------------------------------------
    if context.get("context_file"):
        board.post_draft(
            source  = "decomposer",
            content = f"Contexto baseado no arquivo: {context['context_file']}.",
            role    = "evidence",
            weight  = 0.90,
        )