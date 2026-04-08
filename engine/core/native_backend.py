# -*- coding: utf-8 -*-
"""
ORN — Native Backend (Vulcano Nativo)
Chama orn.dll diretamente via ctypes — sem overhead do llama-cpp-python.
"""
import os
import sys
import time
from ctypes import cdll, c_char_p, c_int, create_string_buffer
from pathlib import Path


class NativeBackend:
    """Interface ctypes para orn.dll.
    
    Implementa a mesma assinatura de retorno que _call_engine() do bridge:
        {'text': str, 'usage': dict, 'llm_call_ms': float}
    """

    _OUTPUT_SIZE = 8192

    def __init__(self, dll_path: str | Path, model_path: str | Path,
                 n_ctx: int = 512, n_threads: int = 2) -> None:
        self._dll_path   = Path(dll_path)
        self._model_path = str(model_path)
        self._n_ctx      = n_ctx
        self._n_threads  = n_threads
        self._lib        = None
        self._ready      = False

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Carrega DLL e inicializa modelo."""
        if self._ready:
            return

        if not self._dll_path.exists():
            raise FileNotFoundError(f"orn.dll não encontrado em: {self._dll_path}")

        dll_dirs = [self._dll_path.parent]
        root_dir = self._dll_path.parent.parent
        dll_dirs.extend(
            [
                root_dir / "venv" / "Lib" / "site-packages" / "llama_cpp" / "lib",
                Path(sys.prefix) / "Lib" / "site-packages" / "llama_cpp" / "lib",
            ]
        )
        seen: set[str] = set()
        for d in dll_dirs:
            key = str(d).lower()
            if key in seen or not d.exists():
                continue
            seen.add(key)
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(d))

        lib = cdll.LoadLibrary(str(self._dll_path))

        lib.orn_init.argtypes  = [c_char_p, c_int, c_int]
        lib.orn_init.restype   = c_int
        lib.orn_infer.argtypes = [c_char_p, c_int, c_char_p, c_int]
        lib.orn_infer.restype  = c_int
        lib.orn_free.argtypes  = []
        lib.orn_free.restype   = None

        rc = lib.orn_init(
            self._model_path.encode("utf-8"),
            self._n_ctx,
            self._n_threads,
        )
        if rc != 0:
            raise RuntimeError(f"orn_init falhou: {rc}")

        self._lib   = lib
        self._ready = True

    def shutdown(self) -> None:
        if self._lib and self._ready:
            self._lib.orn_free()
        self._lib  = None
        self._ready = False

    # ------------------------------------------------------------------
    # Inferência — mesma assinatura de retorno que _call_engine()
    # ------------------------------------------------------------------

    def call(self, prompt: str, max_tokens: int) -> dict:
        """Executa inferência nativa e retorna dict compatível com bridge."""
        if not self._ready:
            raise RuntimeError("NativeBackend não inicializado.")

        buf = create_string_buffer(self._OUTPUT_SIZE)
        t0  = time.perf_counter()

        n = self._lib.orn_infer(
            prompt.encode("utf-8"),
            max_tokens,
            buf,
            self._OUTPUT_SIZE,
        )

        llm_ms = (time.perf_counter() - t0) * 1000.0

        if n < 0:
            raise RuntimeError(f"orn_infer falhou: {n}")

        text = buf.value.decode("utf-8", errors="ignore")
        real_token_count = len(text.split())  # estimativa rápida

        # --- ADICIONE ESTE BLOCO AQUI ---
        # Limpeza agressiva da RAM (OSL-18)
        del buf
        import gc
        gc.collect()
        # -------------------------------

        return {
            "text":       text,
            "usage":      {
                "prompt_tokens":     0,
                "completion_tokens": real_token_count, 
                "total_tokens":      real_token_count,
            },
            "llm_call_ms": round(llm_ms, 3),
        }