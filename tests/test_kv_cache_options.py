from engine.core.llm_bridge import BridgeConfig, SiCDoxBridge
from engine.server.server import ServerCLI


def test_bridge_config_reads_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("ORN_CACHE_TYPE_K", "q8_0")
    monkeypatch.setenv("ORN_CACHE_TYPE_V", "q4_0")
    monkeypatch.setenv("ORN_ACTIVE_WINDOW", "128")
    monkeypatch.setenv("ORN_ROPE_FREQ_BASE", "10000")
    monkeypatch.setenv("ORN_ROPE_FREQ_SCALE", "0.5")
    monkeypatch.setenv("ORN_FLASH_ATTN", "on")
    monkeypatch.setenv("ORN_USE_MMAP", "0")
    monkeypatch.setenv("ORN_NO_ALLOC", "1")
    monkeypatch.setenv("ORN_MIN_P", "0.01")
    monkeypatch.setenv("ORN_REPETITION_MEMO", "1")
    monkeypatch.setenv("ORN_REPETITION_MEMO_SIZE", "16")
    monkeypatch.setenv("ORN_PIN_THREADS", "1")
    monkeypatch.setenv("ORN_CONT_BATCHING", "1")

    cfg = BridgeConfig(n_ctx=256, active_window=256)

    assert cfg.cache_type_k == "q8_0"
    assert cfg.cache_type_v == "q4_0"
    assert cfg.active_window == 128
    assert cfg.rope_freq_base == 10000.0
    assert cfg.rope_freq_scale == 0.5
    assert cfg.flash_attn is True
    assert cfg.use_mmap is False
    assert cfg.no_alloc is True
    assert cfg.min_p == 0.01
    assert cfg.repetition_memo_enabled is True
    assert cfg.repetition_memo_size == 16
    assert cfg.pin_threads is True
    assert cfg.cont_batching is True


def test_bridge_config_clamps_active_window_to_n_ctx(monkeypatch) -> None:
    monkeypatch.setenv("ORN_ACTIVE_WINDOW", "999")

    cfg = BridgeConfig(n_ctx=256, active_window=32)

    assert cfg.active_window == 256


def test_server_cli_start_parses_new_flags(monkeypatch) -> None:
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
        min_p=None,
        pin_threads=False,
        cont_batching=False,
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
        called["min_p"] = min_p
        called["pin_threads"] = pin_threads
        called["cont_batching"] = cont_batching
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
        "--min-p", "0.01",
        "--pin-threads",
        "--cont-batching",
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
        "min_p": "0.01",
        "pin_threads": True,
        "cont_batching": True,
        "no_mmap": True,
        "no_alloc": True,
    }


def test_server_cli_start_env_includes_overrides(monkeypatch) -> None:
    cli = ServerCLI()
    monkeypatch.setenv("KEEP", "1")

    env = cli._start_env("q8_0", "q4_0", "160", "10000", "0.5", "on", "0.01", True, True, True, True)

    assert env["KEEP"] == "1"
    assert env["ORN_CACHE_TYPE_K"] == "q8_0"
    assert env["ORN_CACHE_TYPE_V"] == "q4_0"
    assert env["ORN_ACTIVE_WINDOW"] == "160"
    assert env["ORN_ROPE_FREQ_BASE"] == "10000"
    assert env["ORN_ROPE_FREQ_SCALE"] == "0.5"
    assert env["ORN_FLASH_ATTN"] == "on"
    assert env["ORN_MIN_P"] == "0.01"
    assert env["ORN_PIN_THREADS"] == "1"
    assert env["ORN_CONT_BATCHING"] == "1"
    assert env["ORN_USE_MMAP"] == "0"
    assert env["ORN_NO_ALLOC"] == "1"


def test_bridge_config_ignores_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv("ORN_ROPE_FREQ_BASE", "abc")
    monkeypatch.setenv("ORN_ROPE_FREQ_SCALE", "")
    monkeypatch.setenv("ORN_FLASH_ATTN", "talvez")
    monkeypatch.setenv("ORN_USE_MMAP", "talvez")
    monkeypatch.setenv("ORN_NO_ALLOC", "talvez")
    monkeypatch.setenv("ORN_MIN_P", "abc")
    monkeypatch.setenv("ORN_REPETITION_MEMO_SIZE", "xx")
    monkeypatch.setenv("ORN_PIN_THREADS", "talvez")
    monkeypatch.setenv("ORN_CONT_BATCHING", "talvez")

    cfg = BridgeConfig()

    assert cfg.rope_freq_base is None
    assert cfg.rope_freq_scale is None
    assert cfg.flash_attn is None
    assert cfg.use_mmap is True
    assert cfg.no_alloc is False
    assert cfg.min_p == 0.01
    assert cfg.repetition_memo_size == 32
    assert cfg.pin_threads is False
    assert cfg.cont_batching is False


def test_bridge_config_disable_tokens(monkeypatch) -> None:
    monkeypatch.setenv("ORN_CACHE_TYPE_K", "none")
    monkeypatch.setenv("ORN_CACHE_TYPE_V", "OFF")
    monkeypatch.setenv("ORN_ROPE_FREQ_BASE", "disable")
    monkeypatch.setenv("ORN_ROPE_FREQ_SCALE", "null")
    monkeypatch.setenv("ORN_FLASH_ATTN", "off")
    monkeypatch.setenv("ORN_USE_MMAP", "false")
    monkeypatch.setenv("ORN_NO_ALLOC", "true")
    monkeypatch.setenv("ORN_REPETITION_MEMO", "0")
    monkeypatch.setenv("ORN_PIN_THREADS", "0")
    monkeypatch.setenv("ORN_CONT_BATCHING", "0")

    cfg = BridgeConfig(
        cache_type_k="q8_0",
        cache_type_v="q4_0",
        rope_freq_base=10000.0,
        rope_freq_scale=1.0,
        flash_attn=True,
        use_mmap=True,
        no_alloc=False,
    )

    assert cfg.cache_type_k is None
    assert cfg.cache_type_v is None
    assert cfg.rope_freq_base is None
    assert cfg.rope_freq_scale is None
    assert cfg.flash_attn is None
    assert cfg.use_mmap is False
    assert cfg.no_alloc is True
    assert cfg.repetition_memo_enabled is False
    assert cfg.pin_threads is False
    assert cfg.cont_batching is False


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
        "--min-p", "0.01",
        "--pin-threads",
        "--cont-batching",
        "--no-mmap",
        "--no-alloc",
    ])

    assert called["cache_type_k"] == "none"
    assert called["cache_type_v"] == "off"
    assert called["rope_freq_base"] == "disable"
    assert called["rope_freq_scale"] == "null"
    assert called["flash_attn"] == "off"
    assert called["min_p"] == "0.01"
    assert called["pin_threads"] is True
    assert called["cont_batching"] is True
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
    cfg = BridgeConfig(use_mmap=False, no_alloc=True, pin_threads=True, cont_batching=False)
    assert cfg.use_mmap is False
    assert cfg.no_alloc is True
    assert cfg.pin_threads is True
    assert cfg.cont_batching is False


def test_bridge_memoization_prunes_old_entries() -> None:
    cfg = BridgeConfig(repetition_memo_enabled=True, repetition_memo_size=2)
    b = SiCDoxBridge(cfg)

    b._memo_put("a", "1")
    b._memo_put("b", "2")
    b._memo_put("c", "3")

    assert b._memo_get("a") is None
    assert b._memo_get("b") == "2"
    assert b._memo_get("c") == "3"


def test_bridge_config_context_rotation_env(monkeypatch) -> None:
    monkeypatch.setenv("ORN_CONTEXT_ROTATION", "0")
    monkeypatch.setenv("ORN_CONTEXT_COMPACT_RATIO", "0.6")

    cfg = BridgeConfig()

    assert cfg.context_rotation is False
    assert cfg.context_compact_ratio == 0.6


def test_server_cli_start_env_sets_doxoade_root_when_discovered(monkeypatch) -> None:
    cli = ServerCLI()
    monkeypatch.setattr("engine.server.server._discover_doxoade_root", lambda: "/tmp/doxoade-root")

    env = cli._start_env(None, None, None, None, None, None, None, False, False, False, False)

    assert env["DOXOADE_ROOT"] == "/tmp/doxoade-root"
