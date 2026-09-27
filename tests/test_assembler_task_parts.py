from engine.thinking.assembler import (
    _ASSEMBLER_MAX_TOKENS,
    _decompose_task_parts,
    _render_parts_plan,
    CodeAssembler,
)


class _BridgeCapture:
    def __init__(self):
        self.calls = []

    def ask(self, prompt: str, max_tokens: int = 0) -> str:
        self.calls.append((prompt, max_tokens))
        return "[code-begin]\ndef ok(a: int) -> int:\n    return a\n[code-end]"


class _Validator:
    def validar_output(self, output: str, lang: str | None = None):
        return True, ""


def test_decompose_task_parts_splits_connectors() -> None:
    parts = _decompose_task_parts("ler arquivo e validar schema; depois gerar relatorio")
    assert len(parts) >= 2
    assert "ler arquivo" in parts[0].lower()


def test_render_parts_plan_has_numbered_lines() -> None:
    rendered = _render_parts_plan(["a", "b"])
    assert "Parte 1" in rendered
    assert "Parte 2" in rendered


def test_assembler_includes_parts_plan_and_higher_token_budget(monkeypatch) -> None:
    bridge = _BridgeCapture()
    assembler = CodeAssembler(bridge=bridge, validator=_Validator(), run_isolated=False)

    monkeypatch.setattr("engine.tools.code_sandbox.stage_code", lambda code, stem="candidate": __import__("pathlib").Path("/tmp/candidate.py"))
    monkeypatch.setattr("engine.tools.code_sandbox.diagnose_python_file", lambda _path: [])

    result = assembler.assemble("ler arquivo e validar schema e gerar relatorio")

    assert result["success"] is True
    assert bridge.calls
    prompt, max_tokens = bridge.calls[0]
    assert "Plano de execução em partes" in prompt
    assert max_tokens == _ASSEMBLER_MAX_TOKENS
