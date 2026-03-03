# -*- coding: utf-8 -*-
"""
ORN — LLM Bridge (Hefesto) — Fase 1: ATIVO
Interface com Qwen2.5-Coder via llama-cpp-python.

POLÍTICA DE MEMÓRIA (Relatório de Protótipo):
  - Modelo é SERVIÇO — sobe sob demanda, desce por shutdown() (TTL via Executive).
  - KV-cache controlado por ContextWindow (sliding window, §2.2).
  - Quantização INT4 resolvida no modelo escolhido (Q4_K_M).
  - n_gpu_layers: 0 = CPU-only (edge/desktop safe). Ajustar se VRAM disponível.
  - n_ctx = 2048: conservador; active_window = 1024: janela ativa do KV-cache.

  [ Executive ]
       |
  [ SiCDoxBridge ]
       |
  [ Llama (llama-cpp) ]
  |        |        |
  KV     Weights  Layers
 (ContextWindow)  (n_gpu_layers)

OSL-3:  _llm é None até _load(); liberado deterministicamente por shutdown().
OSL-4:  _build_prompt(), _call_engine(), ask() separados e curtos.
OSL-7:  Retorno de inferência verificado em ask() antes de repassar.
OSL-12: stats() expõe uso de memória para `orn brain`.
God: Hefesto — forja sob demanda; transforma prompt em artefato.

ARCHAEOLOGY NOTE (2026-02-01 layer 1) — recuperar na Fase 4:
    def generate_plan(self, user_intent: str, context_graph_snippet: str) -> str:
        prompt = (f'CONTEXTO ATUAL (TGF):\n{context_graph_snippet}\n\n'
                  f'INTENÇÃO DO ARQUITETO: {user_intent}')
        return self._call_engine(self._build_prompt(), self._cfg.max_tokens)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuração de memória
# ---------------------------------------------------------------------------

@dataclass
class BridgeConfig:
    """Parâmetros de controle de memória e inferência.

    Calibrado para Celeron N2808 (REP.INFRA.20260209.GOLD §4):
      - Sem AVX/AVX2: compilado com SSE4.2, -DGGML_OPENMP=OFF
      - n_threads=2: Dual-Core real — mais threads não ajudam sem OpenMP
      - Load time: ~80 segundos — NORMAL para este hardware
      - Performance: ~1.40 t/s após otimização SSE4.2
      - ttl_seconds=3600: recarregar custa 80s, manter em RAM o máximo possível
    """

    model_path:    Path = Path(
        "models/sicdox/Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF"
        "/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
    )
    n_ctx:         int  = 2048   # janela total do KV-cache (conservador)
    active_window: int  = 1024   # tokens ativos na sliding window

    # N2808: Dual-Core sem hyperthreading útil — 2 threads é o teto real
    n_threads:     int  = 2
    n_gpu_layers:  int  = 0      # CPU-only (sem GPU no N2808)

    # TTL longo: load custa ~80s — manter em RAM; só descarregar por necessidade
    ttl_seconds:   int  = 3600   # 1 hora (era 300s — inadequado para N2808)

    # max_tokens reduzido para testes — 679s foi causado por resposta gigante
    # Regra: 128 para testes rápidos, 512 para uso normal
    max_tokens:    int   = 512

    # Parâmetros de sampling (doc ORN_up — seção 3)
    # Qwen 0.5B alucina rápido com temperature alta — manter <= 0.6
    temperature:    float = 0.45
    top_p:          float = 0.85
    top_k:          int   = 40
    repeat_penalty: float = 1.1

    system_prompt: str  = (
        "You are ORN, a code assistant. "
        "Answer DIRECTLY and CONCISELY. "
        "No introductions. No examples unless asked. "
        "If asked for N lines, write exactly N lines. "
        "Respond in at most 5 items unless instructed otherwise. "
        "Never mix multiple tasks in one response. "
        "Prefer Python, C, C++, batch script. "
        "Respond in portuguese. "
        "Do not lie. Be honest and transparent. "
    )


# ---------------------------------------------------------------------------
# KV-cache — sliding window (Relatório §2.2)
# ---------------------------------------------------------------------------

class ContextWindow:
    """Gerencia histórico de contexto com sliding window.

    Descarta turns antigos quando estimativa de tokens ultrapassa max_tokens.
    Fase 1: estimativa por palavras. Fase 2: tokenizer real do llama.cpp.

    OSL-2: Crescimento da lista tem limite explícito.
    OSL-3: Sem alocação dinâmica além da lista inicial.
    OSL-6: get_turns() retorna cópia — não expõe referência interna.
    """

    def __init__(self, max_tokens: int = 1024) -> None:
        if max_tokens <= 0:
            raise ValueError("max_tokens deve ser positivo.")
        self._max    = max_tokens
        self._turns: list[dict[str, str]] = []
        self._count  = 0

    def push(self, role: str, content: str) -> None:
        """Adiciona mensagem, descartando turns antigos se necessário.

        OSL-5.1: Valida role e content antes de inserir.
        """
        if role not in ("user", "assistant", "system"):
            raise ValueError(f"role inválido: '{role}'")
        if not content:
            raise ValueError("content não pode ser vazio.")

        est = len(content.split())
        self._turns.append({"role": role, "content": content})
        self._count += est

        while self._count > self._max and len(self._turns) > 1:
            removed = self._turns.pop(0)
            self._count -= len(removed["content"].split())

    def get_turns(self) -> list[dict[str, str]]:
        return list(self._turns)

    def clear(self) -> None:
        self._turns.clear()
        self._count = 0

    def stats(self) -> dict[str, int]:
        return {"turns": len(self._turns), "token_est": self._count,
                "max_tokens": self._max}


# ---------------------------------------------------------------------------
# Bridge principal — Fase 1 ATIVO
# ---------------------------------------------------------------------------

class SiCDoxBridge:
    """Bridge com o modelo GGUF local.

    OSL-3: _llm = None até _load(); shutdown() libera deterministicamente.
    OSL-16: Métodos curtos e separados por responsabilidade.
    """

    def __init__(self, config: BridgeConfig | None = None) -> None:
        self._cfg: BridgeConfig  = config or BridgeConfig()
        self._llm: Any           = None
        self._ctx: ContextWindow = ContextWindow(self._cfg.active_window)
        self._load_time: Any     = None   # float | None — timestamp do load (OSL-12)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def ask(self, prompt: str, max_tokens: int | None = None) -> str:
        """Envia *prompt* ao modelo e retorna texto gerado.

        OSL-5.1: prompt não pode ser vazio.
        OSL-7: Resposta verificada antes de retornar ao Executive.

        Raises:
            ValueError:        prompt vazio.
            RuntimeError:      resposta vazia do modelo.
            FileNotFoundError: .gguf não encontrado.
        """
        if not prompt:
            raise ValueError("prompt não pode ser vazio.")

        self._ensure_loaded()
        self._ctx.push("user", prompt)

        texto = self._call_engine(
            self._build_prompt(),
            max_tokens or self._cfg.max_tokens
        )

        if not texto.strip():
            raise RuntimeError("Modelo retornou resposta vazia.")

        self._ctx.push("assistant", texto)
        return texto

    def shutdown(self) -> None:
        """Libera modelo da RAM. Idempotente. OSL-3.

        ATENÇÃO — Bug Python 3.12 (Relatório REP.INFRA.20260209.GOLD §5.2):
          O destruidor do objeto Llama falha com TypeError: NoneType se o
          objeto for coletado pelo GC sem .close() explícito.
          .close() DEVE ser chamado antes de self._llm = None.
        """
        if self._llm is not None:
            try:
                self._llm.close()
            except Exception:
                pass   # .close() pode falhar se já destruído — ignorar
            self._llm = None
        self._load_time = None
        # ContextWindow preservada para retomada de sessão.

    def clear_context(self) -> None:
        """Limpa histórico de contexto sem descarregar o modelo."""
        self._ctx.clear()

    def stats(self) -> dict[str, Any]:
        """Estado de memória para `orn brain`. OSL-12."""
        import time
        elapsed = None
        if self._load_time is not None:
            elapsed = round(time.monotonic() - self._load_time, 1)
        return {
            "model_loaded":      self._llm is not None,
            "model_path":        str(self._cfg.model_path),
            "loaded_since_s":    elapsed,   # segundos desde o load (None = descarregado)
            "context":           self._ctx.stats(),
            "config": {
                "n_ctx":         self._cfg.n_ctx,
                "active_window": self._cfg.active_window,
                "n_threads":     self._cfg.n_threads,
                "n_gpu_layers":  self._cfg.n_gpu_layers,
                "ttl_seconds":   self._cfg.ttl_seconds,
            },
        }

    # ------------------------------------------------------------------
    # Internos — OSL-4: cada método faz uma coisa
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._llm is None:
            self._load()

    def _load(self) -> None:
        """Carrega o modelo GGUF. Chamado apenas por _ensure_loaded().

        OSL-5.2: Verifica existência antes de abrir.

        HARDWARE: Celeron N2808 (REP.INFRA.20260209.GOLD)
          - Sem AVX/AVX2 — compilado com SSE4.2 apenas
          - Sem OpenMP — n_threads=2 (Dual-Core, sem hyperthreading útil)
          - Load time esperado: ~80 segundos — NORMAL para este hardware
          - Performance esperada: ~1.40 t/s (após otimização SSE4.2)
          - verbose=False: silencia output do llama.cpp no terminal
        """
        import time
        if not self._cfg.model_path.exists():
            raise FileNotFoundError(
                f"Modelo não encontrado: {self._cfg.model_path}\n"
                "Configure via `orn config --model <path>`."
            )

        from llama_cpp import Llama  # noqa: PLC0415
        self._llm = Llama(
            model_path   = str(self._cfg.model_path),
            n_ctx        = self._cfg.n_ctx,
            n_threads    = self._cfg.n_threads,
            n_gpu_layers = self._cfg.n_gpu_layers,
            verbose      = False,
        )
        self._load_time = time.monotonic()

    def _build_prompt(self) -> str:
        """Monta prompt ChatML com a janela de contexto ativa.

        Formato Qwen: <|im_start|>role\\ncontent<|im_end|>
        OSL-4: separado de ask() para facilitar variações de formato.
        """
        partes: list[str] = [
            f"<|im_start|>system\n{self._cfg.system_prompt}<|im_end|>"
        ]
        for turn in self._ctx.get_turns():
            partes.append(
                f"<|im_start|>{turn['role']}\n{turn['content']}<|im_end|>"
            )
        partes.append("<|im_start|>assistant\n")
        return "\n".join(partes)

    def _call_engine(self, prompt: str, max_tokens: int) -> str:
        """Chama o runtime Llama e retorna texto cru.

        OSL-7: Chamador (ask) verifica o retorno — este método só chama.
        """
        if self._llm is None:
            raise RuntimeError("Modelo não carregado.")

        output = self._llm(
            prompt,
            max_tokens     = max_tokens,
            stop           = ["<|im_end|>", "</s>"],
            echo           = False,
            temperature    = self._cfg.temperature,
            top_p          = self._cfg.top_p,
            top_k          = self._cfg.top_k,
            repeat_penalty = self._cfg.repeat_penalty,
        )
        return output["choices"][0]["text"]