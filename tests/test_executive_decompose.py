import sys
import types

sys.modules.setdefault(
    "engine.telemetry.forensic",
    types.SimpleNamespace(emit_forensic_log=lambda *args, **kwargs: None),
)

from engine.core.executive import (
    _decompose_query,
    _looks_degenerate_think_output,
    _deterministic_code_answer,
)


class _Board:
    def __init__(self):
        self.posts = []

    def post_draft(self, source, content, role, weight):
        self.posts.append({"source": source, "content": content, "role": role, "weight": weight})


def _contents(board: _Board):
    return [p["content"] for p in board.posts]


def test_decompose_adds_code_task_for_language_prompt_without_generate_verb():
    board = _Board()

    _decompose_query(board, "buffer python", context={})

    texts = _contents(board)
    assert any("Tarefa: geração de código prático e curto." in t for t in texts)
    assert any("Código esperado em: python." in t for t in texts)


def test_decompose_adds_format_hint_when_search_code_only_context_present():
    board = _Board()

    _decompose_query(
        board,
        "[CTX-BEGIN]\n[CODE-BEGIN]\ndef x():\n    pass\n[CODE-END]\n[TASK]\nbuffer python",
        context={"search_code_only": True},
    )

    texts = _contents(board)
    assert any("entregue primeiro um bloco de código útil e curto" in t for t in texts)


def test_degenerate_output_detection_and_deterministic_softmax_answer():
    assert _looks_degenerate_think_output("buffer python", "[TASK]\nbuffer python") is True
    answer = _deterministic_code_answer("faça softmax python")
    assert "def softmax" in answer
    assert "math.exp" in answer
