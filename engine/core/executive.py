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
        self._infer_queue = None
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
            import sys as _dox_sys, os as _dox_os
            exc_type, exc_obj, exc_tb = _dox_sys.exc_info()
            f_name = _dox_os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] if exc_tb else "Unknown"
            line_n = exc_tb.tb_lineno if exc_tb else 0
            print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: _analyze_layer\033[0m\n\033[31m  ■ Type: {type(e).__name__} | Value: {exc}\033")

        except FileNotFoundError as exc:
            result = GoalResult(
                success=False, intent=intent,
                errors=[f"[ARQUIVO] {exc}"],
            )
            import sys as _dox_sys, os as _dox_os
            exc_type, exc_obj, exc_tb = _dox_sys.exc_info()
            f_name = _dox_os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] if exc_tb else "Unknown"
            line_n = exc_tb.tb_lineno if exc_tb else 0
            print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: _analyze_layer\033[0m\n\033[31m  ■ Type: {type(e).__name__} | Value: {exc}\033")

        except Exception as exc:  # OSL-15: captura controlada
            result = GoalResult(
                success=False, intent=intent,
                errors=[f"[ERRO INTERNO] {type(exc).__name__}: {exc}"],
            )
            import sys as _dox_sys, os as _dox_os
            exc_type, exc_obj, exc_tb = _dox_sys.exc_info()
            f_name = _dox_os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] if exc_tb else "Unknown"
            line_n = exc_tb.tb_lineno if exc_tb else 0
            print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: _analyze_layer\033[0m\n\033[31m  ■ Type: {type(e).__name__} | Value: {exc}\033")


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

    def board_summary(self) -> dict[str, Any]:
        """Estado da sessão corrente da lousa (OSL-12)."""
        return self._get_board().session_info()

    def clear_board(self) -> None:
        """Fecha e descarta a sessão corrente da lousa."""
        self._get_board().close_session()

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
          1. Abre sessão na lousa (workspace limpo).
          2. Decompõe a query em rascunhos de raciocínio.
          3. Injeta contexto de arquivo opcional (--file).
          4. Constrói prompt = synthesis_block + [TASK].
          5. Chama Bridge.ask().
          6. Valida output via Validator.
          7. Fecha sessão da lousa (descarta rascunhos).

        OSL-7: sessão fechada em finally — sem vazamento entre queries.
        """
        bridge    = self._get_bridge()
        validator = self._get_validator()
        board     = self._get_board()

        # 1. Workspace limpo para esta query
        _session_opened = False
        try:
            board.open_session(prompt)
            _session_opened = True
        except Exception as exc:
            return GoalResult(
                success=False, intent="think",
                errors=[f"[BOARD] Falha ao abrir sessão: {exc}"],
            )
            import sys as _dox_sys, os as _dox_os
            exc_type, exc_obj, exc_tb = _dox_sys.exc_info()
            f_name = _dox_os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] if exc_tb else "Unknown"
            line_n = exc_tb.tb_lineno if exc_tb else 0
            print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: _analyze_layer\033[0m\n\033[31m  ■ Type: {type(e).__name__} | Value: {exc}\033")


        try:
            # 2. Popula lousa com rascunhos de raciocínio (rule-based, sem LLM)
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

            # 4. Monta bloco de síntese (vai para system prompt, não para user turn)
            synthesis = board.build_synthesis_block(compact=True)

            # 5. Inferência
            #    synthesis → system_hint (instruções, não ecoadas pelo modelo)
            #    prompt    → user turn puro (apenas a query)
            token_hint = len((synthesis or "") + prompt) // 3 + 30
            max_tokens = context.get("max_tokens")
            output = self._infer_queue.submit(
                prompt,
                max_tokens,
                token_hint,
                synthesis,
            )

            # 6. Validação (OSL-7)
            valid, motivo = validator.validar_output(output)
            if not valid:
                return GoalResult(
                    success=False, intent="think",
                    errors=[f"Output inválido: {motivo}"],
                )

            # Captura estado da lousa antes de descartar (vai para metadata/telemetria)
            board_snapshot = board.session_info()
            board_snapshot["token_hint"]  = token_hint
            board_snapshot["system_hint"] = bool(synthesis)

            result = GoalResult(success=True, intent="think", output=output)
            result.metadata["board"] = board_snapshot
            return result

        finally:
            # 7. OSL-3: descarta workspace — sem acúmulo entre queries.
            # O guard _session_opened evita chamar close_session() se open_session()
            # falhou, o que poderia causar erro ao fechar uma sessão inexistente.
            if _session_opened:
                try:
                    board.close_session()
                except Exception as e:
                    import sys as _dox_sys, os as _dox_os
                    exc_type, exc_obj, exc_tb = _dox_sys.exc_info()
                    f_name = _dox_os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] if exc_tb else "Unknown"
                    line_n = exc_tb.tb_lineno if exc_tb else 0
                    print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: _analyze_layer\033[0m\n\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033")


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
        """TODO Fase 3: DoxoBoard.session_info() + VectorDB.stats()."""
        raise NotImplementedError("brain — implementar na Fase 3.")

    def _run_graph(self, payload: str, context: dict[str, Any]) -> GoalResult:
        """TODO Fase 2: ConceptMapper.internalizar() + GraphInspector.show()."""
        raise NotImplementedError("graph — implementar na Fase 2.")

    # ------------------------------------------------------------------
    # Loaders lazy (OSL-3)
    # ------------------------------------------------------------------

    def _get_bridge(self):
        if self._bridge is None:
            from engine.core.llm_bridge import SiCDoxBridge
            from engine.runtime.infer_queue import InferQueue

            self._bridge = SiCDoxBridge()
            self._infer_queue = InferQueue(self._bridge)

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
# Utilitários internos (OSL-18: stdlib only)
# ---------------------------------------------------------------------------

# Constantes de decomposição movidas para módulo — evitam realocação a cada chamada.
_LANG_MAP: tuple[tuple[str, str], ...] = (
    ("python", "python"), ("py ",    "python"),
    ("c++",    "c++"),    ("cpp",    "c++"),
    (" c ",    "C"),      ("em c,",  "C"), ("em c.", "C"),
    ("batch",  "batch"),  ("bat ",   "batch"),
)
_KW_EXPLAIN  = ("explique", "explica", "o que é", "como funciona", "define")
_KW_GENERATE = ("crie", "escreva", "gere", "implemente", "faça", "cria")
_KW_FIX      = ("corrija", "conserte", "bug", "erro", "fix")
_KW_LIST     = ("liste", "quais são", "enumere", "mostre os")


def _decompose_query(board: Any, prompt: str, context: dict) -> None:
    """Popula a lousa com rascunhos de raciocínio baseados em regras.

    Orienta o modelo sobre o que é esperado sem custo extra de inferência.
    Conteúdo dos drafts intencionalmente curto — cada char aqui custa token.

    Args:
        board:   DoxoBoard com sessão aberta.
        prompt:  Query original do usuário.
        context: Dict de contexto do Executive.
    """
    p = prompt.lower()

    # Restrição de idioma (sempre presente, texto mínimo)
    board.post_draft(
        source  = "decomposer",
        content = "PT.conciso.",
        role    = "constraint",
        weight  = 1.0,
    )

    # Detecção de linguagem de programação
    for kw, lang in _LANG_MAP:
        if kw in p:
            board.post_draft(
                source  = "decomposer",
                content = f"lang:{lang}.",
                role    = "constraint",
                weight  = 0.95,
            )
            break

    # Tipo de tarefa (texto curto — o modelo entende diretivas concisas)
    if any(kw in p for kw in _KW_EXPLAIN):
        board.post_draft(
            source  = "decomposer",
            content = "explicar.",
            role    = "decomp",
            weight  = 0.85,
        )
    elif any(kw in p for kw in _KW_GENERATE):
        board.post_draft(
            source  = "decomposer",
            content = "gerar artefato.",
            role    = "decomp",
            weight  = 0.85,
        )
    elif any(kw in p for kw in _KW_FIX):
        board.post_draft(
            source  = "decomposer",
            content = "corrigir:causa+fix.",
            role    = "decomp",
            weight  = 0.85,
        )
    elif any(kw in p for kw in _KW_LIST):
        board.post_draft(
            source  = "decomposer",
            content = "lista numerada.",
            role    = "format",
            weight  = 0.8,
        )

    # Escopo de arquivo (se --file fornecido)
    if context.get("context_file"):
        board.post_draft(
            source  = "decomposer",
            content = f"file:{context['context_file']}",
            role    = "angle",
            weight  = 0.9,
        )


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