from engine.tools.code_sandbox import lint_python_text


def test_lint_detects_incomplete_function_and_class() -> None:
    code = """
class Service:
    pass

def run(a: int) -> int:
    pass
"""
    issues = lint_python_text(code)
    assert any("classe 'Service' está incompleta" in i for i in issues)
    assert any("função 'run' está incompleta" in i for i in issues)


def test_lint_detects_mutable_default_and_undefined_name() -> None:
    code = """
def bad(payload: dict = {}):
    return missing_name
"""
    issues = lint_python_text(code)
    assert any("default mutável" in i for i in issues)
    assert any("nome possivelmente indefinido" in i for i in issues)


def test_lint_detects_zero_division_pattern() -> None:
    code = """
def calc(v: int) -> float:
    return v / 0
"""
    issues = lint_python_text(code)
    assert any("divisão/módulo por zero" in i for i in issues)
