import importlib
import types


def test_server_entrypoint_importable_without_doxo_runtime() -> None:
    mod = importlib.import_module("engine.server.__main__")
    assert hasattr(mod, "main")


def test_server_main_dispatches_args(monkeypatch) -> None:
    mod = importlib.import_module("engine.server.__main__")
    captured = {}

    class FakeServerCLI:
        def run(self, args):
            captured["args"] = list(args)

    monkeypatch.setattr(mod, "ServerCLI", FakeServerCLI)
    monkeypatch.setattr(mod.sys, "argv", ["orn-server", "status"])

    mod.main()
    assert captured["args"] == ["status"]


def test_web_main_dispatches_args(monkeypatch) -> None:
    mod = importlib.import_module("engine.web.__main__")
    captured = {}

    class FakeWebCLI:
        def run(self, args):
            captured["args"] = list(args)

    fake_module = types.SimpleNamespace(WebCLI=FakeWebCLI)
    monkeypatch.setitem(mod.sys.modules, "engine.web.web_server", fake_module)
    monkeypatch.setattr(mod.sys, "argv", ["orn-web", "start", "--port", "9000"])

    mod.main()
    assert captured["args"] == ["start", "--port", "9000"]
