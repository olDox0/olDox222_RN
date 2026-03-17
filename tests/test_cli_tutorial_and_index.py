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
