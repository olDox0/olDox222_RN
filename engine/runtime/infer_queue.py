# -*- coding: utf-8 -*-
# engine/runtime/infer_queue.py

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor


class InferQueue:
    """
    Fila de Inferência (Harmonia de Fluxo).
    Protege o LLM (Hefesto) de atropelamentos e gerencia a concorrência.
    """
    def __init__(self, bridge, max_workers: int = 1, async_mode: bool = False):
        self._bridge = bridge
        self._async = async_mode
        
        # OSL-Hardware: Limitamos estritamente a 1 worker para proteger a CPU/RAM (N2808)
        safe_workers = 1 if max_workers <= 1 else max_workers
        self._executor = ThreadPoolExecutor(max_workers=safe_workers) if async_mode else None
        
        # O Leão de Chácara: Garante que o Llama.cpp nunca processe duas coisas ao mesmo tempo.
        self._lock = threading.Lock()

    def submit(self, prompt, max_tokens=None, token_hint=None, system_hint=None):
        """Submete uma requisição de forma segura (síncrona ou assíncrona)."""
        
        def _task():
            # A mágica da harmonia: O Lock impede que o modelo sofra concorrência.
            # As threads aguardam aqui pacificamente a vez delas.
            with self._lock:
                return self._bridge.ask(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    token_hint=token_hint,
                    system_hint=system_hint,
                )

        if not self._async:
            return _task()

        # No modo assíncrono, a thread principal é liberada instantaneamente.
        # Isso permite que o `orn-server` continue respondendo a /status no HTTP.
        return self._executor.submit(_task)

    def shutdown(self, wait: bool = True) -> None:
        """Desliga a fila de forma limpa (Bug de Copy-Paste corrigido)."""
        if self._executor is not None:
            # Pede para as threads terminarem suavemente
            self._executor.shutdown(wait=wait)
            self._executor = None
            
        # Nota: Nós NÃO desligamos a _bridge aqui. 
        # A responsabilidade de gerenciar a vida útil da bridge é do Executive (Zeus).
        # Apenas soltamos a referência para o Garbage Collector limpar.
        self._bridge = None