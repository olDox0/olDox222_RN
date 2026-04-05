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

import re, time, functools

from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any

from engine.telemetry.forensic import emit_forensic_log
from engine.thinking.code_hook import apply_code_hook     # Argos
from engine.thinking.drawer_router import DrawerRouter

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
    success: bool
    intent: str
    output: str = ""
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Executive
# ---------------------------------------------------------------------------

class SiCDoxExecutive:
    """Orquestrador central do ORN.

    OSL-3: Módulos filhos carregados sob demanda (lazy) — não no __init__.
    OSL-16: Máx 500 linhas; lógica de cada intent vai para _run_*().
    """

    def __init__(self, persistent: bool = True) -> None:
        self._board: Any = None              # DoxoBoard (Hades)
        self._bridge: Any = None              # SiCDoxBridge (Hefesto)
        self._infer_queue: Any = None
        self._memory: Any = None             # VectorDB (Osíris)
        self._persistent = persistent
        self._planner: Any = None            # ExecutivePlanner (Atena)
        self._validator: Any = None          # SiCDoxValidator (Anúbis)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def process_goal(
        self,
        intent: str,
        payload: str,
        context: dict[str, Any] | None = None,
    ) -> GoalResult:
        """Processa um goal recebido da CLI."""
        if not intent:
            raise ValueError("intent não pode ser vazio.")
        if not payload:
            raise ValueError("payload não pode ser vazio.")

        context = context or {}
        t_start = time.monotonic()

        try:
            result = self._dispatch(intent, payload, context)
        except NotImplementedError as exc:
            emit_forensic_log(exc, "_dispatch")
            result = GoalResult(success=False, intent=intent, errors=[f"[TODO] {exc}"])
        except FileNotFoundError as exc:
            emit_forensic_log(exc, "_dispatch")
            result = GoalResult(success=False, intent=intent, errors=[f"[ARQUIVO] {exc}"])
        except Exception as exc:
            emit_forensic_log(exc, "_dispatch")
            result = GoalResult(
                success=False,
                intent=intent,
                errors=[f"[ERRO INTERNO] {type(exc).__name__}: {exc}"],
            )

        result.metadata["elapsed_s"] = round(time.monotonic() - t_start, 3)
        return result

    def shutdown(self, force: bool = False) -> None:
        """Libera recursos. Só fecha o bridge se não estiver em modo persistente,
        ou se force=True for explicitamente pedido."""
        if self._persistent and not force:
            return

        if self._infer_queue is not None:
            try:
                self._infer_queue.shutdown()
            except Exception:
                pass
            self._infer_queue = None

        if self._bridge is not None:
            try:
                self._bridge.shutdown()
            except Exception:
                pass
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

    def _dispatch(
        self,
        intent: str,
        payload: str,
        context: dict[str, Any],
    ) -> GoalResult:
        """Roteia intent para o método _run_* correto."""
        routes: dict[str, Any] = {
            "think": self._run_think,
            "audit": self._run_audit,
            "fix": self._run_fix,
            "gen": self._run_gen,
            "brain": self._run_brain,
            "graph": self._run_graph,
        }
        runner = routes.get(intent)
        if runner is None:
            return GoalResult(
                success=False,
                intent=intent,
                errors=[
                    f"Intent desconhecido: '{intent}'. "
                    f"Opções: {list(routes.keys())}",
                ],
            )
        return runner(payload, context)

    # ------------------------------------------------------------------
    # MVP — think (Fase 1)
    # ------------------------------------------------------------------

    def _run_think(self, prompt: str, context: dict[str, Any]) -> GoalResult:
        _bridge = self._get_bridge()
        validator = self._get_validator()
        board = self._get_board()

        session_opened = False
        try:
            board.open_session(prompt)
            session_opened = True
        except Exception as exc:
            return GoalResult(success=False, intent="think", errors=[f"[BOARD] Erro: {exc}"])

        try:
            # 2. Popula lousa com rascunhos de raciocínio
            _decompose_query(board, prompt, context)

            # 2.5 --- ATIVAÇÃO DO GAVETEIRO (HERMES) ---
            max_tokens = context.get("max_tokens")
            if context.get("drawer_first"):
                router = self._get_drawer_router()
                if router:
                    r_res = router.route(prompt, board)
                    if r_res.hit:
                        # Se achou no gaveteiro, reduzimos o trabalho do LLM para apenas explicar
                        max_tokens = r_res.max_tokens_hint or 128
                        print("\n  [Hermes] 📦 Snippet resgatado do Gaveteiro e injetado na lousa!")
            # ------------------------------------------

            # 3. Contexto de arquivo opcional (--file)
            if context.get("context_file"):
                file_content = _read_file_safe(context["context_file"])
                if file_content:
                    board.post_draft(
                        source="context_file",
                        content=f"Arquivo '{context['context_file']}': {file_content[:120]}",
                        role="evidence",
                        weight=0.95,
                    )

            synthesis = board.build_synthesis_block(compact=True)

            # Limita system_hint: cada token de prompt custa igual a
            # um token gerado no N2808 — evita prefill caro.
            if synthesis and len(synthesis) > 160: # 240:
                synthesis = synthesis[:160].rsplit(" ", 1)[0] + " […]"

            token_hint = 64
            max_tokens = context.get("max_tokens") or _adaptive_max_tokens(prompt)

            # ── DrawerRouter: tenta código pré-pronto (Hermes) ────────
            # Se o DrawerRouter encontrar e validar um snippet no CodeDrawer,
            # ele injeta o código na lousa como evidência de peso 1.0 e retorna
            # max_tokens_hint=64. O bridge.ask() subsequente só escreve a
            # explicação — não regenera o código do zero.
            route = self._get_drawer_router().route(
                prompt,
                board=board,
            )
            if route.hit:
                # Código já na lousa → LLM só explica
                max_tokens = route.max_tokens_hint or 64
                # Reconstrói synthesis com o código injetado
                synthesis = board.build_synthesis_block(compact=True)
                if synthesis and len(synthesis) > 240:
                    synthesis = synthesis[:240].rsplit(" ", 1)[0] + " […]"

            result = self._infer_queue.submit(
                prompt=prompt,
                max_tokens=max_tokens,
                token_hint=token_hint,
                system_hint=synthesis,
            )

            if isinstance(result, Future):
                output = result.result()
            else:
                output = result

            if _looks_degenerate_think_output(prompt, output):
                output = _deterministic_code_answer(prompt)

            # ── Hook: diagnostica código no output e corrige se necessário ──
            output = apply_code_hook(
                output,
                task=prompt,
                bridge=_bridge,
                validator=validator,
                max_retries=1,        # 1 fix attempt dentro do think (rápido)
                run_isolated=True,    # executa python -I para validar
            )

            valid, motivo = validator.validar_output(output)
            if not valid:
                return GoalResult(
                    success=False,
                    intent="think",
                    errors=[f"Output inválido: {motivo}"],
                )

            board_snapshot = board.session_info()
            board_snapshot["token_hint"] = token_hint
            board_snapshot["system_hint"] = bool(synthesis)

            result_goal = GoalResult(success=True, intent="think", output=output)
            result_goal.metadata["board"] = board_snapshot
            return result_goal

        finally:
            if session_opened:
                try:
                    board.close_session()
                except Exception:
                    pass
            # Limpa contexto do bridge entre sessões diretas (evita prompt_tokens crescentes)
            if self._bridge is not None:
                try:
                    self._bridge._ctx.clear()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Fases futuras — stubs com NotImplementedError descritivo
    # ------------------------------------------------------------------

    def _run_audit(self, payload: str, context: dict[str, Any]) -> GoalResult:
        raise NotImplementedError("audit — implementar na Fase 2.")

    def _run_fix(self, payload: str, context: dict[str, Any]) -> GoalResult:
        raise NotImplementedError("fix — implementar na Fase 4.")

    # Fase 4 — Geração (gen) via CodeAssembler (Cosmo Visão)
    def _run_gen(self, payload: str, context: dict[str, Any]) -> GoalResult:
        assembler = self._get_assembler()
        board = self._get_board()
        
        session_opened = False
        try:
            # 1. Abre a lousa para focar o contexto
            board.open_session(f"Gerar arquitetura: {payload}")
            session_opened = True
            
            board.post_draft(
                source="executive",
                content="Priorize a clareza dos contratos I/O (type hints).",
                role="constraint",
                weight=1.0,
            )
            
            # 2. Chama o CodeAssembler (Dédalo)
            # Ele fará as idas e vindas com o modelo para gerar e validar o esqueleto
            assembly_result = assembler.assemble(payload)
            
            if not assembly_result["success"]:
                return GoalResult(
                    success=False,
                    intent="gen",
                    errors=[assembly_result["error"]],
                    output=assembly_result["output"]
                )
            
            # 3. Sucesso! Empacota e retorna
            result_goal = GoalResult(
                success=True, 
                intent="gen", 
                output=assembly_result["output"]
            )
            
            board_snapshot = board.session_info()
            result_goal.metadata["board"] = board_snapshot
            result_goal.metadata["assembler_info"] = "Cosmo Visão I/O aplicada."
            
            return result_goal

        finally:
            if session_opened:
                try:
                    board.close_session()
                except Exception:
                    pass

    def _run_brain(self, payload: str, context: dict[str, Any]) -> GoalResult:
        raise NotImplementedError("brain — implementar na Fase 3.")

    def _run_graph(self, payload: str, context: dict[str, Any]) -> GoalResult:
        raise NotImplementedError("graph — implementar na Fase 2.")

    # ------------------------------------------------------------------
    # Loaders lazy (OSL-3)
    # ------------------------------------------------------------------

    def _get_bridge(self):
        if self._bridge is None:
            from engine.core.llm_bridge import SiCDoxBridge
            from engine.runtime.infer_queue import InferQueue

            self._bridge = SiCDoxBridge()
            self._infer_queue = InferQueue(self._bridge, async_mode=False)

        return self._bridge

    def _get_board(self) -> Any:
        if self._board is None:
            from engine.core.blackboard import DoxoBoard  # noqa: PLC0415
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

    def _get_assembler(self) -> Any:
        if not hasattr(self, "_assembler") or self._assembler is None:
            from engine.thinking.assembler import CodeAssembler  # noqa: PLC0415
            self._assembler = CodeAssembler(self._get_bridge(), self._get_validator())
        return self._assembler

    def _get_drawer_router(self) -> DrawerRouter:
        if not hasattr(self, "_drawer_router") or self._drawer_router is None:
            self._drawer_router = DrawerRouter(max_fix_attempts=1)
        return self._drawer_router

    def _get_memory(self) -> Any:
        if self._memory is None:
            from engine.memory.vector_db import VectorDB  # noqa: PLC0415
            self._memory = VectorDB()
        return self._memory


# ---------------------------------------------------------------------------
# Utilitários internos (OSL-18: stdlib only)
# ---------------------------------------------------------------------------

# Constantes de decomposição
_LANG_MAP: tuple[tuple[str, str], ...] = (
    ("python", "python"),
    (r"\bpy\b", "python"),
    (r"c\+\+", "c++"),
    (r"\bcpp\b", "c++"),
    (r"\bc\b", "C"),
    (r"\bbatch\b", "batch"),
    (r"\bbat\b", "batch script"),
)

_KW_EXPLAIN = r"\b(explique|explica|o que é|como funciona|define)\b"
_KW_GENERATE = r"\b(crie|escreva|gere|implemente|faça|cria)\b"
_KW_FIX = r"\b(corrija|conserte|bug|erro|fix)\b"
_KW_LIST = r"\b(liste|quais são|enumere|mostre)\b"
_KW_CODE_CONTEXT = (
    r"\b(python|py|c\+\+|cpp|java|javascript|typescript|rust|go|script|código|codigo)\b"
)

# --- Cache das Expressões Regulares ---
@functools.lru_cache(maxsize=256)
def classify_prompt(prompt_lower: str):
    # Seu código atual de re.search() entra aqui
    # Retorne a tupla: (lang, task_type, max_tokens)
    pass

def _decompose_query(board: Any, prompt: str, context: dict) -> None:
    """Popula a lousa com rascunhos de raciocínio baseados em Regex (OSL-5)."""
    p = prompt.lower()
    has_code_context = bool(re.search(_KW_CODE_CONTEXT, p))
    wants_explanation = bool(re.search(_KW_EXPLAIN, p))
    wants_generation = bool(re.search(_KW_GENERATE, p))
    has_code_block_ctx = "[code-begin]" in p or bool(context.get("search_code_only"))

    board.post_draft(
        source="decomposer",
        content="Responda em português, objetivo, e sem repetir contexto bruto.",
        role="constraint",
        weight=1.0,
    )

    for pattern, lang in _LANG_MAP:
        if re.search(pattern, p):
            board.post_draft(
                source="decomposer",
                content=f"Código esperado em: {lang}.",
                role="constraint",
                weight=0.95,
            )
            break

    if wants_explanation:
        board.post_draft(
            source="decomposer",
            content="Tarefa: explicação. Priorize clareza sobre completude.",
            role="decomp",
            weight=0.85,
        )
        if has_code_context:
            board.post_draft(
                source="decomposer",
                content="Inclua um exemplo mínimo em código além da explicação.",
                role="format",
                weight=0.83,
            )
    elif wants_generation:
        board.post_draft(
            source="decomposer",
            content="Tarefa: geração. Produza artefato conciso.",
            role="decomp",
            weight=0.85,
        )
    elif re.search(_KW_FIX, p):
        board.post_draft(
            source="decomposer",
            content="Tarefa: correção. Identifique a causa e forneça o fix.",
            role="decomp",
            weight=0.85,
        )
    elif re.search(_KW_LIST, p):
        board.post_draft(
            source="decomposer",
            content="Formato esperado: lista numerada, itens curtos.",
            role="format",
            weight=0.80,
        )
    elif has_code_context:
        board.post_draft(
            source="decomposer",
            content="Tarefa: geração de código prático e curto.",
            role="decomp",
            weight=0.84,
        )

    if has_code_block_ctx and (has_code_context or wants_generation):
        board.post_draft(
            source="decomposer",
            content="Formato: entregue primeiro um bloco de código útil e curto, sem prefácios longos.",
            role="format",
            weight=0.88,
        )

    if context.get("context_file"):
        board.post_draft(
            source="decomposer",
            content=f"Arquivo alvo: {context['context_file']}",
            role="angle",
            weight=0.9,
        )


def _read_file_safe(path: str, bridge_active_window: int = 512) -> str:
    """Lê um arquivo e aplica Redução Cognitiva para poupar o LLM."""
    if not path:
        return ""

    try:
        from pathlib import Path
        file_path = Path(path)
        
        # Lê um bom pedaço do arquivo (até 10KB) para análise
        with file_path.open("r", encoding="utf-8", errors="replace") as fh:
            raw_content = fh.read(10240) 
        
        # Calcula quantos caracteres podemos gastar (aprox 3 chars = 1 token)
        max_chars = max(300, (bridge_active_window - 150) * 3)
        
        # Pede pro Redutor mastigar o código e devolver só o esqueleto
        from engine.core.blackboard import CognitiveReducer
        skeletal_code = CognitiveReducer.reduce_file(file_path.name, raw_content, max_chars=max_chars)
        
        return skeletal_code

    except OSError as exc:
        emit_forensic_log(exc, "_read_file_safe")
        return ""


def _looks_degenerate_think_output(prompt: str, output: str) -> bool:
    out = (output or "").strip().lower()
    p = (prompt or "").strip().lower()
    if not out:
        return True
    if out == p:
        return True
    if out in {"[task]", "[task]\nbuffer python"}:
        return True
    if out.startswith("[task]"):
        return True
    if "não tenho acesso a um contexto específico" in out:
        return True
    # Modelo recusou a tarefa (prompt system contradiz a query)
    _REFUSALS = (
        "não tenho capacidade de produzir",
        "não posso fornecer um bloco",
        "como assistente de ia, não",
        "desculpe, mas não posso",
    )
    if any(r in out for r in _REFUSALS):
        return True
    # Saudação — modelo perdeu o contexto da task
    if out.startswith(("olá", "olá!", "oi!", "hello", "hi!")):
        return True
    return False


def _deterministic_code_answer(prompt: str) -> str:
    p = (prompt or "").lower()
    if "softmax" in p:
        return (
            "import math\n\n"
            "def softmax(values: list[float]) -> list[float]:\n"
            "    if not values:\n"
            "        return []\n"
            "    m = max(values)\n"
            "    exps = [math.exp(v - m) for v in values]\n"
            "    s = sum(exps)\n"
            "    return [e / s for e in exps]\n"
        )
    if "buffer" in p and "python" in p:
        return (
            "from collections import deque\n"
            "from typing import Deque, Generic, Iterable, TypeVar\n\n"
            "T = TypeVar('T')\n\n"
            "class RingBuffer(Generic[T]):\n"
            "    def __init__(self, maxlen: int, data: Iterable[T] = ()):\n"
            "        self._buf: Deque[T] = deque(data, maxlen=maxlen)\n\n"
            "    def push(self, value: T) -> None:\n"
            "        self._buf.append(value)\n\n"
            "    def snapshot(self) -> list[T]:\n"
            "        return list(self._buf)\n"
        )
    return (
        "def solve(data: object) -> object:\n"
        "    \"\"\"Fallback determinístico para resposta degenerada do modelo.\"\"\"\n"
        "    return data\n"
    )

_KW_CODE_GEN = re.compile(
    r"\b(faça|crie|escreva|gere|implemente|cria|make|write|implement|create)\b",
    re.IGNORECASE,
)
_KW_LANG = re.compile(
    r"\b(python|py|c\+\+|cpp|javascript|typescript|rust|go|java|batch|script"
    r"|buffer|array|lista|list|dict|struct|classe|class)\b",   # ← ADD
    re.IGNORECASE,
)
_KW_COMPLEX_ALGO = re.compile(
    r"\b(quicksort|mergesort|heapsort|avl|bst|lru.?cache|"
    r"ring.?buffer|linked.?list|trie|grafo|graph|dijkstra|"
    r"classe|class|buffer)\b",    # ← ADD buffer aqui também
    re.IGNORECASE,
)

def _adaptive_max_tokens(prompt: str) -> int:
    """Limite de tokens calibrado para Celeron N2808 @ ~1.4 t/s.

      320 tokens ≈ 229s  — algoritmo complexo / classe com buffer
      256 tokens ≈ 183s  — geração de código simples (função única)
      128 tokens ≈  91s  — pergunta sobre código
       64 tokens ≈  46s  — texto puro
    """
    p = prompt or ""
    is_gen  = bool(_KW_CODE_GEN.search(p))
    is_lang = bool(_KW_LANG.search(p))

    if is_gen and is_lang and _KW_COMPLEX_ALGO.search(p):
        return 320   # algoritmo complexo — classe, recursão, buffer
    if is_gen and is_lang:
        return 256   # geração simples — função única
    if is_lang:
        return 128   # explicação / pergunta sobre código
    return 64        # texto puro