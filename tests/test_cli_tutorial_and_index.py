from click.testing import CliRunner

from engine.cli import cli


def test_orn_index_delegates_to_local_index(monkeypatch) -> None:
    captured = {}

    def fake_cli_main(args):
        captured["args"] = args
        return 0

    import engine.tools.local_index as local_index

    monkeypatch.setattr(local_index, "_cli_main", fake_cli_main)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["index", "search", "wiki_src", "quicksort python", "--code-only"],
    )

    assert result.exit_code == 0
    assert captured["args"] == ["search", "wiki_src", "quicksort python", "--code-only"]


def test_orn_tutorial_lists_core_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["tutorial"])

    assert result.exit_code == 0
    assert "orn server start" in result.output
    assert "orn web start" in result.output
    assert "orn probe status" in result.output
    assert "orn index search" in result.output
    assert "orn drawer add" in result.output
    assert "--drawer-first" in result.output
    assert "--drawer-only" in result.output


def test_orn_index_help_is_forwarded_to_local_index(monkeypatch) -> None:
    captured = {}

    def fake_cli_main(args):
        captured["args"] = args
        return 0

    import engine.tools.local_index as local_index

    monkeypatch.setattr(local_index, "_cli_main", fake_cli_main)

    runner = CliRunner()
    result = runner.invoke(cli, ["index", "--help"])

    assert result.exit_code == 0
    assert captured["args"] == ["--help"]


def test_orn_drawer_add_and_assemble(monkeypatch, tmp_path) -> None:
    drawer_path = tmp_path / "drawer.json"
    src = tmp_path / "quick.py"
    src.write_text("def quicksort(x):\n    return sorted(x)\n", encoding="utf-8")
    monkeypatch.setenv("ORN_CODE_DRAWER_PATH", str(drawer_path))

    runner = CliRunner()
    add = runner.invoke(
        cli,
        [
            "drawer",
            "add",
            "--name",
            "quicksort",
            "--lang",
            "python",
            "--in",
            "list[int]",
            "--out",
            "list[int]",
            "--file",
            str(src),
        ],
    )
    assert add.exit_code == 0

    assemble = runner.invoke(
        cli,
        [
            "drawer",
            "assemble",
            "--name",
            "quicksort",
            "--lang",
            "python",
            "--in",
            "list[int]",
            "--out",
            "list[int]",
        ],
    )
    assert assemble.exit_code == 0
    assert "def quicksort" in assemble.output


def test_orn_drawer_list_flag_alias(monkeypatch, tmp_path) -> None:
    drawer_path = tmp_path / "drawer.json"
    monkeypatch.setenv("ORN_CODE_DRAWER_PATH", str(drawer_path))

    runner = CliRunner()
    result = runner.invoke(cli, ["drawer", "--list"])

    assert result.exit_code == 0
    assert "Drawer vazio" in result.output


def test_orn_think_help_lists_drawer_flags() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["think", "--help"])

    assert result.exit_code == 0
    assert "--drawer-first" in result.output
    assert "--drawer-only" in result.output
    assert "--drawer-auto-save" in result.output


def test_orn_think_drawer_only_short_circuits_model(monkeypatch) -> None:
    import engine.tools.code_drawer as code_drawer_mod

    class _FakeDrawer:
        def assemble(self, **kwargs):
            class _Sn:
                name = "quicksort"
                lang = "python"
                code = "def quicksort(x):\n    return sorted(x)\n"
            return _Sn()

    monkeypatch.setattr(code_drawer_mod, "CodeDrawer", _FakeDrawer)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["think", "faça quicksort python", "--drawer-only"],
    )

    assert result.exit_code == 0
    assert "def quicksort" in result.output
    assert "[drawer-only]" in result.output


def test_orn_think_drawer_only_without_snippet_fails_fast(monkeypatch) -> None:
    import engine.tools.code_drawer as code_drawer_mod

    class _FakeDrawer:
        def assemble(self, **kwargs):
            return None

    monkeypatch.setattr(code_drawer_mod, "CodeDrawer", _FakeDrawer)

    runner = CliRunner()
    result = runner.invoke(cli, ["think", "faça quicksort python", "--drawer-only"])

    assert result.exit_code != 0
    assert "Nenhum snippet compatível no drawer" in result.output
