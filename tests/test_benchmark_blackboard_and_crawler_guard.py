from pathlib import Path

from engine.core.blackboard import DoxoBoard
from engine.tools.benchmark_tuner import Candidate, autotune
from engine.tools.crawler import CrawlerResult, OrnCrawler


def test_benchmark_autotune_picks_fastest_candidate() -> None:
    def fake_runner(cfg, prompt, max_tokens, runs):
        return float(cfg.n_ctx) / 1000.0 + cfg.min_p

    report = autotune(
        prompt="kernel",
        max_tokens=32,
        runs=1,
        candidates=[Candidate(256, 0.2, 1.1), Candidate(512, 0.05, 1.1)],
        runner=fake_runner,
    )

    assert report["best"]["n_ctx"] == 256
    assert report["candidates"][0]["avg_s"] <= report["candidates"][1]["avg_s"]


def test_blackboard_persists_and_builds_context(tmp_path: Path) -> None:
    store = tmp_path / "bb.json"
    board = DoxoBoard(store_path=store)
    board.post_hypothesis("think", "Kernel gerencia processos e memória", 0.8)
    board.add_causal_link("kernel", "gerencia recursos")

    board2 = DoxoBoard(store_path=store)
    summary = board2.get_summary()
    assert summary["items"] == 1
    ctx = board2.build_context_block("o que é kernel")
    assert "[BLACKBOARD]" in ctx
    assert "Kernel" in ctx or "kernel" in ctx


def test_crawler_auto_handles_none_result(monkeypatch) -> None:
    crawler = OrnCrawler()
    monkeypatch.setattr(crawler, "check_deps", lambda: {"requests": True, "beautifulsoup4": True, "urllib.robotparser": True})
    monkeypatch.setattr("engine.tools.crawler.search_pypi", lambda *a, **k: None)
    monkeypatch.setattr("engine.tools.crawler.search_stackoverflow", lambda *a, **k: None)
    monkeypatch.setattr("engine.tools.crawler.search_github", lambda *a, **k: None)
    monkeypatch.setattr("engine.tools.crawler.search_arxiv", lambda *a, **k: None)
    monkeypatch.setattr("engine.tools.crawler.search_wikipedia", lambda *a, **k: None)

    result = crawler.search("qual é kernel", source="auto")

    assert isinstance(result, CrawlerResult)
    assert result.ok is False
