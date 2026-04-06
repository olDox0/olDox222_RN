from engine.web import web_server


def test_stream_cache_start_append_finish_get() -> None:
    request_id = web_server._stream_cache_start("abc", 123)
    assert request_id

    idx0 = web_server._stream_cache_append(request_id, "hel")
    idx1 = web_server._stream_cache_append(request_id, "lo")
    assert idx0 == 0
    assert idx1 == 1

    web_server._stream_cache_finish(request_id, "hello", 1.5, error=None)
    item = web_server._stream_cache_get(request_id)
    assert item is not None
    assert item["output"] == "hello"
    assert item["chunks"] == ["hel", "lo"]
    assert item["done"] is True
    assert item["elapsed_s"] == 1.5


def test_stream_cache_prune_expired() -> None:
    request_id = web_server._stream_cache_start("old", 8)
    item = web_server._stream_cache_get(request_id)
    assert item is not None
    old_now = float(item["created_at"]) + web_server.STREAM_CACHE_TTL_S + 1
    web_server._prune_stream_cache(now=old_now)
    assert web_server._stream_cache_get(request_id) is None
