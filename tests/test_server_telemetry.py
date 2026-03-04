import json

import engine.server.server as server


class _FakeConn:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._sent = b""

    def settimeout(self, _v):
        return None

    def recv(self, _n: int) -> bytes:
        payload, self._payload = self._payload, b""
        return payload

    def sendall(self, data: bytes) -> None:
        self._sent += data

    def close(self) -> None:
        return None


def test_telemetry_hotspots_sorted_by_total_ms(monkeypatch) -> None:
    fake_snap = {
        "a": {"calls": 10, "avg_ms": 2.0, "p95_ms": 3.0},
        "b": {"calls": 2, "avg_ms": 30.0, "p95_ms": 31.0},
        "c": {"calls": 100, "avg_ms": 0.1, "p95_ms": 0.2},
    }
    monkeypatch.setattr(server.GLOBAL_TELEMETRY, "snapshot", lambda: fake_snap)

    rows = server._telemetry_hotspots(limit=2)
    assert [r["name"] for r in rows] == ["b", "a"]
    assert rows[0]["total_ms"] == 60.0


def test_status_payload_includes_telemetry_hotspots(monkeypatch) -> None:
    monkeypatch.setattr(server, "_telemetry_hotspots", lambda limit=3: [{"name": "server.infer", "calls": 7, "avg_ms": 9.5, "p95_ms": 12.0, "total_ms": 66.5}])
    conn = _FakeConn(b"STATUS\n")

    server._handle(conn)

    payload = json.loads(conn._sent.decode("utf-8").strip())
    assert payload["status"] == "online"
    assert payload["telemetry_hotspots"][0]["name"] == "server.infer"
    assert "boot_perf" in payload
    assert "vulcan_boot_ms" in payload["boot_perf"]


def test_infer_registers_phase_telemetry(monkeypatch) -> None:
    class _Cfg:
        system_prompt = "sys"
        temperature = 0.1
        top_p = 0.9
        top_k = 40
        repeat_penalty = 1.1

    class _LLM:
        def __call__(self, *_args, **_kwargs):
            return {"choices": [{"text": "ok"}]}

    observed = []

    def _capture(name, elapsed_ms, **kwargs):
        observed.append((name, elapsed_ms, kwargs))

    monkeypatch.setattr(server, "_cfg", _Cfg())
    monkeypatch.setattr(server, "_llm", _LLM())
    monkeypatch.setattr(server, "_observe_telemetry", _capture)

    infer_fn = getattr(server._infer, "__wrapped__", server._infer)
    out, elapsed = infer_fn("ping", 8)
    assert out == "ok"
    assert elapsed >= 0
    names = [item[0] for item in observed]
    assert "server.infer.lock_wait" in names
    assert "server.infer.llm_call" in names
