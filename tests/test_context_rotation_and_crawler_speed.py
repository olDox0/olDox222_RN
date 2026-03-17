from engine.core.llm_bridge import ContextWindow
from engine.tools.crawler import CrawlerResult, OrnCrawler, _session_cache


def test_context_rotation_compacts_old_turns() -> None:
    ctx = ContextWindow(max_tokens=100, rotation=True, compact_ratio=0.5)

    ctx.push("user", "um dois tres quatro cinco")
    ctx.push("assistant", "a b c d e")
    ctx.push("user", "f g h i j")
    ctx.push("assistant", "k l m n o")

    compacted = ctx._compact_old_turns()
    turns = ctx.get_turns()

    assert compacted is True
    assert turns[0]["role"] == "system"
    assert "[CTX-ROTATION]" in turns[0]["content"]


def test_context_rotation_can_be_disabled() -> None:
    ctx = ContextWindow(max_tokens=10, rotation=False, compact_ratio=0.5)

    ctx.push("user", "um dois tres quatro cinco")
    ctx.push("assistant", "a b c d e")
    ctx.push("user", "f g h i j")

    turns = ctx.get_turns()
    assert all("[CTX-ROTATION]" not in t["content"] for t in turns)
    assert ctx.stats()["token_est"] <= 10


def test_crawler_uses_cache_without_rate_wait_for_explicit_source(monkeypatch) -> None:
    cached = CrawlerResult(source="wikipedia", query="kernel", title="Kernel", context="cached text")
    _session_cache["wiki:pt:kernel"] = cached

    crawler = OrnCrawler()
    monkeypatch.setattr(crawler, "check_deps", lambda: {"requests": True, "beautifulsoup4": True, "urllib.robotparser": True})

    called = {"rate": 0}

    def fake_rate_wait(domain: str) -> None:
        called["rate"] += 1

    monkeypatch.setattr(crawler, "_rate_wait", fake_rate_wait)

    result = crawler.search("kernel", source="wikipedia", lang="pt")

    assert result.context == "cached text"
    assert called["rate"] == 0
    _session_cache.clear()


def test_crawler_auto_prefers_local_before_cached_remote(monkeypatch, tmp_path) -> None:
    cached = CrawlerResult(source="stackoverflow", query="python async", title="Async", context="cached so")
    _session_cache["so:stackoverflow:python async"] = cached

    idx_dir = tmp_path / "data" / "index"
    idx_dir.mkdir(parents=True)
    (idx_dir / "wiki_fake.db").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    crawler = OrnCrawler()
    monkeypatch.setattr(crawler, "check_deps", lambda: {"requests": True, "beautifulsoup4": True, "urllib.robotparser": True})

    class _LocalRes:
        ok = True
        title = "Local Async"

        def to_prompt_block(self, max_chars=1200):
            return "[CTX-BEGIN]local async[CTX-END]"

    def fake_search_local(query: str, source_id: str, limit: int = 1):
        return [_LocalRes()]

    import engine.tools.crawler as crawler_mod
    monkeypatch.setattr(crawler_mod, "_get_local_index", lambda: (fake_search_local, lambda *_a, **_k: {}))

    result = crawler.search("python async", source="auto")

    assert result.source.endswith("-local")
    assert "local async" in result.context
    _session_cache.clear()


def test_crawler_local_source_prefers_code_index_for_code_query(monkeypatch, tmp_path) -> None:
    idx_dir = tmp_path / "data" / "index"
    idx_dir.mkdir(parents=True)
    (idx_dir / "wikipedia_en_chemistry_mini_2026_01.db").write_text("x", encoding="utf-8")
    (idx_dir / "wikipedia_pt_computer_maxi_2026_01.db").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    crawler = OrnCrawler()
    monkeypatch.setattr(crawler, "check_deps", lambda: {"requests": True, "beautifulsoup4": True, "urllib.robotparser": True})

    class _Res:
        ok = True

        def __init__(self, title: str):
            self.title = title

        def to_prompt_block(self, max_chars=1200):
            return "[CTX-BEGIN]dummy[CTX-END]"

    def fake_search_local(query: str, source_id: str, limit: int = 1):
        if "computer" in source_id:
            return [_Res("Quicksort")]
        return [_Res("Sesquioxide")]

    import engine.tools.crawler as crawler_mod
    monkeypatch.setattr(crawler_mod, "_get_local_index", lambda: (fake_search_local, lambda *_a, **_k: {}))

    result = crawler.search("quicksort python", source="local")
    assert result.source.startswith("wikipedia_pt_computer_maxi_2026_01")
