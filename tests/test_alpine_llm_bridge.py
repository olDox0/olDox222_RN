"""Regressões de portabilidade do SiCDoxBridge."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import engine.core.llm_bridge as llm_bridge
from engine.core.llm_bridge import BridgeConfig, SiCDoxBridge


def test_bridge_config_uses_orn_model_path(monkeypatch, tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    monkeypatch.setenv("ORN_MODEL_PATH", str(model))
    monkeypatch.delenv("ORN_MODEL_ALIAS", raising=False)

    cfg = BridgeConfig()

    assert cfg.model_path == model


def test_explicit_model_path_precedes_environment(monkeypatch, tmp_path: Path) -> None:
    env_model = tmp_path / "env-model.gguf"
    explicit_model = tmp_path / "explicit-model.gguf"
    monkeypatch.setenv("ORN_MODEL_PATH", str(env_model))

    cfg = BridgeConfig(model_path=str(explicit_model))

    assert cfg.model_path == explicit_model
    assert isinstance(cfg.model_path, Path)


def test_native_backend_off_disables_auto_discovery(
    monkeypatch, tmp_path: Path
) -> None:
    model = tmp_path / "model.gguf"
    model.touch()
    native_library = tmp_path / "liborn.so"
    native_library.touch()
    monkeypatch.setenv("ORN_NATIVE_BACKEND", "0")
    monkeypatch.delenv("ORN_MODEL_PATH", raising=False)
    monkeypatch.setattr(
        llm_bridge, "_find_native_library", lambda: native_library
    )

    class UnexpectedNativeBackend:
        def __init__(self, **_kwargs):
            raise AssertionError("backend nativo não deveria ser inicializado")

    import engine.core.native_backend as native_module

    monkeypatch.setattr(native_module, "NativeBackend", UnexpectedNativeBackend)

    class FakeLlama:
        def __init__(self, **_kwargs):
            pass

        def tokenize(self, _text, special=False):
            return [1, 2]

    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=FakeLlama))

    bridge = SiCDoxBridge(
        BridgeConfig(
            model_path=model,
            n_ctx=128,
            active_window=64,
            n_batch=16,
            rope_freq_base=None,
            flash_attn=False,
            no_alloc=False,
            cont_batching=False,
        )
    )
    bridge._load()

    assert bridge._native is None
    assert isinstance(bridge._llm, FakeLlama)


def test_shutdown_releases_native_backend_and_stats_reports_it() -> None:
    class FakeNative:
        _ready = True

        def __init__(self) -> None:
            self.closed = False

        def shutdown(self) -> None:
            self.closed = True
            self._ready = False

    bridge = SiCDoxBridge(BridgeConfig(model_path=Path("unused.gguf")))
    native = FakeNative()
    bridge._native = native

    assert bridge.stats()["model_loaded"] is True

    bridge.shutdown()

    assert native.closed is True
    assert bridge._native is None
    assert bridge.stats()["model_loaded"] is False
