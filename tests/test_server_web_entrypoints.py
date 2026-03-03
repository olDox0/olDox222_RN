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


def test_server_main_fallback_on_wrapper_signature_error(monkeypatch) -> None:
    mod = importlib.import_module("engine.server.__main__")
    called = {}

    class BrokenServerCLI:
        def run(self, args):
            raise TypeError("ServerCLI_vulcan_optimized() missing 1 required positional argument: 'ctx'")

    class FallbackServerCLI:
        def run(self, args):
            called["args"] = list(args)

    monkeypatch.setattr(mod, "ServerCLI", BrokenServerCLI)
    monkeypatch.setattr(mod, "_load_python_server_cli_fallback", lambda: FallbackServerCLI)
    monkeypatch.setattr(mod.sys, "argv", ["orn-server", "status"])

    mod.main()
    assert called["args"] == ["status"]


def test_web_main_reraises_unrelated_typeerror(monkeypatch) -> None:
    mod = importlib.import_module("engine.web.__main__")

    class BrokenWebCLI:
        def run(self, args):
            raise TypeError("unsupported operand type(s)")

    fake_module = types.SimpleNamespace(WebCLI=BrokenWebCLI)
    monkeypatch.setitem(mod.sys.modules, "engine.web.web_server", fake_module)
    monkeypatch.setattr(mod.sys, "argv", ["orn-web", "start"])

    try:
        mod.main()
    except TypeError as exc:
        assert "unsupported operand type(s)" in str(exc)
    else:
        raise AssertionError("expected TypeError to be re-raised")
