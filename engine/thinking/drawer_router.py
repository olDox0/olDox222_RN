# -*- coding: utf-8 -*-
"""
ORN — DrawerRouter (Hermes)
Fase pré-LLM: tenta montar o código a partir de snippets existentes no
CodeDrawer antes de acionar a inferência completa.

Filosofia:
  Se o código já existe → monta, testa, encaixa na lousa.
  Se não existe         → cai no fluxo LLM normal (sem custo extra).

Fluxo:
    route(prompt, board)
        ├─ _extract_intent()     → nome canônico + io hints
        ├─ CodeDrawer.assemble() → snippet candidato (ou None)
        ├─ sandbox diagnose      → issues
        ├─ se issues → _fix_io()  → ajuste mínimo de I/O (sem regerar tudo)
        └─ board.post_draft()    → injeta código como evidência pesada
        └─ retorna RouteResult(hit, code, max_tokens_hint)

OSL-3:  CodeDrawer e sandbox importados lazy.
OSL-4:  Cada método faz uma coisa.
OSL-7:  route() sempre retorna RouteResult — nunca levanta exceção.
OSL-15: Falha silenciosa — pipeline continua normalmente se router falhar.
OSL-18: stdlib only neste módulo.
God: Hermes — mensageiro rápido; entrega o código antes do LLM acordar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engine.core.blackboard import DoxoBoard


# ---------------------------------------------------------------------------
# Resultado do roteamento
# ---------------------------------------------------------------------------

@dataclass
class RouteResult:
    """Resultado de DrawerRouter.route().

    Attributes:
        hit:            True se snippet foi encontrado e passou no sandbox.
        code:           Código pronto (vazio se hit=False).
        max_tokens_hint: Sugestão de max_tokens para o bridge.ask() subsequente.
                         Se hit=True, só precisamos de explicação → 64 tokens.
                         Se hit=False, geração completa → valor original.
        attempts:       Quantas tentativas de fix foram necessárias.
        issues:         Issues remanescentes após fix (vazio = ok).
    """
    hit: bool
    code: str = ""
    max_tokens_hint: int | None = None
    attempts: int = 0
    issues: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extração de intent (regex puro — zero custo)
# ---------------------------------------------------------------------------

# Padrões de geração em PT/EN
_KW_GEN = re.compile(
    r"\b(fa[çc]a|cri[ae]|escreva|gere|implemente|make|write|implement|create|build)\b",
    re.IGNORECASE,
)

# Nomes canônicos de algoritmos / patterns conhecidos pelo CodeDrawer
_ALGO_MAP: tuple[tuple[str, str], ...] = (
    (r"\bquicksort\b",               "quicksort"),
    (r"\bmergesort\b",               "mergesort"),
    (r"\bbubble.?sort\b",            "bubblesort"),
    (r"\bfibonacci\b",               "fibonacci"),
    (r"\bbinary.?search\b",          "binary_search"),
    (r"\bring.?buffer\b|ringbuffer", "ring_buffer"),
    (r"\bstack\b",                   "stack"),
    (r"\bqueue\b",                   "queue"),
    (r"\blinked.?list\b",            "linked_list"),
    (r"\bbst\b|binary.?search.?tree","bst"),
    (r"\bhash.?map\b|hashmap",       "hash_map"),
    (r"\bfactory\b",                 "factory"),
    (r"\bsingleton\b",               "singleton"),
    (r"\bdecorator\b",               "decorator"),
    (r"\blru.?cache\b",              "lru_cache"),
)

# Dicas de I/O a partir de palavras no prompt
_IO_HINTS: tuple[tuple[str, str, str], ...] = (
    # (padrão, tipo_io, nome_hint)
    (r"\barr(?:ay)?\b|lista",   "input",  "arr"),
    (r"\bn\b|\bnum(?:ero)?\b",  "input",  "n"),
    (r"\bstring\b|str\b",       "input",  "s"),
    (r"\bsorted\b|ordenad",     "output", "sorted_arr"),
    (r"\bresult(?:ado)?\b",     "output", "result"),
    (r"\bsequen[çc]",           "output", "sequence"),
)

_LANG_MAP: tuple[tuple[str, str], ...] = (
    (r"\bpython\b|\bpy\b",      "python"),
    (r"\bc\+\+\b|\bcpp\b",      "c++"),
    (r"\bc\b",                  "C"),
    (r"\bbatch\b|\bbat\b",      "batch"),
)


def _extract_intent(prompt: str) -> tuple[str | None, str, list[str], list[str]]:
    """Extrai (nome_canônico, lang, inputs, outputs) do prompt.

    Returns:
        (name, lang, inputs, outputs)
        name=None se nenhum algoritmo reconhecido.
    """
    p = prompt.lower()

    # Verifica se é uma pergunta de geração (senão não há o que montar)
    if not _KW_GEN.search(p):
        return None, "python", [], []

    # Nome canônico
    name: str | None = None
    for pattern, canonical in _ALGO_MAP:
        if re.search(pattern, p, re.IGNORECASE):
            name = canonical
            break

    # Linguagem
    lang = "python"
    for pattern, detected_lang in _LANG_MAP:
        if re.search(pattern, p, re.IGNORECASE):
            lang = detected_lang
            break

    # I/O hints
    inputs: list[str] = []
    outputs: list[str] = []
    for pattern, io_type, hint in _IO_HINTS:
        if re.search(pattern, p, re.IGNORECASE):
            if io_type == "input":
                inputs.append(hint)
            else:
                outputs.append(hint)

    return name, lang, inputs, outputs


# ---------------------------------------------------------------------------
# DrawerRouter
# ---------------------------------------------------------------------------

class DrawerRouter:
    """Roteador pré-LLM: CodeDrawer → sandbox → lousa.

    Args:
        max_fix_attempts: Tentativas de fix de I/O antes de desistir.
    """

    def __init__(self, max_fix_attempts: int = 1) -> None:
        self._max_fix = max(0, int(max_fix_attempts))

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def route(
        self,
        prompt: str,
        board: "DoxoBoard | None" = None,
        lang_override: str | None = None,
    ) -> RouteResult:
        """Tenta montar código a partir do CodeDrawer.

        Args:
            prompt:        Prompt original do usuário.
            board:         Lousa corrente (para injetar o código como draft).
            lang_override: Força linguagem (ex: "python").

        Returns:
            RouteResult com hit=True e código pronto, ou hit=False.
        """
        try:
            return self._route_impl(prompt, board, lang_override)
        except Exception:
            return RouteResult(hit=False)  # OSL-15

    # ------------------------------------------------------------------
    # Implementação interna
    # ------------------------------------------------------------------

    def _route_impl(
        self,
        prompt: str,
        board: "DoxoBoard | None",
        lang_override: str | None,
    ) -> RouteResult:
        # 1. Extrai intent
        name, lang, inputs, outputs = _extract_intent(prompt)
        if lang_override:
            lang = lang_override
        if name is None:
            return RouteResult(hit=False)

        # 2. Busca no CodeDrawer (lazy — OSL-3)
        from engine.tools.code_drawer import CodeDrawer
        drawer = CodeDrawer()
        snippet = drawer.assemble(
            name=name,
            lang=lang,
            inputs=inputs or None,
            outputs=outputs or None,
        )
        if snippet is None:
            return RouteResult(hit=False)

        code = snippet.code
        attempts = 0
        issues: list[str] = []

        # 3. Diagnóstico no sandbox
        for attempt in range(self._max_fix + 1):
            attempts = attempt + 1
            issues = self._diagnose(code)

            if not issues:
                break

            if attempt < self._max_fix:
                # Fix pontual: apenas ajusta nomes de variáveis / tipo de IO
                # Não chama o LLM para regerar tudo — só aplica substituições simples.
                fixed = _fix_io(code, inputs, outputs)
                if fixed != code:
                    code = fixed
                    continue
                # Se fix de IO não ajudou, desiste
                break

        if issues:
            # Sandbox falhou mesmo após fix → não injeta código ruim na lousa
            return RouteResult(hit=False, issues=issues, attempts=attempts)

        # 4. Injeta na lousa como evidência pesada
        if board is not None:
            self._post_to_board(board, code, name, lang)

        return RouteResult(
            hit=True,
            code=code,
            max_tokens_hint=64,   # LLM só precisa escrever a explicação
            attempts=attempts,
        )

    # ------------------------------------------------------------------
    # Sandbox — diagnóstico inline (OSL-3: lazy)
    # ------------------------------------------------------------------

    @staticmethod
    def _diagnose(code: str) -> list[str]:
        try:
            from engine.tools.code_sandbox import lint_python_text
            issues = lint_python_text(code)
            # Ignora issues cosméticos — só bloqueia erros que quebram execução
            _SKIP = ("trailing whitespace", "evitar TAB", "linha acima de 120")
            return [i for i in issues if not any(s in i for s in _SKIP)]
        except Exception as exc:
            return [f"[ROUTER] linter indisponível: {exc}"]

    # ------------------------------------------------------------------
    # Injeção na lousa
    # ------------------------------------------------------------------

    @staticmethod
    def _post_to_board(board: Any, code: str, name: str, lang: str) -> None:
        """Posta o código como draft de alta evidência na lousa.

        O `system_hint` que chega ao bridge.ask() já vai conter o código,
        então o LLM só precisa escrever a explicação em torno dele.
        """
        try:
            # Código como evidência — peso máximo
            board.post_draft(
                source="drawer_router",
                content=(
                    f"Código pronto para '{name}' ({lang}):\n"
                    f"[code-begin]\n{code}\n[code-end]"
                ),
                role="evidence",
                weight=1.0,
            )
            # Instrução para o LLM: não regenerar, só explicar
            board.post_draft(
                source="drawer_router",
                content=(
                    "O código acima já está pronto e validado. "
                    "Apresente-o diretamente e explique brevemente o que ele faz. "
                    "Não regenere o código — use exatamente o bloco fornecido."
                ),
                role="constraint",
                weight=1.0,
            )
        except Exception:
            pass  # OSL-15


# ---------------------------------------------------------------------------
# Fix pontual de I/O — sem LLM (OSL-18: stdlib only)
# ---------------------------------------------------------------------------

def _fix_io(code: str, inputs: list[str], outputs: list[str]) -> str:
    """Tenta corrigir nomes de variáveis de I/O no snippet.

    Estratégia simples: se o snippet usa nomes genéricos (data, lst, items)
    e o prompt menciona nomes específicos, substitui no código.

    Não toca em nenhuma lógica — só renomeia variáveis de fronteira.
    """
    if not code:
        return code

    # Mapeamentos genérico → específico para inputs comuns
    _GENERIC_INPUTS  = ("data", "lst", "items", "collection", "elements")
    _GENERIC_OUTPUTS = ("result", "output", "ret", "out")

    patched = code
    for i, inp in enumerate(inputs[:2]):          # máx 2 inputs
        generic = _GENERIC_INPUTS[i] if i < len(_GENERIC_INPUTS) else None
        if generic and generic in patched:
            patched = re.sub(rf"\b{generic}\b", inp, patched)

    for i, outp in enumerate(outputs[:1]):        # máx 1 output
        generic = _GENERIC_OUTPUTS[i] if i < len(_GENERIC_OUTPUTS) else None
        if generic and generic in patched:
            patched = re.sub(rf"\b{generic}\b", outp, patched)

    return patched