from engine.core.llm_bridge import BridgeConfig
from engine.server.server import ServerCLI


def test_bridge_config_reads_kv_cache_types_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ORN_CACHE_TYPE_K", "q8_0")
    monkeypatch.setenv("ORN_CACHE_TYPE_V", "q4_0")
    monkeypatch.setenv("ORN_ACTIVE_WINDOW", "128")
    monkeypatch.setenv("ORN_ROPE_FREQ_BASE", "10000")
    monkeypatch.setenv("ORN_ROPE_FREQ_SCALE", "0.5")
    monkeypatch.setenv("ORN_FLASH_ATTN", "on")
    monkeypatch.setenv("ORN_USE_MMAP", "0")
    monkeypatch.setenv("ORN_NO_ALLOC", "1")

    cfg = BridgeConfig(n_ctx=256, active_window=256)

    assert cfg.cache_type_k == "q8_0"
    assert cfg.cache_type_v == "q4_0"
    assert cfg.active_window == 128
    assert cfg.rope_freq_base == 10000.0
    assert cfg.rope_freq_scale == 0.5
    assert cfg.flash_attn is True
    assert cfg.use_mmap is False
    assert cfg.no_alloc is True


def test_bridge_config_clamps_active_window_to_n_ctx(monkeypatch) -> None:
    monkeypatch.setenv("ORN_ACTIVE_WINDOW", "999")

    cfg = BridgeConfig(n_ctx=256, active_window=32)

    assert cfg.active_window == 256


def test_server_cli_start_parses_new_kv_flags(monkeypatch) -> None:
    cli = ServerCLI()
    called = {}

    def fake_start(
        background=False,
        cache_type_k=None,
        cache_type_v=None,
        active_window=None,
        rope_freq_base=None,
        rope_freq_scale=None,
        flash_attn=None,
        no_mmap=False,
        no_alloc=False,
    ):
        called["background"] = background
        called["cache_type_k"] = cache_type_k
        called["cache_type_v"] = cache_type_v
        called["active_window"] = active_window
        called["rope_freq_base"] = rope_freq_base
        called["rope_freq_scale"] = rope_freq_scale
        called["flash_attn"] = flash_attn
        called["no_mmap"] = no_mmap
        called["no_alloc"] = no_alloc

    monkeypatch.setattr(cli, "_start", fake_start)

    cli.run([
        "start", "--bg",
        "--cache-type-k", "q8_0",
        "--cache-type-v", "q4_0",
        "--active-window", "192",
        "--rope-freq-base", "10000",
        "--rope-freq-scale", "0.5",
        "--flash-attn", "true",
        "--no-mmap",
        "--no-alloc",
    ])

    assert called == {
        "background": True,
        "cache_type_k": "q8_0",
        "cache_type_v": "q4_0",
        "active_window": "192",
        "rope_freq_base": "10000",
        "rope_freq_scale": "0.5",
        "flash_attn": "true",
        "no_mmap": True,
        "no_alloc": True,
    }


def test_server_cli_start_env_includes_kv_cache_overrides(monkeypatch) -> None:
    cli = ServerCLI()
    monkeypatch.setenv("KEEP", "1")

    env = cli._start_env("q8_0", "q4_0", "160", "10000", "0.5", "on", True, True)

    assert env["KEEP"] == "1"
    assert env["ORN_CACHE_TYPE_K"] == "q8_0"
    assert env["ORN_CACHE_TYPE_V"] == "q4_0"
    assert env["ORN_ACTIVE_WINDOW"] == "160"
    assert env["ORN_ROPE_FREQ_BASE"] == "10000"
    assert env["ORN_ROPE_FREQ_SCALE"] == "0.5"
    assert env["ORN_FLASH_ATTN"] == "on"
    assert env["ORN_USE_MMAP"] == "0"
    assert env["ORN_NO_ALLOC"] == "1"


def test_bridge_config_ignores_invalid_rope_values(monkeypatch) -> None:
    monkeypatch.setenv("ORN_ROPE_FREQ_BASE", "abc")
    monkeypatch.setenv("ORN_ROPE_FREQ_SCALE", "")
    monkeypatch.setenv("ORN_FLASH_ATTN", "talvez")
    monkeypatch.setenv("ORN_USE_MMAP", "talvez")
    monkeypatch.setenv("ORN_NO_ALLOC", "talvez")

    cfg = BridgeConfig()

    assert cfg.rope_freq_base is None
    assert cfg.rope_freq_scale is None
    assert cfg.flash_attn is None
    assert cfg.use_mmap is True
    assert cfg.no_alloc is False


def test_bridge_config_disables_cache_and_rope_with_none_tokens(monkeypatch) -> None:
    monkeypatch.setenv("ORN_CACHE_TYPE_K", "none")
    monkeypatch.setenv("ORN_CACHE_TYPE_V", "OFF")
    monkeypatch.setenv("ORN_ROPE_FREQ_BASE", "disable")
    monkeypatch.setenv("ORN_ROPE_FREQ_SCALE", "null")
    monkeypatch.setenv("ORN_FLASH_ATTN", "off")
    monkeypatch.setenv("ORN_USE_MMAP", "false")
    monkeypatch.setenv("ORN_NO_ALLOC", "true")

    cfg = BridgeConfig(cache_type_k="q8_0", cache_type_v="q4_0", rope_freq_base=10000.0, rope_freq_scale=1.0, flash_attn=True, use_mmap=True, no_alloc=False)

    assert cfg.cache_type_k is None
    assert cfg.cache_type_v is None
    assert cfg.rope_freq_base is None
    assert cfg.rope_freq_scale is None
    assert cfg.flash_attn is None
    assert cfg.use_mmap is False
    assert cfg.no_alloc is True


def test_bridge_config_strips_quotes_from_cache_type(monkeypatch) -> None:
    monkeypatch.setenv("ORN_CACHE_TYPE_K", '"q8_0"')

    cfg = BridgeConfig()

    assert cfg.cache_type_k == "q8_0"


def test_server_cli_allows_disable_tokens(monkeypatch) -> None:
    cli = ServerCLI()
    called = {}

    def fake_start(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr(cli, "_start", fake_start)

    cli.run([
        "start",
        "--cache-type-k", "none",
        "--cache-type-v", "off",
        "--rope-freq-base", "disable",
        "--rope-freq-scale", "null",
        "--flash-attn", "off",
        "--no-mmap",
        "--no-alloc",
    ])

    assert called["cache_type_k"] == "none"
    assert called["cache_type_v"] == "off"
    assert called["rope_freq_base"] == "disable"
    assert called["rope_freq_scale"] == "null"
    assert called["flash_attn"] == "off"
    assert called["no_mmap"] is True
    assert called["no_alloc"] is True


def test_bridge_config_normalizes_flash_attn_bool(monkeypatch) -> None:
    monkeypatch.delenv("ORN_FLASH_ATTN", raising=False)

    cfg_on = BridgeConfig(flash_attn="true")
    cfg_off = BridgeConfig(flash_attn="0")

    assert cfg_on.flash_attn is True
    assert cfg_off.flash_attn is False


def test_bridge_config_normalizes_mmap_and_no_alloc_bool(monkeypatch) -> None:
    monkeypatch.delenv("ORN_USE_MMAP", raising=False)
    monkeypatch.delenv("ORN_NO_ALLOC", raising=False)

    cfg = BridgeConfig(use_mmap=False, no_alloc=True)

    assert cfg.use_mmap is False
    assert cfg.no_alloc is True
