# -*- coding: utf-8 -*-
"""
ORN — Executive (Zeus)
Orquestrador central. Recebe goals da CLI e despacha para os módulos certos.

OSL-17: Este módulo só orquestra — nunca executa lógica de negócio diretamente.
OSL-5.1: Pré-condições verificadas antes de qualquer dispatch.
OSL-7: Retorno de cada módulo filho é verificado antes de prosseguir.
OSL-15: Modo degradado — erros não fatais retornam GoalResult(success=False).
God: Zeus — controla permissões e decisões globais do sistema.

Fluxo MVP (think):
  CLI → process_goal("think", prompt)
       → _run_think()
       → Bridge.ask()
       → Validator.validar_output()
       → GoalResult → CLI

Fluxo futuro (audit, fix, gen):
  CLI → process_goal(intent, payload)
       → Planner.formulate_strategy()
       → ConceptMapper / ferramentas
       → Bridge.ask()
       → Validator.validar_output()
       → GoalResult → CLI
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Tipos de contrato (OSL-7)
# ---------------------------------------------------------------------------

@dataclass
class GoalResult:
    """Resultado de um process_goal.

    Attributes:
        success:  True se o pipeline completou sem erros críticos.
        intent:   Intent original recebido.
        output:   Texto gerado (resposta, código, análise, etc).
        errors:   Erros não-fatais encontrados no pipeline.
        metadata: Dados extras — tempo de execução, tokens estimados, etc.
    """
    success:  bool
    intent:   str
    output:   str             = ""
    errors:   list[str]       = field(default_factory=list)
    metadata: dict[str, Any]  = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Executive
# ---------------------------------------------------------------------------

class SiCDoxExecutive:
    """Orquestrador central do ORN.

    OSL-3: Módulos filhos carregados sob demanda (lazy) — não no __init__.
    OSL-16: Máx 500 linhas; lógica de cada intent vai para _run_*().
    """

    def __init__(self) -> None:
        self._bridge:    Any = None   # SiCDoxBridge  (Hefesto)
        self._board:     Any = None   # DoxoBoard     (Hades)
        self._validator: Any = None   # SiCDoxValidator (Anúbis)
        self._planner:   Any = None   # ExecutivePlanner (Atena)
        self._memory:    Any = None   # VectorDB      (Osíris)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def process_goal(self, intent: str, payload: str,
                     context: dict[str, Any] | None = None) -> GoalResult:
        """Processa um goal recebido da CLI.

        OSL-5.1: Valida intent e payload antes de qualquer dispatch.
        OSL-7: Cada etapa tem retorno verificado.
        OSL-15: Exceções internas viram GoalResult(success=False) — nunca
                propagam para a CLI como exceção não tratada.

        Args:
            intent:  Tipo de ação: 'think' | 'audit' | 'fix' | 'gen' |
                                   'brain' | 'graph' | 'config'.
            payload: Conteúdo principal (prompt ou caminho de arquivo).
            context: Dados extras opcionais passados pelo comando CLI.

        Returns:
            GoalResult com output e status do pipeline.
        """
        if not intent:
            raise ValueError("intent não pode ser vazio.")
        if not payload:
            raise ValueError("payload não pode ser vazio.")

        context = context or {}
        t_start = time.monotonic()

        try:
            result = self._dispatch(intent, payload, context)
        except NotImplementedError as exc:
            result = GoalResult(
                success=False, intent=intent,
                errors=[f"[TODO] {exc}"],
            )
        except FileNotFoundError as exc:
            result = GoalResult(
                success=False, intent=intent,
                errors=[f"[ARQUIVO] {exc}"],
            )
        except Exception as exc:  # OSL-15: captura controlada
            result = GoalResult(
                success=False, intent=intent,
                errors=[f"[ERRO INTERNO] {type(exc).__name__}: {exc}"],
            )

        result.metadata["elapsed_s"] = round(time.monotonic() - t_start, 3)
        return result

    def shutdown(self) -> None:
        """Libera recursos. OSL-3: determinístico, não depende do GC."""
        if self._bridge is not None:
            self._bridge.shutdown()
            self._bridge = None

    def bridge_stats(self) -> dict[str, Any]:
        """Estado do bridge para `orn brain`. OSL-12."""
        if self._bridge is None:
            return {"model_loaded": False}
        return self._bridge.stats()

    # ------------------------------------------------------------------
    # Dispatcher central
    # ------------------------------------------------------------------

    def _dispatch(self, intent: str, payload: str,
                  context: dict[str, Any]) -> GoalResult:
        """Roteia intent para o método _run_* correto.

        OSL-5.1: intent desconhecido retorna GoalResult de erro, não exceção.
        """
        routes: dict[str, Any] = {
            "think": self._run_think,
            "audit": self._run_audit,
            "fix":   self._run_fix,
            "gen":   self._run_gen,
            "brain": self._run_brain,
            "graph": self._run_graph,
        }
        runner = routes.get(intent)
        if runner is None:
            return GoalResult(
                success=False, intent=intent,
                errors=[f"Intent desconhecido: '{intent}'. "
                        f"Opções: {list(routes.keys())}"],
            )
        return runner(payload, context)

    # ------------------------------------------------------------------
    # MVP — think (Fase 1)
    # ------------------------------------------------------------------

    def _run_think(self, prompt: str, context: dict[str, Any]) -> GoalResult:
        """Pipeline completo do comando `orn think`.

        Etapas:
          1. Injeta contexto de arquivo (se fornecido).
          2. Chama Bridge.ask().
          3. Valida output via Validator.
          4. Registra no Blackboard.
        """
        bridge    = self._get_bridge()
        validator = self._get_validator()
        board     = self._get_board()

        # 1. Contexto de arquivo opcional (--file)
        full_prompt = prompt
        if context.get("context_file"):
            file_content = _read_file_safe(context["context_file"])
            if file_content:
                full_prompt = (
                    f"[CTX-BEGIN]\n"
                    f"scope: {context['context_file']}\n"
                    f"{file_content}\n"
                    f"[CTX-END]\n\n"
                    f"[TASK]\n{prompt}"
                )

        # 2. Inferência — max_tokens do contexto (CLI --tokens) ou None (usa config)
        max_tokens = context.get("max_tokens")
        output = bridge.ask(full_prompt, max_tokens=max_tokens)

        # 3. Validação (OSL-7)
        valid, motivo = validator.validar_output(output)
        if not valid:
            board.post_hypothesis(
                source="validator",
                content=f"Output rejeitado: {motivo}",
                confidence=0.9,
            )
            return GoalResult(
                success=False, intent="think",
                errors=[f"Output inválido: {motivo}"],
            )

        # 4. Registra no Blackboard (Hades)
        board.post_hypothesis(
            source="think",
            content=f"Q: {prompt[:80]}...",
            confidence=1.0,
        )

        return GoalResult(success=True, intent="think", output=output)

    # ------------------------------------------------------------------
    # Fases futuras — stubs com NotImplementedError descritivo
    # ------------------------------------------------------------------

    def _run_audit(self, payload: str, context: dict[str, Any]) -> GoalResult:
        """TODO Fase 2: ConceptMapper → prompt estruturado → LLM → relatório."""
        raise NotImplementedError("audit — implementar na Fase 2.")

    def _run_fix(self, payload: str, context: dict[str, Any]) -> GoalResult:
        """TODO Fase 4: audit() + diff de patch + validação sintática."""
        raise NotImplementedError("fix — implementar na Fase 4.")

    def _run_gen(self, payload: str, context: dict[str, Any]) -> GoalResult:
        """TODO Fase 4: generate_plan() + LLM + Validator._validar_python()."""
        raise NotImplementedError("gen — implementar na Fase 4.")

    def _run_brain(self, payload: str, context: dict[str, Any]) -> GoalResult:
        """TODO Fase 3: DoxoBoard.get_summary() + VectorDB.stats()."""
        raise NotImplementedError("brain — implementar na Fase 3.")

    def _run_graph(self, payload: str, context: dict[str, Any]) -> GoalResult:
        """TODO Fase 2: ConceptMapper.internalizar() + GraphInspector.show()."""
        raise NotImplementedError("graph — implementar na Fase 2.")

    # ------------------------------------------------------------------
    # Loaders lazy (OSL-3)
    # ------------------------------------------------------------------

    def _get_bridge(self) -> Any:
        if self._bridge is None:
            from engine.core.llm_bridge import SiCDoxBridge   # noqa: PLC0415
            self._bridge = SiCDoxBridge()
        return self._bridge

    def _get_board(self) -> Any:
        if self._board is None:
            from engine.core.blackboard import DoxoBoard        # noqa: PLC0415
            self._board = DoxoBoard()
        return self._board

    def _get_validator(self) -> Any:
        if self._validator is None:
            from engine.core.logic_filter import SiCDoxValidator  # noqa: PLC0415
            self._validator = SiCDoxValidator()
        return self._validator

    def _get_planner(self) -> Any:
        if self._planner is None:
            from engine.thinking.planner import ExecutivePlanner  # noqa: PLC0415
            self._planner = ExecutivePlanner()
        return self._planner

    def _get_memory(self) -> Any:
        if self._memory is None:
            from engine.memory.vector_db import VectorDB          # noqa: PLC0415
            self._memory = VectorDB()
        return self._memory


# ---------------------------------------------------------------------------
# Utilitário interno (OSL-18: stdlib only)
# ---------------------------------------------------------------------------

def _read_file_safe(path: str, max_chars: int = 3000) -> str:
    """Lê um arquivo de texto com limite de caracteres.

    OSL-5.2: Valida path antes de abrir.
    OSL-3: max_chars evita injetar arquivos gigantes no KV-cache.

    Args:
        path:      Caminho do arquivo.
        max_chars: Limite de caracteres a incluir no contexto.

    Returns:
        Conteúdo do arquivo (truncado se necessário) ou string vazia se falhar.
    """
    if not path:
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read(max_chars)
        if len(content) == max_chars:
            content += "\n[... arquivo truncado para caber no contexto ...]"
        return content
    except OSError:
        return ""