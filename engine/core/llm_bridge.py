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
import time
import os
import json
from typing import Any
from pathlib import Path
from dataclasses import dataclass
from engine.telemetry.runtime import record_direct  # noqa: PLC0415
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
        #"/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
    )
    n_ctx:         int  = 256   # era 2048 — reduz KV-cache pela metade
    active_window: int  = 256    # era 1024 — proporcional
    n_batch:       int  = 256     # NOVO — era 512 (default llama.cpp)
                                  # 64 = menos pressão de memória no N2808
                                  
    # N2808: Dual-Core sem hyperthreading útil — 2 threads é o teto real
    n_threads:       int = 2
    n_threads_batch: int = 2
    n_gpu_layers:    int = 0      # CPU-only (sem GPU no N2808)
    use_mmap: bool = True   # mmap para pesos (carregamento preguiçoso)
    use_mlock: bool = True # Trava o modelo na RAM (impede o Windows de jogar pro swap/disco)
    no_alloc: bool = False # Evita alocação interna inicial quando suportado pelo backend
    pin_threads: bool = False # Fixa threads em núcleos quando suportado
    cont_batching: bool = False # Continuous batching quando suportado
    # n_threads_batch=2 # (Disponível nas versões mais recentes do wrapper python)
    # TTL longo: load custa ~80s — manter em RAM; só descarregar por necessidade
    ttl_seconds:   int  = 400   # 1 hora (era 300s — inadequado para N2808)
    # max_tokens reduzido para testes — 679s foi causado por resposta gigante
    # Regra: 128 para testes rápidos, 512 para uso normal
    max_tokens:    int   = 32
    # Parâmetros de sampling (doc ORN_up — seção 3)
    # Qwen 0.5B alucina rápido com temperature alta — manter <= 0.6
    temperature:    float = 0.45
    top_p:          float = 0.85
    top_k:          int   = 35
    repeat_penalty: float = 1.1
    min_p:          float = 0.01
    # Menemonização de repetições (com pruning LRU)
    repetition_memo_enabled: bool = True
    repetition_memo_size:    int  = 32
    # Context rotation + compactação para conversas longas
    context_rotation: bool = True
    context_compact_ratio: float = 0.5
    # Quantização do KV-cache (llama.cpp): ex. f16, q8_0, q4_0
    cache_type_k: str | None = None
    cache_type_v: str | None = None
    # Parâmetros RoPE para ajuste de extrapolação/contexto
    rope_freq_base: float | None = None
    rope_freq_scale: float | None = None
    # Flash Attention (quando suportado pelo backend/llama.cpp)
    flash_attn: bool | None = None
    system_prompt: str = ("succinct assistant. tightening writing. PTBR.")  # era ~170 tokens, agora ~20 tokens
    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().strip('"').strip("'")
        if not cleaned:
            return None
        if cleaned.lower() in {"none", "null", "off", "disable", "disabled", "false"}:
            return None
        return cleaned
    @classmethod
    def _normalize_optional_float(cls, value: str | None) -> float | None:
        cleaned = cls._normalize_optional_text(value)
        if cleaned is None:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    @staticmethod
    def _normalize_optional_bool(value: str | bool | None) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        cleaned = value.strip().strip('"').strip("'").lower()
        if cleaned in {"", "none", "null", "off", "disable", "disabled"}:
            return None
        if cleaned in {"1", "true", "yes", "on", "enable", "enabled"}:
            return True
        if cleaned in {"0", "false", "no"}:
            return False
        return None
    def __post_init__(self) -> None:
        # Normaliza valores opcionais recebidos no construtor.
        self.cache_type_k = self._normalize_optional_text(self.cache_type_k)
        self.cache_type_v = self._normalize_optional_text(self.cache_type_v)
        self.rope_freq_base = self._normalize_optional_float(str(self.rope_freq_base)) if self.rope_freq_base is not None else None
        self.rope_freq_scale = self._normalize_optional_float(str(self.rope_freq_scale)) if self.rope_freq_scale is not None else None
        self.flash_attn = self._normalize_optional_bool(self.flash_attn)
        # Normaliza bools de infra/memória.
        self.use_mmap = bool(self.use_mmap)
        self.no_alloc = bool(self.no_alloc)
        self.pin_threads = bool(self.pin_threads)
        self.cont_batching = bool(self.cont_batching)
        self.repetition_memo_enabled = bool(self.repetition_memo_enabled)
        if self.repetition_memo_size <= 0:
            self.repetition_memo_size = 1
        self.context_rotation = bool(self.context_rotation)
        if self.context_compact_ratio <= 0:
            self.context_compact_ratio = 0.5
        if self.context_compact_ratio >= 1:
            self.context_compact_ratio = 0.9
        # Overrides opcionais por ambiente para tuning sem alterar código.
        env_active_window = os.environ.get("ORN_ACTIVE_WINDOW", "").strip()
        if env_active_window:
            try:
                self.active_window = int(env_active_window)
            except ValueError:
                pass
        env_cache_k = os.environ.get("ORN_CACHE_TYPE_K")
        env_cache_v = os.environ.get("ORN_CACHE_TYPE_V")
        self.cache_type_k = self._normalize_optional_text(env_cache_k) if env_cache_k is not None else self.cache_type_k
        self.cache_type_v = self._normalize_optional_text(env_cache_v) if env_cache_v is not None else self.cache_type_v
        env_rope_base = os.environ.get("ORN_ROPE_FREQ_BASE")
        env_rope_scale = os.environ.get("ORN_ROPE_FREQ_SCALE")
        self.rope_freq_base = self._normalize_optional_float(env_rope_base) if env_rope_base is not None else self.rope_freq_base
        self.rope_freq_scale = self._normalize_optional_float(env_rope_scale) if env_rope_scale is not None else self.rope_freq_scale
        env_flash_attn = os.environ.get("ORN_FLASH_ATTN")
        self.flash_attn = self._normalize_optional_bool(env_flash_attn) if env_flash_attn is not None else self.flash_attn
        env_use_mmap = os.environ.get("ORN_USE_MMAP")
        parsed_use_mmap = self._normalize_optional_bool(env_use_mmap) if env_use_mmap is not None else None
        if parsed_use_mmap is not None:
            self.use_mmap = parsed_use_mmap
        env_no_alloc = os.environ.get("ORN_NO_ALLOC")
        parsed_no_alloc = self._normalize_optional_bool(env_no_alloc) if env_no_alloc is not None else None
        if parsed_no_alloc is not None:
            self.no_alloc = parsed_no_alloc
        env_pin_threads = os.environ.get("ORN_PIN_THREADS")
        parsed_pin_threads = self._normalize_optional_bool(env_pin_threads) if env_pin_threads is not None else None
        if parsed_pin_threads is not None:
            self.pin_threads = parsed_pin_threads
        env_cont_batching = os.environ.get("ORN_CONT_BATCHING")
        parsed_cont_batching = self._normalize_optional_bool(env_cont_batching) if env_cont_batching is not None else None
        if parsed_cont_batching is not None:
            self.cont_batching = parsed_cont_batching
        env_min_p = os.environ.get("ORN_MIN_P", "").strip()
        if env_min_p:
            try:
                self.min_p = float(env_min_p)
            except ValueError:
                pass
        env_memo = os.environ.get("ORN_REPETITION_MEMO")
        parsed_memo = self._normalize_optional_bool(env_memo) if env_memo is not None else None
        if parsed_memo is not None:
            self.repetition_memo_enabled = parsed_memo
        env_memo_size = os.environ.get("ORN_REPETITION_MEMO_SIZE", "").strip()
        if env_memo_size:
            try:
                self.repetition_memo_size = max(1, int(env_memo_size))
            except ValueError:
                pass
        env_rotation = os.environ.get("ORN_CONTEXT_ROTATION")
        parsed_rotation = self._normalize_optional_bool(env_rotation) if env_rotation is not None else None
        if parsed_rotation is not None:
            self.context_rotation = parsed_rotation
        env_compact = os.environ.get("ORN_CONTEXT_COMPACT_RATIO", "").strip()
        if env_compact:
            try:
                ratio = float(env_compact)
                if 0 < ratio < 1:
                    self.context_compact_ratio = ratio
            except ValueError:
                pass
        if self.active_window <= 0:
            self.active_window = 1
        if self.active_window > self.n_ctx:
            self.active_window = self.n_ctx
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
    def __init__(self, max_tokens: int = 1024, rotation: bool = True, compact_ratio: float = 0.5) -> None:
        if max_tokens <= 0:
            raise ValueError("max_tokens deve ser positivo.")
        self._max    = max_tokens
        self._turns: list[dict[str, str]] = []
        self._count  = 0
        self._rotation = rotation
        self._compact_ratio = compact_ratio if 0 < compact_ratio < 1 else 0.5
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
            if self._compact_old_turns():
                if self._count <= self._max:
                    break
                continue
            removed = self._turns.pop(0)
            self._count -= len(removed["content"].split())
    def _compact_old_turns(self) -> bool:
        if not self._rotation:
            return False
        if len(self._turns) < 4:
            return False
        keep = max(2, int(len(self._turns) * self._compact_ratio))
        old = self._turns[:-keep]
        if len(old) < 2:
            return False
        bullets: list[str] = []
        for t in old[-4:]:
            snippet = " ".join(t["content"].split()[:8]).strip()
            if snippet:
                bullets.append(f"- {t['role']}: {snippet}")
        if not bullets:
            return False
        summary = "[CTX-ROTATION] Resumo compacto de turns antigos:\n" + "\n".join(bullets)
        self._turns = [{"role": "system", "content": summary}] + self._turns[-keep:]
        self._count = sum(len(t["content"].split()) for t in self._turns)
        return True
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
        self._ctx: ContextWindow = ContextWindow(
            self._cfg.active_window,
            rotation=self._cfg.context_rotation,
            compact_ratio=self._cfg.context_compact_ratio,
        )
        self._load_time: Any     = None   # float | None — timestamp do load (OSL-12)
        self._memo: dict[str, str] = {}
        self._memo_order: list[str] = []
    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def ask(self, prompt: str, max_tokens: int | None = None) -> str:
        if not prompt:
            raise ValueError("prompt não pode ser vazio.")
        self._ensure_loaded()
        self._ctx.push("user", prompt)
        max_tokens = max_tokens or self._cfg.max_tokens
        memo_answer = self._memo_get(prompt)
        if memo_answer is not None:
            self._ctx.push("assistant", memo_answer)
            return memo_answer
        # marks
        t_start = time.perf_counter()
        # optional: mark model load time elsewhere if needed
        # prompt eval isn't synchronous in llama.cpp — but keep a metric for completeness
        t_prompt_eval_start = time.perf_counter()
        built = self._build_prompt()
        t_prompt_eval_end = time.perf_counter()
        t_gen_start = time.perf_counter()
        resp = self._call_engine(built, max_tokens)
        t_gen_end = time.perf_counter()
        text = resp["text"]
        usage = resp.get("usage", {})
        # computed metrics
        infer_elapsed = t_gen_end - t_gen_start
        prompt_eval = t_prompt_eval_end - t_prompt_eval_start
        total_elapsed = time.perf_counter() - t_start
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
        tokens_per_second = 0.0
        if infer_elapsed > 0:
            tokens_per_second = completion_tokens / infer_elapsed
        # push assistant turn and return
        if text is None or not text.strip():
            raise RuntimeError("Modelo retornou resposta vazia.")
        self._ctx.push("assistant", text)
        self._memo_put(prompt, text)
        # telemetry payload (consistent schema)
        telemetry = {
            "mode": "direct",
            "model": self._cfg.model_path.name,
            "n_ctx": self._cfg.n_ctx,
            "n_threads": self._cfg.n_threads,
            "n_threads_batch": self._cfg.n_threads_batch,
            "prompt_chars": len(prompt),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "prompt_eval_s": round(prompt_eval, 3),
            "infer_s": round(infer_elapsed, 3),
            "total_s": round(total_elapsed, 3),
            "tokens_per_second": round(tokens_per_second, 3),
            "context_turns": len(self._ctx.get_turns()),
            "max_tokens": max_tokens,
            "system_prompt": self._cfg.system_prompt,
            "repeat_penalty": self._cfg.repeat_penalty,
            "min_p": self._cfg.min_p,
            "temperature": self._cfg.temperature,
            "llm_call_ms": resp.get("llm_call_ms"),
        } 
        # "": self._cfg.,
        try:
            record_direct(telemetry)
        except Exception:
            # never fail user flow: telemetry write must be fail-silent
            pass
        return text
    def _log_runtime(self, data: dict):
        path = Path("telemetry/direct_runtime.jsonl")
        with path.open("a", encoding="utf8") as f:
            f.write(json.dumps(data) + "\n")
    def _memo_key(self, prompt: str) -> str:
        return " ".join(prompt.lower().split())
    def _memo_get(self, prompt: str) -> str | None:
        if not self._cfg.repetition_memo_enabled:
            return None
        key = self._memo_key(prompt)
        return self._memo.get(key)
    def _memo_put(self, prompt: str, answer: str) -> None:
        if not self._cfg.repetition_memo_enabled:
            return
        key = self._memo_key(prompt)
        if key in self._memo:
            self._memo[key] = answer
            return
        self._memo[key] = answer
        self._memo_order.append(key)
        while len(self._memo_order) > self._cfg.repetition_memo_size:
            oldest = self._memo_order.pop(0)
            self._memo.pop(oldest, None)
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
                "cache_type_k":   self._cfg.cache_type_k,
                "cache_type_v":   self._cfg.cache_type_v,
                "rope_freq_base": self._cfg.rope_freq_base,
                "rope_freq_scale": self._cfg.rope_freq_scale,
                "flash_attn": self._cfg.flash_attn,
                "use_mmap": self._cfg.use_mmap,
                "no_alloc": self._cfg.no_alloc,
                "pin_threads": self._cfg.pin_threads,
                "cont_batching": self._cfg.cont_batching,
                "min_p": self._cfg.min_p,
                "repetition_memo_enabled": self._cfg.repetition_memo_enabled,
                "repetition_memo_size": self._cfg.repetition_memo_size,
                "context_rotation": self._cfg.context_rotation,
                "context_compact_ratio": self._cfg.context_compact_ratio,
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
        kwargs = {
            "model_path": str(self._cfg.model_path),
            "n_ctx": self._cfg.n_ctx,
            "n_threads": self._cfg.n_threads,
            "n_threads_batch": self._cfg.n_threads_batch,
            "n_gpu_layers": self._cfg.n_gpu_layers,
            "n_batch": self._cfg.n_batch,
            "use_mmap": self._cfg.use_mmap,
            "use_mlock": self._cfg.use_mlock,
            "verbose": False,
        }
        if self._cfg.cache_type_k:
            kwargs["type_k"] = self._cfg.cache_type_k
        if self._cfg.cache_type_v:
            kwargs["type_v"] = self._cfg.cache_type_v
        if self._cfg.rope_freq_base is not None:
            kwargs["rope_freq_base"] = self._cfg.rope_freq_base
        if self._cfg.rope_freq_scale is not None:
            kwargs["rope_freq_scale"] = self._cfg.rope_freq_scale
        if self._cfg.flash_attn is not None:
            kwargs["flash_attn"] = self._cfg.flash_attn
        if self._cfg.no_alloc:
            kwargs["no_alloc"] = True
        if self._cfg.pin_threads:
            kwargs["pin_threads"] = True
        if self._cfg.cont_batching:
            kwargs["cont_batching"] = True
        try:
            self._llm = Llama(**kwargs)
        except TypeError as exc:
            msg = str(exc)
            unsupported = ("type_k", "type_v", "rope_freq_base", "rope_freq_scale", "flash_attn", "no_alloc", "use_mmap", "pin_threads", "cont_batching")
            if not any(token in msg for token in unsupported):
                raise
            for token in unsupported:
                kwargs.pop(token, None)
            self._llm = Llama(**kwargs)
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
    def _call_engine(self, prompt: str, max_tokens: int) -> dict:
        """Chama o runtime Llama e retorna dict: {'text': str, 'usage': {...}}"""
        if self._llm is None:
            raise RuntimeError("Modelo não carregado.")
        t0 = time.perf_counter()
        call_kwargs = {
            "max_tokens": max_tokens,
            "stop": ["<|im_end|>", "</s>"],
            "echo": False,
            "temperature": self._cfg.temperature,
            "top_p": self._cfg.top_p,
            "top_k": self._cfg.top_k,
            "min_p": self._cfg.min_p,
            "repeat_penalty": self._cfg.repeat_penalty,
        }
        try:
            output = self._llm(prompt, **call_kwargs)
        except TypeError as exc:
            if "min_p" not in str(exc):
                raise
            call_kwargs.pop("min_p", None)
            output = self._llm(prompt, **call_kwargs)
        llm_ms = (time.perf_counter() - t0) * 1000.0
        text = output["choices"][0]["text"]
        usage = output.get("usage", {}) or {}
        # normalize usage keys for compat
        usage = {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", usage.get("completion_tokens", 0) or usage.get("completion_tokens")),
            "total_tokens": usage.get("total_tokens", usage.get("total_tokens", 0)),
        }
        return {"text": text, "usage": usage, "llm_call_ms": round(llm_ms, 3)}
