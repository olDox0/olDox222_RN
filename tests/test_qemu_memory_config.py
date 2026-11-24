"""Testes de configuração da memória do QEMU daemon."""

import pytest

from engine.tools.qemu_daemon import (
    DEFAULT_QEMU_RAM_MB,
    MAX_QEMU_RAM_MB,
    MIN_QEMU_RAM_MB,
    _resolve_qemu_memory_mb,
)


def test_default_ram_preserves_legacy_value(monkeypatch):
    monkeypatch.delenv("ORN_QEMU_RAM_MB", raising=False)
    assert _resolve_qemu_memory_mb() == DEFAULT_QEMU_RAM_MB == 512


def test_ram_can_be_set_by_environment(monkeypatch):
    monkeypatch.setenv("ORN_QEMU_RAM_MB", "1280")
    assert _resolve_qemu_memory_mb() == 1280


def test_explicit_argument_overrides_environment(monkeypatch):
    monkeypatch.setenv("ORN_QEMU_RAM_MB", "2048")
    assert _resolve_qemu_memory_mb(1280) == 1280


@pytest.mark.parametrize("value", ["invalid", "1280.5", "-512", "255", "8193", ""])
def test_invalid_ram_is_rejected(value, monkeypatch):
    monkeypatch.setenv("ORN_QEMU_RAM_MB", value)
    if value == "":
        assert _resolve_qemu_memory_mb() == DEFAULT_QEMU_RAM_MB
    else:
        with pytest.raises(ValueError):
            _resolve_qemu_memory_mb()


def test_ram_range_boundaries_are_accepted():
    assert _resolve_qemu_memory_mb(MIN_QEMU_RAM_MB) == MIN_QEMU_RAM_MB
    assert _resolve_qemu_memory_mb(MAX_QEMU_RAM_MB) == MAX_QEMU_RAM_MB
