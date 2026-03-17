from engine.tools.local_index import _score_code_only_match


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
