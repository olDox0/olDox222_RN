import engine.__main__ as entrypoint
import engine.cli as cli_module


def test_main_falls_back_on_vulcan_signature_typeerror(monkeypatch) -> None:
    called = []

    def broken_cli() -> None:
        raise TypeError("cli_vulcan_optimized() takes exactly 1 positional argument (0 given)")

    def fallback_cli() -> None:
        called.append(True)

    monkeypatch.setattr(cli_module, "cli", broken_cli)
    monkeypatch.setattr(entrypoint, "_load_python_cli_fallback", lambda: fallback_cli)

    entrypoint.main()
    assert called == [True]


def test_wrapper_signature_detector_supports_click_ctx_message() -> None:
    exc = TypeError("cli_vulcan_optimized() missing 1 required positional argument: 'ctx'")
    assert entrypoint._is_wrapper_signature_type_error(exc)


def test_main_reraises_unrelated_typeerror(monkeypatch) -> None:
    def broken_cli() -> None:
        raise TypeError("unsupported operand type(s)")

    monkeypatch.setattr(cli_module, "cli", broken_cli)

    try:
        entrypoint.main()
    except TypeError as exc:
        assert "unsupported operand type(s)" in str(exc)
    else:
        raise AssertionError("expected TypeError to be re-raised")


def test_main_does_not_fallback_for_generic_signature_error(monkeypatch) -> None:
    def broken_cli() -> None:
        raise TypeError("foo() missing 1 required positional argument: 'x'")

    monkeypatch.setattr(cli_module, "cli", broken_cli)

    try:
        entrypoint.main()
    except TypeError as exc:
        assert "foo() missing 1 required positional argument" in str(exc)
    else:
        raise AssertionError("expected TypeError to be re-raised")
