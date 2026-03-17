from engine.tools.local_index import _format_snippet_for_terminal, _normalize_math_text


def test_normalize_math_text_compacts_tokenized_formula() -> None:
    raw = """
    O
    (
    n
    log
    n
    )
    {\\displaystyle {O}(n\\log n)}
    """
    normalized = _normalize_math_text(raw)
    assert normalized == "{O}(n\\log n)"


def test_format_snippet_for_terminal_renders_code_and_math_blocks() -> None:
    snippet = """Intro
[CODE-BEGIN python]
def quicksort(a):
    return a
[CODE-END]
e
[MATH-BEGIN]
O
(
n
log
n
)
{\\displaystyle {O}(n\\log n)}
[MATH-END]
"""

    rendered = _format_snippet_for_terminal(snippet)
    assert "```python" in rendered
    assert "def quicksort(a):" in rendered
    assert "$$" in rendered
    assert "{O}(n\\log n)" in rendered
    assert "[CODE-BEGIN" not in rendered
    assert "[MATH-BEGIN" not in rendered
