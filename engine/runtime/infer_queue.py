# engine/runtime/infer_queue.py

import queue
import threading
from dataclasses import dataclass

@dataclass
class InferJob:
    prompt: str
    max_tokens: int | None
    token_hint: int | None
    system_hint: str | None
    result: list

class InferQueue:

    def __init__(self, bridge):
        self._bridge = bridge
        self._q = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def submit(self, prompt, max_tokens, token_hint, system_hint):
        result = []
        job = InferJob(prompt, max_tokens, token_hint, system_hint, result)
        self._q.put(job)

        while not result:
            pass  # wait

        return result[0]

    def _run(self):
        while True:
            job = self._q.get()
            try:
                r = self._bridge.ask(
                    job.prompt,
                    max_tokens=job.max_tokens,
                    token_hint=job.token_hint,
                    system_hint=job.system_hint,
                )
                job.result.append(r)
            except Exception as e:
                job.result.append(f"[ERR] {e}")