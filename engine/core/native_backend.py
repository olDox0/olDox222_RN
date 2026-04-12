# -*- coding: utf-8 -*-
"""
ORN — Native Backend (Vulcano Nativo)
Chama orn.dll diretamente via ctypes — sem overhead do llama-cpp-python.
"""
import os
import sys
import time

from ctypes import CFUNCTYPE, cdll, c_char_p, c_int, c_void_p, create_string_buffer
from pathlib import Path

import queue as _queue


_OrnTokenCb = CFUNCTYPE(c_int, c_char_p, c_int, c_void_p)

class NativeBackend:
    """Interface ctypes para orn.dll.
    
    Implementa a mesma assinatura de retorno que _call_engine() do bridge:
        {'text': str, 'usage': dict, 'llm_call_ms': float}
    """

    _OUTPUT_SIZE = 1000000

    def __init__(self, dll_path: str | Path, model_path: str | Path,
                     n_ctx: int = 1024, n_threads: int = 2) -> None:
        self._dll_path   = Path(dll_path)
        self._model_path = str(model_path)
        self._n_ctx      = n_ctx
        self._n_threads  = n_threads
        self._lib        = None
        self._ready      = False
        self._buf        = create_string_buffer(self._OUTPUT_SIZE)

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

        self._buf[0] = b'\0'
        t0 = time.perf_counter()

        n = self._lib.orn_infer(
            prompt.encode("utf-8"),
            max_tokens,
            self._buf,
            self._OUTPUT_SIZE,
        )

        # -5 = llama_decode falhou (KV cache cheio ou histórico corrompido).
        # orn_free() + orn_init() zera g_history_len e limpa o KV cache.
        # Com use_mmap=True os pesos já estão no page-cache do SO — reinit é rápido.
        if n == -5:
            print("[NATIVE] KV cache cheio — resetando contexto e tentando novamente.", flush=True)
            try:
                self._lib.orn_free()
                rc = self._lib.orn_init(
                    self._model_path.encode("utf-8"),
                    self._n_ctx,
                    self._n_threads,
                )
                if rc == 0:
                    self._buf[0] = b'\0'
                    n = self._lib.orn_infer(
                        prompt.encode("utf-8"),
                        max_tokens,
                        self._buf,
                        self._OUTPUT_SIZE,
                    )
                else:
                    raise RuntimeError(f"orn_init falhou após reset: {rc}")
            except Exception as exc:
                raise RuntimeError(f"orn_infer falhou: -5 (reset também falhou: {exc})")

        llm_ms = (time.perf_counter() - t0) * 1000.0

        if n < 0:
            raise RuntimeError(f"orn_infer falhou: {n}")

        text = self._buf.value.decode("utf-8", errors="ignore")
        real_token_count = len(text.split())

        return {
            "text":  text,
            "usage": {
                "prompt_tokens":     0,
                "completion_tokens": real_token_count,
                "total_tokens":      real_token_count,
            },
            "llm_call_ms": round(llm_ms, 3),
        }
        
    def stream(self, prompt: str, max_tokens: int):
        """Gerador que yield cada peça de token conforme é produzida pela DLL."""
        if not self._ready:
            raise RuntimeError("NativeBackend não inicializado.")

        # Tenta registrar orn_infer_stream — se a DLL antiga não tiver, faz fallback
        fn = getattr(self._lib, "orn_infer_stream", None)
        if fn is None:
            # DLL antiga sem streaming — emite tudo de uma vez
            result = self.call(prompt, max_tokens)
            yield result["text"]
            return

        fn.argtypes = [c_char_p, c_int, _OrnTokenCb, c_void_p]
        fn.restype  = c_int

        # Fila thread-safe entre o callback C e o gerador Python
        q: _queue.Queue = _queue.Queue()
        _DONE    = object()
        _ERRCODE = []

        @_OrnTokenCb
        def _cb(piece_ptr, n_bytes, _ud):
            try:
                text = piece_ptr[:n_bytes].decode("utf-8", errors="replace")
                q.put(text)
            except Exception:
                pass
            return 0  # 0 = continuar

        import threading

        def _run():
            rc = fn(prompt.encode("utf-8"), max_tokens, _cb, None)
            _ERRCODE.append(rc)
            q.put(_DONE)

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        while True:
            item = q.get()
            if item is _DONE:
                break
            yield item

        t.join()
        rc = _ERRCODE[0] if _ERRCODE else -99

        # KV cache cheio → reset e tenta não-stream como fallback
        if rc == -5:
            print("[NATIVE] KV cache cheio no stream — resetando contexto.", flush=True)
            self._lib.orn_free()
            init_rc = self._lib.orn_init(
                self._model_path.encode("utf-8"), self._n_ctx, self._n_threads
            )
            if init_rc != 0:
                raise RuntimeError(f"orn_init falhou após reset: {init_rc}")
            result = self.call(prompt, max_tokens)
            yield result["text"]
        elif rc not in (0, None):
            raise RuntimeError(f"orn_infer_stream falhou: {rc}")