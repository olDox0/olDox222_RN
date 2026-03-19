# -*- coding: utf-8 -*-
"""
ORN — Lousa de Raciocínio (DoxoBoard / Hades)

Blackboard clássico: espaço de trabalho ATIVO por query.
Fontes de conhecimento depositam rascunhos → board sintetiza
um bloco estruturado → bloco guia a geração → sessão encerrada.

NÃO é histórico. NÃO persiste respostas entre sessões.
NÃO injeta Q&A do passado no contexto.

OSL-3:  Estado de sessão descartado em close_session() — sem acúmulo.
OSL-4:  open / post / build / close — cada método faz uma coisa.
OSL-5.1: Papéis de rascunho validados contra ROLES conhecidos.
OSL-7:  build_synthesis_block() retorna "" se a sessão estiver vazia.
OSL-18: stdlib only.
God: Hades — guarda o que é útil agora; descarta o que já passou.

Fluxo por query:
  Executive._run_think()
    ├─ board.open_session(query)          # abre workspace limpo
    ├─ board.post_draft(...)              # deposita rascunhos
    ├─ prompt = board.build_synthesis_block() + query
    ├─ bridge.ask(prompt)
    └─ board.close_session()             # descarta tudo
"""

from __future__ import annotations

import ast
import re

from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Papéis de rascunho — o que cada draft representa no raciocínio
# ---------------------------------------------------------------------------

DraftRole = Literal[
    "decomp",       # decomposição da query em sub-aspectos
    "constraint",   # restrição de formato ou escopo da resposta
    "evidence",     # fato ou dado de suporte já conhecido
    "angle",        # ângulo de abordagem sugerido
    "counter",      # contra-argumento ou ressalva a considerar
    "format",       # instrução de formato para o output
]

_VALID_ROLES: frozenset[str] = frozenset(
    {"decomp", "constraint", "evidence", "angle", "counter", "format"}
)


# ---------------------------------------------------------------------------
# Unidade de rascunho
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Draft:
    """Um rascunho depositado por uma fonte de conhecimento.

    Attributes:
        source:  Quem depositou (ex: "decomposer", "context_file", "user_hint").
        role:    Papel no raciocínio — ver DraftRole.
        content: Conteúdo do rascunho (texto curto).
        weight:  Importância relativa; influencia ordem no bloco (0.0–1.0).
    """
    source:  str
    role:    str
    content: str
    weight:  float = 1.0


# ---------------------------------------------------------------------------
# DoxoBoard — lousa de raciocínio
# ---------------------------------------------------------------------------

class DoxoBoard:
    """Workspace de raciocínio por query.

    Cada chamada a open_session() apaga a sessão anterior.
    Os drafts acumulados em post_draft() são sintetizados por
    build_synthesis_block() num bloco de texto injetado no prompt.
    close_session() descarta tudo — não há persistência de conteúdo.

    Args:
        max_drafts: Limite de drafts por sessão (evita crescimento sem controle).
    """

    _MAX_CONTENT: int = 160   # chars máximos por draft no bloco final
    _SECTION_SEP: str = "\n"

    def __init__(self, max_drafts: int = 16) -> None:
        self._max_drafts: int = max(4, int(max_drafts))
        self._query:      str = ""
        self._drafts:     list[Draft] = []
        self._open:       bool = False

    # ------------------------------------------------------------------
    # Ciclo de vida da sessão
    # ------------------------------------------------------------------

    def open_session(self, query: str) -> None:
        """Inicia um workspace limpo para a query.

        OSL-5.1: query vazia é aceita (pode ser completada depois).
        Chama close_session() implicitamente para garantir limpeza.

        Args:
            query: Texto da query que será processada.
        """
        self.close_session()
        self._query = query.strip() if query else ""
        self._open  = True

    def close_session(self) -> None:
        """Descarta todos os drafts da sessão corrente.

        OSL-3: determinístico — não depende de GC nem de TTL.
        Idempotente: seguro chamar sem sessão aberta.
        """
        self._query  = ""
        self._drafts = []
        self._open   = False

    # ------------------------------------------------------------------
    # Depósito de rascunhos (fontes de conhecimento)
    # ------------------------------------------------------------------

    def post_draft(
        self,
        source:  str,
        content: str,
        role:    str = "angle",
        weight:  float = 1.0,
    ) -> None:
        """Deposita um rascunho de raciocínio na lousa.

        OSL-5.1: valida role, source e content antes de aceitar.
        Limita ao max_drafts mais pesados quando cheio.

        Args:
            source:  Identificador da fonte (ex: "decomposer", "file_ctx").
            content: Texto curto — será truncado a _MAX_CONTENT chars.
            role:    Papel do rascunho — ver DraftRole.
            weight:  Importância (0.0–1.0). Padrão 1.0.

        Raises:
            RuntimeError: Se chamado sem open_session() ativo.
            ValueError:   Se source, content ou role forem inválidos.
        """
        if not self._open:
            raise RuntimeError(
                "post_draft() chamado sem sessão aberta. "
                "Chame open_session() primeiro."
            )
        if not source or not source.strip():
            raise ValueError("source não pode ser vazio.")
        if not content or not content.strip():
            raise ValueError("content não pode ser vazio.")
        role = role.strip().lower()
        if role not in _VALID_ROLES:
            raise ValueError(
                f"role inválido: '{role}'. "
                f"Válidos: {sorted(_VALID_ROLES)}"
            )

        draft = Draft(
            source  = source.strip(),
            role    = role,
            content = content.strip()[: self._MAX_CONTENT * 2],   # pré-trunca
            weight  = max(0.0, min(1.0, float(weight))),
        )
        self._drafts.append(draft)

        # Mantém apenas os max_drafts mais relevantes (por weight, FIFO como desempate)
        if len(self._drafts) > self._max_drafts:
            self._drafts.sort(key=lambda d: d.weight, reverse=True)
            self._drafts = self._drafts[: self._max_drafts]

    # ------------------------------------------------------------------
    # Síntese — monta bloco para injetar no prompt
    # ------------------------------------------------------------------

    def build_synthesis_block(self, compact: bool = False) -> str:
        """Sintetiza os drafts em um bloco estruturado para o prompt.

        OSL-7: retorna "" se a sessão estiver vazia — chamador não precisa
               verificar nada especial, pode concatenar diretamente.

        O bloco é organizado por role na ordem de prioridade:
          constraint → decomp → evidence → angle → counter → format
        Dentro de cada role, ordenado por weight (maior primeiro).

        Args:
            compact: Se True, usa formato ultra-curto para economizar tokens.
                     Modo normal  → ~35–50 tokens de overhead.
                     Modo compacto → ~8–14 tokens de overhead.

        Returns:
            Bloco de texto pronto para ser prefixado ao prompt,
            ou "" se não houver drafts.
        """
        if not self._drafts:
            return ""

        role_order = ["constraint", "decomp", "evidence", "angle", "counter", "format"]
        grouped: dict[str, list[Draft]] = {r: [] for r in role_order}
        for d in self._drafts:
            if d.role in grouped:
                grouped[d.role].append(d)

        if compact:
            return self._build_compact(grouped, role_order)

        sections: list[str] = []
        for role in role_order:
            items = sorted(grouped[role], key=lambda d: d.weight, reverse=True)
            if not items:
                continue
            label = _ROLE_LABELS.get(role, role.upper())
            lines = [f"  - {d.content[: self._MAX_CONTENT]}" for d in items]
            sections.append(f"[{label}]\n" + "\n".join(lines))

        if not sections:
            return ""

        body = self._SECTION_SEP.join(sections)
        return f"[LOUSA]\n{body}\n[/LOUSA]\n\n"

    def _build_compact(
        self,
        grouped: dict[str, list[Draft]],
        role_order: list[str],
    ) -> str:
        """Formato compacto: uma linha por role, tags de 1 char.

        Exemplo de saída:
            [R]PT.conciso. [D]explicar. [E]arquivo:foo.py.

        Mantém apenas o draft de maior weight por role.
        Trunca cada item a 60 chars para conter o overhead.
        """
        _SHORT: dict[str, str] = {
            "constraint": "R",   # Restrição
            "decomp":     "D",   # Decomposição
            "evidence":   "E",   # Evidência
            "angle":      "A",   # Ângulo
            "counter":    "C",   # Counter
            "format":     "F",   # Formato
        }
        _MAX_COMPACT = 60
        parts: list[str] = []
        for role in role_order:
            items = sorted(grouped[role], key=lambda d: d.weight, reverse=True)
            if not items:
                continue
            best = items[0].content[:_MAX_COMPACT].replace("\n", " ")
            parts.append(f"[{_SHORT[role]}]{best}")

        if not parts:
            return ""
        return " ".join(parts) + "\n"

    # ------------------------------------------------------------------
    # Introspecção (OSL-12)
    # ------------------------------------------------------------------

    def session_info(self) -> dict:
        """Retorna estado da sessão corrente para diagnóstico / `orn brain`.

        Returns:
            Dict com query, total de drafts e contagem por role.
        """
        counts: dict[str, int] = {}
        for d in self._drafts:
            counts[d.role] = counts.get(d.role, 0) + 1
        return {
            "open":         self._open,
            "query_preview": self._query[:80] if self._query else "",
            "draft_count":   len(self._drafts),
            "by_role":       counts,
        }


# ---------------------------------------------------------------------------
# Rótulos legíveis para o bloco de síntese
# ---------------------------------------------------------------------------

_ROLE_LABELS: dict[str, str] = {
    "constraint": "RESTRIÇÕES",
    "decomp":     "DECOMPOSIÇÃO",
    "evidence":   "EVIDÊNCIAS",
    "angle":      "ÂNGULOS",
    "counter":    "RESSALVAS",
    "format":     "FORMATO",
}


# ---------------------------------------------------------------------------
# Redutor Cognitivo (Auxiliar da Lousa)
# ---------------------------------------------------------------------------

class CognitiveReducer:
    """
    Mastiga arquivos e cospe apenas o "esqueleto" cognitivo.
    Reduz drasticamente o consumo de tokens (Prompt Eval) no LLM.
    OSL-18: Usa apenas a Standard Library (ast, re).
    """

    @staticmethod
    def reduce_file(filename: str, content: str, max_chars: int = 600) -> str:
        """Roteia o arquivo para o mastigador correto com base na extensão."""
        if not content or len(content) < max_chars:
            return content # Se for pequeno, deixa passar

        if filename.endswith(".py"):
            return CognitiveReducer._reduce_python(content, max_chars)
        
        # Fallback genérico para outras linguagens: 
        # Tira linhas vazias e tenta manter formato denso
        return CognitiveReducer._reduce_generic(content, max_chars)

    @staticmethod
    def _reduce_python(code: str, max_chars: int) -> str:
        """Usa AST para extrair apenas a assinatura de Classes e Funções."""
        try:
            tree = ast.parse(code)
            lines =[]
            
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    lines.append(f"class {node.name}:")
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) or isinstance(item, ast.AsyncFunctionDef):
                            lines.append(f"  def {item.name}(...)")
                
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    lines.append(f"def {node.name}(...)")

            summary = "\n".join(lines)
            
            # Se o arquivo for só um script solto sem funções, faz o corte genérico
            if not summary.strip():
                return CognitiveReducer._reduce_generic(code, max_chars)
                
            # Se a árvore for muito grande, trunca a própria árvore
            return summary[:max_chars]
            
        except SyntaxError:
            # Se o código estiver quebrado, fallback seguro
            return CognitiveReducer._reduce_generic(code, max_chars)

    @staticmethod
    def _reduce_generic(text: str, max_chars: int) -> str:
        """Limpa espaços e quebras de linha excessivas."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        compact = "\n".join(lines)
        if len(compact) > max_chars:
            return compact[:max_chars] + "\n[... truncado]"
        return compact