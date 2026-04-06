# -*- coding: utf-8 -*-
# engine\core\llm_bridge.py
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
from collections import deque

import time
import os
import json

from typing                   import Any
from pathlib                  import Path
from dataclasses              import dataclass
from engine.core.cpu_affinity import apply_process_affinity
from engine.telemetry.runtime import record_direct  # noqa: PLC0415
from engine.core.prompt_utils import pitstop        # noqa: PLC0415
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
        "models/sicdox/Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
        #"/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
    )
    memory_profile:          str  = "default"  # default|low (env: ORN_MEMORY_PROFILE)
    n_ctx:                   int  = 1024   # era 2048 — reduz KV-cache pela metade
    active_window:           int  = 256    # era 1024 — proporcional
    n_batch:                 int  = 64     # NOVO — era 512 (default llama.cpp)
                                 # 64 = menos pressão de memória no N2808
    # N2808: Dual-Core sem hyperthreading útil — 2 threads é o teto real
    n_threads:               int = 2 #n_threads:               int = 2
    n_threads_batch:         int = 2
    n_gpu_layers:            int = 0     # CPU-only (sem GPU no N2808)
    use_mmap: bool =         True        # mmap para pesos (carregamento preguiçoso)
    use_mlock: bool =        True       # Trava o modelo na RAM (impede o Windows de jogar pro swap/disco)
    no_alloc: bool =         True        # Evita alocação interna inicial quando suportado pelo backend
    pin_threads: bool =      False     # Fixa threads em núcleos quando suportado
    cont_batching: bool =    True   # Continuous batching quando suportado
    cpu_mask: str | None =   None
    cpuset: str | None =     None
    # n_threads_batch=2 # (Disponível nas versões mais recentes do wrapper python)
    # TTL longo: load custa ~80s — manter em RAM; só descarregar por necessidade
    ttl_seconds:   int  =    400   # 1 hora (era 300s — inadequado para N2808)
    # max_tokens reduzido para testes — 679s foi causado por resposta gigante
    # Regra: 128 para testes rápidos, 512 para uso normal
    max_tokens:    int   =   512
    response_hard_limit: int = 2048
    # Parâmetros de sampling (doc ORN_up — seção 3)
    # Qwen 0.5B alucina rápido com temperature alta — manter <= 0.6
    temperature:    float =  0.40
    top_p:          float =  0.80 #top_p:          float =  0.85
    top_k:          int   =  20   #top_k:          int   =  35
    repeat_penalty: float =  1.05
    min_p:          float =  0.01 #min_p:          float =  0.05 ou None
    # Menemonização de repetições (com pruning LRU)
    repetition_memo_enabled: bool = True
    repetition_memo_size:    int  = 128
    # Context rotation + compactação para conversas longas
    context_rotation: bool = True
    context_compact_ratio:   float = 0.7
    # Quantização do KV-cache (llama.cpp): ex. f16, q8_0, q4_0
    cache_type_k: q8_0 | None = None
    cache_type_v: q8_0 | None = None
    # Parâmetros RoPE para ajuste de extrapolação/contexto
    rope_freq_base:  float | None = 1_000_000.0 #rope_freq_base: float | None = None
    rope_freq_scale: float | None = None
    # Flash Attention (quando suportado pelo backend/llama.cpp)
    flash_attn: True | None = None
    system_prompt: str = ("succinct. portuguese language") # system_prompt: str = "" 
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
        except ValueError as e:
            import sys as _dox_sys, os as _dox_os
            exc_type, exc_obj, exc_tb = _dox_sys.exc_info()
            f_name = _dox_os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] if exc_tb else "Unknown"
            line_n = exc_tb.tb_lineno if exc_tb else 0
            print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: _analyze_layer\033[0m\n\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033[0m")
            return None
    @staticmethod
    def _normalize_memory_profile(value: str | None) -> str:
        if value is None:
            return "default"
        cleaned = value.strip().strip('"').strip("'").lower()
        if cleaned in {"", "default", "normal", "std"}:
            return "default"
        if cleaned in {"low", "low-memory", "low_memory", "ram", "minimal"}:
            return "low"
        return "default"

    def _apply_memory_profile_defaults(self) -> None:
        if self.memory_profile != "low":
            return
        self.use_mlock = False
        self.n_batch = min(self.n_batch, 64)
        self.active_window = min(self.active_window, 192)
        self.ttl_seconds = min(self.ttl_seconds, 120)

    def effective_memory_flags(self) -> dict[str, Any]:
        return {
            "memory_profile": self.memory_profile,
            "use_mmap": self.use_mmap,
            "use_mlock": self.use_mlock,
            "no_alloc": self.no_alloc,
            "pin_threads": self.pin_threads,
            "cont_batching": self.cont_batching,
            "cpu_mask": self.cpu_mask,
            "cpuset": self.cpuset,
            "n_batch": self.n_batch,
            "active_window": self.active_window,
            "ttl_seconds": self.ttl_seconds,
        }

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
        self.cpu_mask = self._normalize_optional_text(self.cpu_mask)
        self.cpuset = self._normalize_optional_text(self.cpuset)
        self.rope_freq_base = self._normalize_optional_float(str(self.rope_freq_base)) if self.rope_freq_base is not None else None
        self.rope_freq_scale = self._normalize_optional_float(str(self.rope_freq_scale)) if self.rope_freq_scale is not None else None
        self.flash_attn = self._normalize_optional_bool(self.flash_attn)
        # Normaliza bools de infra/memória.
        self.use_mmap = bool(self.use_mmap)
        self.use_mlock = bool(self.use_mlock)
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
        # Perfil de memória (default|low) com overrides finos preservados por env.
        self.memory_profile = self._normalize_memory_profile(self.memory_profile)
        env_memory_profile = os.environ.get("ORN_MEMORY_PROFILE")
        if env_memory_profile is not None:
            self.memory_profile = self._normalize_memory_profile(env_memory_profile)
        self._apply_memory_profile_defaults()

        # Overrides opcionais por ambiente para tuning sem alterar código.
        env_active_window = os.environ.get("ORN_ACTIVE_WINDOW", "").strip()
        if env_active_window:
            try:
                self.active_window = int(env_active_window)
            except ValueError as e:
                import sys as _dox_sys, os as _dox_os
                exc_type, exc_obj, exc_tb = _dox_sys.exc_info()
                f_name = _dox_os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] if exc_tb else "Unknown"
                line_n = exc_tb.tb_lineno if exc_tb else 0
                print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: _analyze_layer\033[0m\n\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033[0m")
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
        elif env_use_mmap is not None:
            # inválido => fallback seguro (mantém carregamento estável)
            self.use_mmap = True
        env_use_mlock = os.environ.get("ORN_USE_MLOCK")
        parsed_use_mlock = self._normalize_optional_bool(env_use_mlock) if env_use_mlock is not None else None
        if parsed_use_mlock is not None:
            self.use_mlock = parsed_use_mlock
        elif env_use_mlock is not None:
            self.use_mlock = False

        env_no_alloc = os.environ.get("ORN_NO_ALLOC")
        parsed_no_alloc = self._normalize_optional_bool(env_no_alloc) if env_no_alloc is not None else None
        if parsed_no_alloc is not None:
            self.no_alloc = parsed_no_alloc
        elif env_no_alloc is not None:
            # inválido => fallback compatível (evita no_alloc inesperado)
            self.no_alloc = False
        env_pin_threads = os.environ.get("ORN_PIN_THREADS")
        parsed_pin_threads = self._normalize_optional_bool(env_pin_threads) if env_pin_threads is not None else None
        if parsed_pin_threads is not None:
            self.pin_threads = parsed_pin_threads
        elif env_pin_threads is not None:
            self.pin_threads = False
        env_cont_batching = os.environ.get("ORN_CONT_BATCHING")
        parsed_cont_batching = self._normalize_optional_bool(env_cont_batching) if env_cont_batching is not None else None
        if parsed_cont_batching is not None:
            self.cont_batching = parsed_cont_batching
        elif env_cont_batching is not None:
            self.cont_batching = False
        env_cpu_mask = os.environ.get("ORN_CPU_MASK")
        env_cpuset = os.environ.get("ORN_CPUSET")
        self.cpu_mask = self._normalize_optional_text(env_cpu_mask) if env_cpu_mask is not None else self.cpu_mask
        self.cpuset = self._normalize_optional_text(env_cpuset) if env_cpuset is not None else self.cpuset
        env_min_p = os.environ.get("ORN_MIN_P", "").strip()
        if env_min_p:
            try:
                self.min_p = float(env_min_p)
            except ValueError as e:
                import sys as _dox_sys, os as _dox_os
                exc_type, exc_obj, exc_tb = _dox_sys.exc_info()
                f_name = _dox_os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] if exc_tb else "Unknown"
                line_n = exc_tb.tb_lineno if exc_tb else 0
                print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: _analyze_layer\033[0m\n\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033[0m")
                self.min_p = 0.01
        env_response_hard_limit = os.environ.get("ORN_RESPONSE_HARD_LIMIT", "").strip()
        if env_response_hard_limit:
            try:
                parsed = int(env_response_hard_limit)
                if parsed > 0:
                    self.response_hard_limit = parsed
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
            except ValueError as e:
                import sys as _dox_sys, os as _dox_os
                exc_type, exc_obj, exc_tb = _dox_sys.exc_info()
                f_name = _dox_os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] if exc_tb else "Unknown"
                line_n = exc_tb.tb_lineno if exc_tb else 0
                print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: _analyze_layer\033[0m\n\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033[0m")
                self.repetition_memo_size = 32

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
            except ValueError as e:
                import sys as _dox_sys, os as _dox_os
                exc_type, exc_obj, exc_tb = _dox_sys.exc_info()
                f_name = _dox_os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] if exc_tb else "Unknown"
                line_n = exc_tb.tb_lineno if exc_tb else 0
                print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: _analyze_layer\033[0m\n\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033[0m")

        if self.n_batch <= 0:
            self.n_batch = 1
        if self.ttl_seconds <= 0:
            self.ttl_seconds = 30
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
        self._system_tokens = None
        self._memo: dict[str, tuple[str, float]] = {}
        self._memo_order: deque[str] = deque()

    def push(self, role: str, content: str) -> None:
        """Adiciona mensagem, descartando turns antigos se necessário.
        OSL-5.1: Valida role e content antes de inserir.
        """
        if role not in ("user", "assistant", "system"):
            raise ValueError(f"role inválido: '{role}'")
        if not content:
            raise ValueError("content não pode ser vazio.")
        est = len(content) >> 2
#TESTAR        est = (len(content) + 3) >> 2
#TESTAR        est = max(1, len(content) // 4)
#TESTAR        est= max(1, int(len(content) / 3.8))
        self._turns.append({"role": role, "content": content})
        self._count += est
        while self._count > self._max and len(self._turns) > 1:
            if self._compact_old_turns():
                if self._count <= self._max:
                    break
                continue
            removed = self._turns.pop(0)
            # self._count -= max(1, len(removed["content"]) // 4)
            # self._count -= len(removed["content"].split())
            self._count -= len(removed["content"]) >> 2
#            self._count -= (len(removed["content"]) + 3) >> 2
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
        for i in range(max(0, len(old)-4), len(old)):
            t = old[i]
            snippet = t["content"][:80].replace("\n", " ")  # FIX: era self._turns[0] — sempre o mesmo turn
            if snippet:
                bullets.append(f"- {t['role']}: {snippet}")
        if not bullets:
            return False
        summary = "[CTX-ROTATION] Resumo compacto de turns antigos:\n" + "\n".join(bullets)
        self._turns = [{"role": "system", "content": summary}] + self._turns[-keep:]
        self._count = 0
        for t in self._turns:
            self._count += len(t["content"]) >> 2
        return True
    def get_turns(self) -> list[dict[str, str]]:
        return list(self._turns)
    def _view_turns(self):
        return self._turns
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
        self._affinity_applied = False
        
        self._native: Any = None
        if os.environ.get("ORN_NATIVE_BACKEND", "").lower() in {"1", "true", "on"}:
            from engine.core.native_backend import NativeBackend
            dll = Path(__file__).parent.parent.parent / "native" / "orn.dll"
            self._native = NativeBackend(
                dll_path   = dll,
                model_path = self._cfg.model_path,
                n_ctx      = self._cfg.n_ctx,
                n_threads  = self._cfg.n_threads,
            )
        
        self._llm: Any           = None
        self._ctx: ContextWindow = ContextWindow(
            self._cfg.active_window,
            rotation=self._cfg.context_rotation,
            compact_ratio=self._cfg.context_compact_ratio,
        )
        self._load_time: Any     = None
        self._memo: dict[str, str] = {}
        # deque com maxlen: popleft() é O(1) vs list.pop(0) que é O(n)
        self._memo_order: deque[str] = deque()
        self._system_hint: str   = ""
        self._last_prompt: str = ""
        self._system_tokens: Any = None
        self._system_prefix = (
            "<|im_start|>system\n"
            + self._cfg.system_prompt +
            "<|im_end|>\n"
        )
        
        # Profiler de inferência fina (Cronos) — fail-silent por design
        try:
            from engine.telemetry.profiler import InferenceProfiler  # noqa: PLC0415
            self._prof: Any = InferenceProfiler()
        except Exception:
            self._prof = None
        
    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    class _NullSpan:
        """Context manager inerte — substitui prof.span() quando prof é None.
        Evita os 6 blocos `if prof is not None / else` em ask().
        """
        __slots__ = ()
        def __enter__(self): return self
        def __exit__(self, *_): pass

    _NULL_SPAN = _NullSpan()

    def ask(self, prompt: str, max_tokens: int | None = None,
            token_hint: int | None = None,
            system_hint: str | None = None) -> str:
        """Executa inferência.

        Args:
            prompt:      Texto do usuário (query pura — sem bloco de síntese).
            max_tokens:  Limite de tokens de saída. Usa config se None.
            token_hint:  Estimativa de tokens do prompt completo (chars//3).
                         Ajusta active_window dinamicamente sem reload.
            system_hint: Instruções extras para o system prompt desta chamada
                         (ex: bloco de síntese da lousa). Não persiste entre
                         chamadas — descartado após _build_prompt().
                         Colocar aqui evita que o modelo ecoe as tags no output.
        """
        if not prompt:
            raise ValueError("prompt não pode ser vazio.")

        MAX_PROMPT_CHARS = 1200  # HARD LIMIT REAL

        if len(prompt) > MAX_PROMPT_CHARS:
            prompt = prompt[-MAX_PROMPT_CHARS:]  # mantém parte mais recente

        max_tokens = max_tokens or self._cfg.max_tokens
        self._system_hint = system_hint or ""

        # ③ Inference Pitstop — limpa prompt e ajusta max_tokens ANTES de
        #   qualquer operação cara (load, push no ctx, build prompt).
        #   Inclui: ④ Remove Redundant Terms + ② Compression.

        # llm_bridge.py — linha ~414, após o pitstop
        #prompt, max_tokens = pitstop(prompt, max_tokens, active_window=self._cfg.active_window)
        prompt, _ = pitstop(prompt, max_tokens, active_window=self._cfg.active_window)
        print(f"[DEBUG] após pitstop: max_tokens={max_tokens}", flush=True)  # ← temporário

        # ── Profiler: inicia sessão de medição ─────────────────────────
        prof = self._prof
        _span = prof.span if prof is not None else lambda _: self._NULL_SPAN
        if prof is not None:
            prof.begin(
                query_chars       = len(prompt),
                system_hint_chars = len(self._system_hint),
                token_hint        = token_hint,
            )

        # ── load_check ─────────────────────────────────────────────────
        with _span("load_check"):
            self._ensure_loaded()

        t_start = time.perf_counter()

        # ── memo_lookup ────────────────────────────────────────────────
        memo_hit = False
        with _span("memo_lookup"):
            memo_answer = self._memo_get(prompt)

        # ── ctx_push (com active_window dinâmico) ─────────────────────
        effective_window = self._ctx._max
        if token_hint is not None and token_hint > 0:
            needed           = token_hint + max_tokens + 32
            effective_window = max(32, min(self._ctx._max, needed))
            old_max          = self._ctx._max
            self._ctx._max   = effective_window
            with _span("ctx_push"):
                self._ctx.push("user", prompt)
            self._ctx._max = old_max
        else:
            with _span("ctx_push"):
                self._ctx.push("user", prompt)

        if memo_answer is not None:
            memo_hit = True
            self._ctx.push("assistant", memo_answer)
            if prof is not None:
                prof.finish(
                    usage               = {"prompt_tokens": 0, "completion_tokens": 0},
                    active_window_used  = effective_window,
                    active_window_cfg   = self._cfg.active_window,
                    context_turns       = len(self._ctx._turns),
                    memo_hit            = True,
                    hw                  = {"n_ctx": self._cfg.n_ctx,
                                           "n_threads": self._cfg.n_threads,
                                           "n_gpu_layers": self._cfg.n_gpu_layers},
                )
            return memo_answer

        # ── prompt_build ───────────────────────────────────────────────
        with _span("prompt_build"):
            token_ids = self._build_prompt_tokens()  # lista de int ou None
            if token_ids is None:
                # Fallback: string (versão original — zero risco)
                built: str | list[int] = self._build_prompt()
            else:
                built = token_ids  # passa lista de tokens diretamente
        self._system_hint = ""

        # ── llm_call ───────────────────────────────────────────────────
        with _span("llm_call"):
            resp = self._call_engine(built, max_tokens)

        # ── text_parse ─────────────────────────────────────────────────
        with _span("text_parse"):
            text  = resp["text"]
            usage = resp.get("usage", {})

        if text is None or not text.strip():
            raise RuntimeError("Modelo retornou resposta vazia.")

        # computed metrics (mantidos para telemetria existente)
        t_end             = time.perf_counter()
        infer_elapsed     = t_end - t_start
        #prompt_tokens     = int(usage.get("prompt_tokens", 0) or 0)
        prompt_tokens     = usage.get("prompt_tokens") or 0
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        total_tokens      = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
        tokens_per_second = round(completion_tokens / infer_elapsed, 3) if infer_elapsed > 0 else 0.0

        self._ctx.push("assistant", text)

        # ── memo_store ─────────────────────────────────────────────────
        with _span("memo_store"):
            self._memo_put(prompt, text)

        # ── Profiler: finish ───────────────────────────────────────────
        if prof is not None:
            prof.finish(
                usage               = usage,
                prompt_built_chars  = len(built),
                active_window_used  = effective_window,
                active_window_cfg   = self._cfg.active_window,
                context_turns       = len(self._ctx._turns),
                memo_hit            = memo_hit,
                hw                  = {
                    "n_ctx":        self._cfg.n_ctx,
                    "n_threads":    self._cfg.n_threads,
                    "n_gpu_layers": self._cfg.n_gpu_layers,
                },
            )
        # ── Telemetria legada (direct_runtime.jsonl) ──────────────────
        telemetry = {
            "mode":               "direct",
            "model":              self._cfg.model_path.name,
            "n_ctx":              self._cfg.n_ctx,
            "n_threads":          self._cfg.n_threads,
            "n_threads_batch":    self._cfg.n_threads_batch,
            "prompt_chars":       len(prompt),
            "prompt_tokens":      prompt_tokens,
            "completion_tokens":  completion_tokens,
            "total_tokens":       total_tokens,
            "prompt_eval_s":      0.0,
            "infer_s":            round(infer_elapsed, 3),
            "total_s":            round(infer_elapsed, 3),
            "tokens_per_second":  tokens_per_second,
            "context_turns":      len(self._ctx._turns),
            "max_tokens":         max_tokens,
            "system_prompt":      self._cfg.system_prompt,
            "repeat_penalty":     self._cfg.repeat_penalty,
            "min_p":              self._cfg.min_p,
            "temperature":        self._cfg.temperature,
            "llm_call_ms":        resp.get("llm_call_ms"),
        }
        try:
            record_direct(telemetry)
        except Exception:
            pass
        return text
    def _log_runtime(self, data: dict):
        path = Path("telemetry/direct_runtime.jsonl")
        with path.open("a", encoding="utf8") as f:
            f.write(json.dumps(data) + "\n")
    def _memo_key(self, prompt: str) -> str:
        return prompt.casefold().strip() # " ".join(prompt.lower().split())
    def _memo_order_discard(self, key: str) -> None:
        """Remove key do deque sem ruído quando ela não existe."""
        try:
            self._memo_order.remove(key)
        except ValueError:
            return
    def _memo_get(self, prompt: str) -> str | None:
        if not self._cfg.repetition_memo_enabled:
            return None
        key = self._memo_key(prompt)
        ent = self._memo.get(key)
        if not ent:
            return None
        answer, ts = ent
        # TTL exemplo: 3600s
        ttl = getattr(self._cfg, "memo_ttl_seconds", 3600)
        if time.monotonic() - ts > ttl:
            # expired
            self._memo.pop(key, None)
            self._memo_order_discard(key)
            return None
        # MRU refresh
        self._memo_order_discard(key)
        self._memo_order.append(key)
        return answer
    def _memo_put(self, prompt: str, answer: str) -> None:
        if not self._cfg.repetition_memo_enabled:
            return
        key = self._memo_key(prompt)
        ts = time.monotonic()
        self._memo[key] = (answer, ts)
        self._memo_order_discard(key)
        self._memo_order.append(key)
        # prune size
        while len(self._memo_order) > self._cfg.repetition_memo_size:
            oldest = self._memo_order.popleft()
            self._memo.pop(oldest, None)
    def shutdown(self) -> None:
        """Libera modelo da RAM. Idempotente."""
        if self._llm is not None:
            try:
                self._llm.close()
            except Exception as e:
                import sys as _dox_sys, os as _dox_os
                exc_type, exc_obj, exc_tb = _dox_sys.exc_info()
                f_name = _dox_os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] if exc_tb else "Unknown"
                line_n = exc_tb.tb_lineno if exc_tb else 0
                print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: _analyze_layer\033[0m\n\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033[0m")
            self._llm = None

        self._load_time = None
        # ContextWindow preservada para retomada de sessão.
    def clear_context(self) -> None:
        """Limpa histórico de contexto sem descarregar o modelo."""
        self._ctx.clear()
    def stats(self) -> dict[str, Any]:
        """Estado de memória para `orn brain`. OSL-12."""
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
                "cpu_mask": self._cfg.cpu_mask,
                "cpuset": self._cfg.cpuset,
                "min_p": self._cfg.min_p,
                "response_hard_limit": self._cfg.response_hard_limit,
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
        if not self._affinity_applied:
            try:
                applied, detail = apply_process_affinity(self._cfg.cpu_mask, self._cfg.cpuset)
                if applied:
                    print(f"[CPU-AFFINITY] {detail}")
            except Exception as exc:
                print(f"[CPU-AFFINITY] falha ao aplicar: {exc}")
            finally:
                self._affinity_applied = True

        # Backend nativo
        if self._native is not None:
            if not self._native._ready:
                try:
                    self._native.load()
                except Exception as exc:
                    print(f"[ORN-NATIVE] falha ao carregar: {exc} — fallback Python")
                    self._native = None
                    # cai no caminho Python abaixo
                else:
                    return  # nativo pronto — não sobe llama-cpp-python
            else:
                return  # já estava pronto

        # Caminho Python — TTL + load
        if self._llm is not None:
            if (self._cfg.ttl_seconds > 0
                    and self._load_time is not None
                    and time.monotonic() - self._load_time > self._cfg.ttl_seconds):
                self.shutdown()
            else:
                return  # já carregado e dentro do TTL

        self._load()  # ← estava faltando
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
        _UNSUPPORTED = ("type_k", "type_v", "rope_freq_base", "rope_freq_scale",
                        "flash_attn", "no_alloc", "use_mmap", "pin_threads", "cont_batching")
        try:
            self._llm = Llama(**kwargs)
        except TypeError as exc:
            import sys as _dox_sys, os as _dox_os
            exc_type, exc_obj, exc_tb = _dox_sys.exc_info()
            f_name = _dox_os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] if exc_tb else "Unknown"
            line_n = exc_tb.tb_lineno if exc_tb else 0
            print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: _analyze_layer\033[0m\n\033[31m  ■ Type: {type(exc).__name__} | Value: {exc}\033[0m")
            msg = str(exc)
            if not any(token in msg for token in _UNSUPPORTED):
                raise
            for token in _UNSUPPORTED:
                kwargs.pop(token, None)
            self._llm = Llama(**kwargs)
        self._load_time = time.monotonic()
        self._system_tokens = self._llm.tokenize(
            self._system_prefix.encode("utf-8"),
            special=True
        )
        
    def _build_prompt(self) -> str:
        turns = self._ctx._view_turns()
        parts: list[str] = []
        append = parts.append

        sys_content = self._cfg.system_prompt
        if self._system_hint:
            if sys_content:
                sys_content += f"\n{self._system_hint}"
            else:
                sys_content = self._system_hint

        if sys_content:
            append(f"<|im_start|>system\n{sys_content}<|im_end|>\n")

        for t in turns:
            append(f"<|im_start|>{t['role']}\n{t['content']}<|im_end|>\n")

        append("<|im_start|>assistant\n")

        prompt = "".join(parts)
        self._last_prompt = prompt
        return prompt
        
    def _call_engine(self, prompt: str | list[int], max_tokens: int) -> dict:
        """Chama o runtime Llama e retorna dict: {'text': str, 'usage': {...}}

        Aceita prompt como str (compatibilidade) ou list[int] (pré-tokenizado).
        Quando list[int], o motor pula a etapa de tokenização do prompt — ganho
        visível em hardware lento como o N2808.

        Stop tokens adaptativos:
          - Se o prompt não abriu um bloco ```, para em <|im_end|> como antes.
          - Se o prompt abriu um bloco ```, NÃO para em ``` — espera o fechamento.
        """
        
        print(f"[DEBUG-CE] native={self._native is not None}, ready={getattr(self._native, '_ready', 'N/A')}")

        import time as _time
        if self._llm is None:
            raise RuntimeError("Modelo não carregado.")

        hard_limit = max(1, int(getattr(self._cfg, "response_hard_limit", max_tokens)))
        chunk_max = max(1, min(int(max_tokens), hard_limit))

        if self._native is not None and self._native._ready:
            print("[DEBUG-CE] → NATIVO")
            p = prompt if isinstance(prompt, str) else self._llm.detokenize(prompt).decode("utf-8", errors="ignore")

            acc: list[str] = []
            total_completion = 0
            total_ms = 0.0
            while total_completion < hard_limit:
                this_chunk = min(chunk_max, hard_limit - total_completion)
                t0n = _time.perf_counter()
                out = self._native.call(p + "".join(acc), this_chunk)
                total_ms += (_time.perf_counter() - t0n) * 1000.0

                text_piece = str(out.get("text", ""))
                if not text_piece:
                    break
                acc.append(text_piece)

                piece_tokens = int((out.get("usage", {}) or {}).get("completion_tokens", 0) or 0)
                if piece_tokens <= 0:
                    piece_tokens = max(1, len(text_piece.split()))
                total_completion += piece_tokens

                # Heurística: se retornou bem menos que o chunk, presume encerramento natural.
                if piece_tokens < max(4, this_chunk // 2):
                    break

            final_text = "".join(acc)
            usage = {
                "prompt_tokens": 0,
                "completion_tokens": total_completion,
                "total_tokens": total_completion,
            }
            return {"text": final_text, "usage": usage, "llm_call_ms": round(total_ms, 3)}

        print("[DEBUG-CE] → PYTHON")

        # Detecta bloco de código aberto — funciona tanto para str quanto para
        # list[int] (no caso de tokens, decodifica para verificar backticks).
        if isinstance(prompt, str):
            open_fences = prompt.count("```")
        else:
            # Para lista de tokens: decodifica só para verificar — sem custo
            # perceptível (operação feita no Python, não no motor).
            try:
                decoded = self._llm.detokenize(prompt).decode("utf-8", errors="ignore")
                open_fences = decoded.count("```")
            except Exception:
                open_fences = 0

        code_is_open = (open_fences % 2) == 1

        if code_is_open:
            stop_tokens = ["<|im_end|>", "</s>", "\n```\n", "\n``` "]
        else:
            stop_tokens = ["<|im_end|>", "</s>"]

        base_kwargs = {
            "stop": stop_tokens,
            "echo": False,
            "temperature": self._cfg.temperature,
            "top_p": self._cfg.top_p,
            "top_k": self._cfg.top_k,
            "repeat_penalty": self._cfg.repeat_penalty,
        }
        if self._cfg.min_p is not None:
            base_kwargs["min_p"] = self._cfg.min_p

        acc: list[str] = []
        total_completion = 0
        total_prompt = 0
        total_ms = 0.0
        prompt_for_call: str | list[int] = prompt
        min_p_unsupported = False

        while total_completion < hard_limit:
            remaining = hard_limit - total_completion
            call_kwargs = dict(base_kwargs)
            call_kwargs["max_tokens"] = min(chunk_max, remaining)

            t0 = _time.perf_counter()
            try:
                output = self._llm(prompt_for_call, **call_kwargs)
            except TypeError as exc:
                msg = str(exc)
                if "min_p" not in msg or min_p_unsupported:
                    raise
                min_p_unsupported = True
                base_kwargs.pop("min_p", None)
                call_kwargs.pop("min_p", None)
                output = self._llm(prompt_for_call, **call_kwargs)
            total_ms += (_time.perf_counter() - t0) * 1000.0

            choice = (output.get("choices") or [{}])[0]
            piece = str(choice.get("text", ""))
            usage = output.get("usage", {}) or {}
            if piece:
                acc.append(piece)

            prompt_t = int(usage.get("prompt_tokens", 0) or 0)
            comp_t = int(usage.get("completion_tokens", 0) or 0)
            if comp_t <= 0 and piece:
                comp_t = max(1, len(piece.split()))
            total_prompt = max(total_prompt, prompt_t)
            total_completion += comp_t

            finish_reason = str(choice.get("finish_reason", "") or "")
            if finish_reason and finish_reason != "length":
                break
            if comp_t <= 0 or not piece:
                break

            # Após a primeira chamada com tokens pré-montados, segue como string.
            if isinstance(prompt_for_call, list):
                try:
                    base_prompt = self._llm.detokenize(prompt_for_call).decode("utf-8", errors="ignore")
                except Exception:
                    base_prompt = self._build_prompt()
                prompt_for_call = base_prompt + "".join(acc)
            else:
                prompt_for_call = prompt_for_call + piece

        final_text = "".join(acc)
        out_usage = {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
        }
        return {"text": final_text, "usage": out_usage, "llm_call_ms": round(total_ms, 3)}

    def _build_prompt_tokens(self) -> list[int] | None:
        """Constrói prompt como lista de token IDs reutilizando _system_tokens.

        ② Pré-tokenização: o bloco system já foi tokenizado em _load();
        aqui só tokenizamos as turns dinâmicas e o marcador de assistente.

        Returns:
            list[int] com todos os tokens prontos para o motor, ou None
            se a tokenização falhar (caller usa fallback de string).
        """
        if self._system_tokens is None or self._llm is None:
            return None

        try:
            turns = self._ctx._view_turns()
            tokens: list[int] = list(self._system_tokens)

            hint = self._system_hint
            if hint:
                # System hint é dinâmico — tokeniza e injeta após system base.
                hint_str = f"\n{hint}"
                # Remove o token <|im_end|> final do system_prefix antes de injetar
                # (último token do system_tokens é o fim do bloco system).
                # Estratégia segura: reconstrói system completo com hint.
                sys_with_hint = (
                    f"<|im_start|>system\n"
                    f"{self._cfg.system_prompt}\n{hint}"
                    f"<|im_end|>\n"
                )
                try:
                    tokens = list(
                        self._llm.tokenize(sys_with_hint.encode("utf-8"), special=True)
                    )
                except TypeError:
                    tokens = list(
                        self._llm.tokenize(sys_with_hint.encode("utf-8"))
                    )
            # else: usa self._system_tokens sem modificação (zero custo)

            for t in turns:
                chunk = f"<|im_start|>{t['role']}\n{t['content']}<|im_end|>\n"
                try:
                    tokens += self._llm.tokenize(chunk.encode("utf-8"), special=True)
                except TypeError:
                    tokens += self._llm.tokenize(chunk.encode("utf-8"))

            # Marcador de início da resposta do assistente
            try:
                tokens += self._llm.tokenize(
                    b"<|im_start|>assistant\n", special=True
                )
            except TypeError:
                tokens += self._llm.tokenize(b"<|im_start|>assistant\n")

            return tokens

        except Exception:
            return None  # OSL-15: fallback silencioso para string
