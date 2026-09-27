from engine.tools.local_index import _format_code_only_body, _score_code_only_match


def test_code_only_requires_language_alignment_when_query_mentions_language() -> None:
    body = """
[CODE-BEGIN java]
public class QuickSort { }
[CODE-END]
"""
    passed, tf, matched, total = _score_code_only_match(body, "quicksort python", ["quicksort", "python"])
    assert not passed
    assert tf == 0.0
    assert matched == 1
    assert total == 2


def test_code_only_passes_with_matching_language_and_terms() -> None:
    body = """
[CODE-BEGIN python]
def quicksort(nums):
    return sorted(nums)
[CODE-END]
"""
    passed, tf, matched, total = _score_code_only_match(body, "quicksort python", ["quicksort", "python"])
    assert passed
    assert tf > 0
    assert matched == 2
    assert total == 2


def test_code_only_rejects_low_term_coverage_for_multi_term_queries() -> None:
    body = """
[CODE-BEGIN python]
def quicksort(nums):
    return nums
[CODE-END]
"""
    passed, tf, matched, total = _score_code_only_match(body, "quicksort pivot python", ["quicksort", "pivot", "python"])
    assert not passed
    assert tf == 0.0
    assert matched == 2
    assert total == 3


def test_code_only_allows_language_query_when_code_blocks_have_no_lang_metadata() -> None:
    body = """
[CODE-BEGIN]
def quicksort(nums):
    if len(nums) < 2:
        return nums
[CODE-END]
"""
    passed, tf, matched, total = _score_code_only_match(body, "quicksort python", ["quicksort", "python"])
    assert passed
    assert tf > 0
    assert matched == 1
    assert total == 2


def test_format_code_only_body_keeps_only_code_blocks() -> None:
    body = """Texto fora
[CODE-BEGIN python]
print('x')
[CODE-END]
mais texto
[CODE-BEGIN]
SELECT 1;
[CODE-END]
"""
    out = _format_code_only_body(body)
    assert "Texto fora" not in out
    assert "mais texto" not in out
    assert "[CODE-BEGIN python]" in out
    assert "SELECT 1;" in out
