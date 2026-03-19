from engine.thinking.assembler import CodeAssembler


class _BridgeOK:
    def __init__(self):
        self.prompts = []

    def ask(self, prompt: str, max_tokens: int = 0) -> str:
        self.prompts.append((prompt, max_tokens))
        return """```python
class Pipeline:
    def run(self, payload: dict[str, str]) -> dict[str, str]:
        pass
```"""


class _BridgeBrokenThenFixed:
    def __init__(self):
        self.calls = 0

    def ask(self, prompt: str, max_tokens: int = 0) -> str:
        self.calls += 1
        if self.calls == 1:
            return "```python\ndef bad(:\n    pass\n```"
        return "```python\ndef good(a: int) -> int:\n    pass\n```"


class _BridgeAlwaysBroken:
    def ask(self, prompt: str, max_tokens: int = 0) -> str:
        return "```python\ndef bad(:\n    pass\n```"


class _Validator:
    def validar_output(self, output: str, lang: str | None = None):
        return True, ""


def test_assemble_uses_io_heuristics_and_succeeds():
    bridge = _BridgeOK()
    assembler = CodeAssembler(bridge=bridge, validator=_Validator())

    result = assembler.assemble(
        "Gerar codigo para API que lê JSON e publica relatório com telemetria"
    )

    assert result["success"] is True
    assert result["strategy"] == "io_heuristic"
    assert "IN=input_document,remote_payload" in result["io_hint"]
    assert "OUT=report_text,code_artifact,observability" in result["io_hint"]
    assert "class Pipeline" in result["output"]


def test_assemble_retries_syntax_fix_and_recovers():
    bridge = _BridgeBrokenThenFixed()
    assembler = CodeAssembler(bridge=bridge, validator=_Validator())

    result = assembler.assemble("Criar script de processamento")

    assert result["success"] is True
    assert bridge.calls == 2
    assert "def good" in result["output"]


def test_assemble_fallback_when_syntax_never_recovers():
    assembler = CodeAssembler(bridge=_BridgeAlwaysBroken(), validator=_Validator())

    result = assembler.assemble("montar sistema")

    assert result["success"] is False
    assert result["strategy"] == "fallback"
    assert "assemble_io_contract" in result["output"]
