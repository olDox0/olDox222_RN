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


def test_orn_think_search_code_only_uses_lower_default_tokens(monkeypatch) -> None:
    import engine.tools.server_client as server_client_mod
    import engine.core.executive as executive_mod

    class _FakeExecutive:
        captured_context = None

        def process_goal(self, intent, payload, context):
            _FakeExecutive.captured_context = context

            class _Result:
                success = True
                output = "ok"
                errors = []
                metadata = {"elapsed_s": 0.01}

            return _Result()

        def shutdown(self):
            return None

    monkeypatch.setattr(server_client_mod, "is_server_online", lambda: False)
    monkeypatch.setattr(executive_mod, "SiCDoxExecutive", _FakeExecutive)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["think", "buffer python", "--search-code-only", "--direct"],
    )

    assert result.exit_code == 0
    assert _FakeExecutive.captured_context is not None
    assert _FakeExecutive.captured_context["max_tokens"] == 96
    assert _FakeExecutive.captured_context["search_code_only"] is True


def test_orn_think_search_code_only_fast_path_uses_drawer_snippet(monkeypatch) -> None:
    import engine.tools.server_client as server_client_mod
    import engine.tools.crawler as crawler_mod
    import engine.tools.code_drawer as code_drawer_mod
    import engine.core.executive as executive_mod

    class _FakeCrawlerResult:
        ok = True
        source = "local"
        title = "Z-buffer"
        context = "[CODE-BEGIN]\ndef z_buffer(items):\n    return list(items)\n[CODE-END]"

        def to_prompt_block(self):
            return "[CTX-BEGIN]\n[CODE-BEGIN]\ndef z_buffer(items):\n    return list(items)\n[CODE-END]\n[CTX-END]"

    class _FakeCrawler:
        def search(self, *args, **kwargs):
            return _FakeCrawlerResult()

    class _FakeDrawer:
        def save_from_context(self, **kwargs):
            return 1

        def assemble(self, **kwargs):
            class _Sn:
                name = "z_buffer"
                lang = "python"
                code = "def z_buffer(items):\n    return list(items)\n"
            return _Sn()

    class _FailExecutive:
        def process_goal(self, *args, **kwargs):
            raise AssertionError("Fast-path deveria evitar inferência no Executive.")

        def shutdown(self):
            return None

    monkeypatch.setattr(server_client_mod, "is_server_online", lambda: False)
    monkeypatch.setattr(crawler_mod, "OrnCrawler", _FakeCrawler)
    monkeypatch.setattr(code_drawer_mod, "CodeDrawer", _FakeDrawer)
    monkeypatch.setattr(executive_mod, "SiCDoxExecutive", _FailExecutive)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["think", "buffer python", "--search", "local:buffer python", "--search-code-only"],
    )

    assert result.exit_code == 0
    assert "SEARCH-CODE-ONLY FAST-PATH" in result.output
    assert "def z_buffer" in result.output


def test_orn_think_search_code_only_skips_fast_path_for_pseudocode(monkeypatch) -> None:
    import engine.tools.server_client as server_client_mod
    import engine.tools.crawler as crawler_mod
    import engine.tools.code_drawer as code_drawer_mod
    import engine.core.executive as executive_mod

    class _FakeCrawlerResult:
        ok = True
        source = "local"
        title = "Z-buffer"
        context = "[CODE-BEGIN]\nAlgoritmo Z-Buffer\nInício\nfim\n[CODE-END]"

        def to_prompt_block(self):
            return "[CTX-BEGIN]\n[CODE-BEGIN]\nAlgoritmo Z-Buffer\nInício\nfim\n[CODE-END]\n[CTX-END]"

    class _FakeCrawler:
        def search(self, *args, **kwargs):
            return _FakeCrawlerResult()

    class _FakeDrawer:
        def save_from_context(self, **kwargs):
            return 1

        def assemble(self, **kwargs):
            class _Sn:
                name = "buffer"
                lang = "python"
                code = "Algoritmo Z-Buffer\nInício\nfim\n"
            return _Sn()

    class _FakeExecutive:
        called = False

        def process_goal(self, *args, **kwargs):
            _FakeExecutive.called = True

            class _Result:
                success = True
                output = "ok"
                errors = []
                metadata = {"elapsed_s": 0.01}

            return _Result()

        def shutdown(self):
            return None

    monkeypatch.setattr(server_client_mod, "is_server_online", lambda: False)
    monkeypatch.setattr(crawler_mod, "OrnCrawler", _FakeCrawler)
    monkeypatch.setattr(code_drawer_mod, "CodeDrawer", _FakeDrawer)
    monkeypatch.setattr(executive_mod, "SiCDoxExecutive", _FakeExecutive)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["think", "buffer python", "--search", "local:buffer python", "--search-code-only"],
    )

    assert result.exit_code == 0
    assert "SEARCH-CODE-ONLY FAST-PATH" not in result.output
    assert _FakeExecutive.called is True


def test_orn_diagnose_passes_on_clean_file(tmp_path) -> None:
    script = tmp_path / "ok.py"
    script.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["diagnose", str(script), "--run"])

    assert result.exit_code == 0
    assert "Diagnóstico OK" in result.output


def test_orn_diagnose_fails_on_bare_except(tmp_path) -> None:
    script = tmp_path / "bad.py"
    script.write_text("try:\n    x = 1\nexcept:\n    x = 2\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["diagnose", str(script)])

    assert result.exit_code != 0
    assert "bare except detectado" in result.output
