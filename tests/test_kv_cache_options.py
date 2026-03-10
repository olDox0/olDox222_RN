from engine.core.llm_bridge import BridgeConfig
from engine.server.server import ServerCLI


def test_bridge_config_reads_kv_cache_types_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ORN_CACHE_TYPE_K", "q8_0")
    monkeypatch.setenv("ORN_CACHE_TYPE_V", "q4_0")
    monkeypatch.setenv("ORN_ACTIVE_WINDOW", "128")

    cfg = BridgeConfig(n_ctx=256, active_window=256)

    assert cfg.cache_type_k == "q8_0"
    assert cfg.cache_type_v == "q4_0"
    assert cfg.active_window == 128


def test_bridge_config_clamps_active_window_to_n_ctx(monkeypatch) -> None:
    monkeypatch.setenv("ORN_ACTIVE_WINDOW", "999")

    cfg = BridgeConfig(n_ctx=256, active_window=32)

    assert cfg.active_window == 256


def test_server_cli_start_parses_new_kv_flags(monkeypatch) -> None:
    cli = ServerCLI()
    called = {}

    def fake_start(background=False, cache_type_k=None, cache_type_v=None, active_window=None):
        called["background"] = background
        called["cache_type_k"] = cache_type_k
        called["cache_type_v"] = cache_type_v
        called["active_window"] = active_window

    monkeypatch.setattr(cli, "_start", fake_start)

    cli.run(["start", "--bg", "--cache-type-k", "q8_0", "--cache-type-v", "q4_0", "--active-window", "192"])

    assert called == {
        "background": True,
        "cache_type_k": "q8_0",
        "cache_type_v": "q4_0",
        "active_window": "192",
    }


def test_server_cli_start_env_includes_kv_cache_overrides(monkeypatch) -> None:
    cli = ServerCLI()
    monkeypatch.setenv("KEEP", "1")

    env = cli._start_env("q8_0", "q4_0", "160")

    assert env["KEEP"] == "1"
    assert env["ORN_CACHE_TYPE_K"] == "q8_0"
    assert env["ORN_CACHE_TYPE_V"] == "q4_0"
    assert env["ORN_ACTIVE_WINDOW"] == "160"
