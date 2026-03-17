import types

import pytest

import engine.tools.local_index as li


def test_build_index_missing_file_includes_close_match_hint(monkeypatch, tmp_path) -> None:
    zim_dir = tmp_path / "zim"
    zim_dir.mkdir()
    (zim_dir / "wikipedia_en_chemistry_mini_2026-01.zim").write_text("x", encoding="utf-8")

    monkeypatch.setattr(li, "ZIM_DIR", zim_dir)
    monkeypatch.setitem(__import__("sys").modules, "pyzim", types.SimpleNamespace())

    with pytest.raises(FileNotFoundError) as exc:
        li.build_index(str(tmp_path / "wikipedia_en_chemistry_mini_2026_01.zim"))

    msg = str(exc.value)
    assert "ZIM não encontrado" in msg
    assert "Sugestões próximas" in msg
    assert "wikipedia_en_chemistry_mini_2026-01.zim" in msg
