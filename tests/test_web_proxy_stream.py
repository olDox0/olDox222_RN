import json
import socket

from engine.web import web_proxy


class _FakeSocket:
    def __init__(self, chunks, timeout_after_reads=None):
        self._chunks = list(chunks)
        self._timeout_after_reads = timeout_after_reads
        self._reads = 0
        self._timeouts = []
        self.sent = b""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def settimeout(self, value):
        self._timeouts.append(value)

    def connect(self, _addr):
        return None

    def sendall(self, data):
        self.sent += data

    def recv(self, _size):
        if self._timeout_after_reads is not None and self._reads >= self._timeout_after_reads:
            raise socket.timeout("timed out")
        self._reads += 1
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


def test_stream_infer_events_reads_trailing_json_without_newline(monkeypatch) -> None:
    payload = json.dumps({"output": "ok", "elapsed_s": 1.2}).encode("utf-8")
    fake = _FakeSocket([payload])
    monkeypatch.setattr(web_proxy.socket, "socket", lambda *args, **kwargs: fake)

    events = list(web_proxy.stream_infer_events("oi", 16, "127.0.0.1", 9000))
    assert events == [{"output": "ok", "elapsed_s": 1.2}]
    assert fake._timeouts[0] == 5.0
    assert fake._timeouts[1] == web_proxy.STREAM_POLL_TIMEOUT_S


def test_stream_infer_events_emits_error_on_timeout_with_buffer(monkeypatch) -> None:
    partial = json.dumps({"output": "quase", "elapsed_s": 2.0}).encode("utf-8")
    fake = _FakeSocket([partial], timeout_after_reads=1)
    monkeypatch.setattr(web_proxy.socket, "socket", lambda *args, **kwargs: fake)
    ticks = iter([0.0, 0.0, web_proxy.STREAM_READ_TIMEOUT_S + 0.1, web_proxy.STREAM_READ_TIMEOUT_S + 0.2])
    monkeypatch.setattr(web_proxy.time, "monotonic", lambda: next(ticks))

    events = list(web_proxy.stream_infer_events("oi", 16, "127.0.0.1", 9000))
    assert events[0] == {"output": "quase", "elapsed_s": 2.0}
    assert events[1]["event"] == "error"
    assert "timeout" in events[1]["error"]
