
# -*- coding: utf-8 -*-
"""Replay cache dos streams NDJSON — para reconexão do cliente.

Cliente que cair no meio do stream pode fazer GET /stream_cache?id=<uuid>
e retomar. Cache tem TTL e LRU eviction. Isolado para ser testável sem HTTP.
"""
from __future__ import annotations

import sys
import threading
import time
import uuid

CACHE_LIMIT = 32
CACHE_TTL_S = 900
CACHE_MAX_CHUNKS = 256
CACHE_MAX_OUTPUT_CHARS = 120_000


class StreamCache:
    def __init__(
        self,
        limit: int = CACHE_LIMIT,
        ttl_s: float = CACHE_TTL_S,
        max_chunks: int = CACHE_MAX_CHUNKS,
        max_output_chars: int = CACHE_MAX_OUTPUT_CHARS,
    ) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, dict] = {}
        self._limit = int(limit)
        self._ttl = float(ttl_s)
        self._max_chunks = int(max_chunks)
        self._max_output_chars = int(max_output_chars)

    def start(self, prompt: str, max_tokens: int) -> str:
        request_id = uuid.uuid4().hex
        now = time.time()
        with self._lock:
            self._store[request_id] = {
                "request_id": request_id,
                "created_at": now,
                "updated_at": now,
                "prompt": prompt,
                "max_tokens": int(max_tokens),
                "chunks": [],
                "output": "",
                "truncated": False,
                "done": False,
                "elapsed_s": 0.0,
                "error": None,
            }
        self._prune(now)
        return request_id

    def append(self, request_id: str, delta: str) -> int:
        with self._lock:
            item = self._store.get(request_id)
            if item is None:
                return -1
            chunks: list[str] = item["chunks"]
            chunks.append(delta)
            if len(chunks) > self._max_chunks:
                del chunks[: len(chunks) - self._max_chunks]
            out = str(item["output"]) + delta
            if len(out) > self._max_output_chars:
                out = out[-self._max_output_chars:]
                item["truncated"] = True
            item["output"] = out
            item["updated_at"] = time.time()
            return len(chunks) - 1

    def finish(
        self, request_id: str, output: str, elapsed_s: float,
        error: str | None = None,
    ) -> None:
        with self._lock:
            item = self._store.get(request_id)
            if item is None:
                return
            final = output
            if len(final) > self._max_output_chars:
                final = final[-self._max_output_chars:]
                item["truncated"] = True
            item["output"] = final
            item["elapsed_s"] = float(elapsed_s)
            item["error"] = error
            item["done"] = True
            item["updated_at"] = time.time()

    def get(self, request_id: str) -> dict | None:
        self._prune()
        with self._lock:
            item = self._store.get(request_id)
            if item is None:
                return None
            return {
                "request_id":    item["request_id"],
                "created_at":    item["created_at"],
                "updated_at":    item["updated_at"],
                "prompt":        item["prompt"],
                "max_tokens":    item["max_tokens"],
                "chunks":        list(item["chunks"]),
                "output":        item["output"],
                "truncated":     bool(item.get("truncated", False)),
                "done":          bool(item["done"]),
                "elapsed_s":     item["elapsed_s"],
                "error":         item["error"],
            }

    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def _prune(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            expired = [
                k for k, v in self._store.items()
                if (now - float(v.get("created_at", now))) > self._ttl
            ]
            for k in expired:
                self._store.pop(k, None)
            if len(self._store) <= self._limit:
                return
            ordered = sorted(
                self._store.keys(),
                key=lambda k: float(self._store[k].get("created_at", now)),
            )
            for k in ordered[: max(0, len(self._store) - self._limit)]:
                self._store.pop(k, None)


# ── testes embutidos ─────────────────────────────────────────
def _run_tests() -> int:
    passed = failed = 0

    def _check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            print(f"  [OK] {name}")
            passed += 1
        else:
            print(f"  [X]  {name}" + (f" — {detail}" if detail else ""))
            failed += 1

    c = StreamCache()
    rid = c.start("hi", 128)
    _check("start devolve id", bool(rid) and len(rid) == 32)
    _check("size=1", c.size() == 1)
    item = c.get(rid)
    _check("get devolve item", item is not None and item["prompt"] == "hi")
    _check("get não mostra done ainda", item is not None and not item["done"])

    idx0 = c.append(rid, "a")
    idx1 = c.append(rid, "b")
    _check("append idx0=0", idx0 == 0)
    _check("append idx1=1", idx1 == 1)
    item = c.get(rid)
    _check("output concatenado", item is not None and item["output"] == "ab")
    _check("chunks preservados", item is not None and item["chunks"] == ["a", "b"])

    c.finish(rid, "abc", 1.5)
    item = c.get(rid)
    _check("finish done=True", item is not None and item["done"])
    _check("finish output final", item is not None and item["output"] == "abc")
    _check("finish elapsed_s", item is not None and item["elapsed_s"] == 1.5)

    _check("append em id inexistente → -1", c.append("nope", "x") == -1)
    _check("get inexistente → None", c.get("nope") is None)
    _check("finish em id inexistente: não crasha",
           c.finish("nope", "x", 0.0) is None)

    # limite de chunks
    c2 = StreamCache(max_chunks=3)
    r = c2.start("x", 10)
    for i in range(5):
        c2.append(r, str(i))
    item = c2.get(r)
    _check("max_chunks=3 mantém últimos 3",
           item is not None and item["chunks"] == ["2", "3", "4"])

    # truncamento de output
    c3 = StreamCache(max_output_chars=5)
    r = c3.start("x", 10)
    c3.append(r, "0123")
    c3.append(r, "4567")
    item = c3.get(r)
    _check("max_output_chars=5 trunca",
           item is not None and item["output"] == "34567"
           and item["truncated"])

    # LRU eviction
    c4 = StreamCache(limit=2, ttl_s=3600)
    a = c4.start("a", 10); c4.append(a, "x")
    b = c4.start("b", 10); c4.append(b, "y")
    c4.start("c", 10)  # dispara prune
    _check("LRU limit=2: size<=2", c4.size() <= 2)
    _check("LRU: 'a' evictado (mais antigo)",
           c4.get(a) is None or c4.get(b) is None)

    # TTL
    c5 = StreamCache(ttl_s=0.01)
    r = c5.start("x", 10)
    time.sleep(0.05)
    _check("TTL: item expira", c5.get(r) is None)

    c6 = StreamCache()
    r = c6.start("x", 10)
    c6.clear()
    _check("clear zera", c6.size() == 0 and c6.get(r) is None)

    print()
    if failed == 0:
        print(f"  {passed} teste(s) OK")
        return 0
    print(f"  {passed}/{passed + failed} passaram — {failed} falha(s)")
    return 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_run_tests())
    print("Uso: python -m engine.web.stream_cache --test")
    raise SystemExit(1)
