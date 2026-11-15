from engine.thinking.code_hook import apply_code_hook
from engine.tools.qemu_daemon import QemuDaemon


class MockBridgeCorrige:
    """Simula modelo: 1ª resposta quebrada, 2ª corrigida."""
    def __init__(self):
        self.calls = 0

    def ask(self, prompt, max_tokens=256, **kw):
        self.calls += 1
        print(f"    [MOCK] chamada #{self.calls}")
        if self.calls == 1:
            # Ainda quebrado (erro sintático proposital)
            return (
                "```c\n#include <stdio.h>\n"
                "int main() {\n"
                "    int x = ;\n"
                "    return 0;\n"
                "}\n```"
            )
        # Corrigido
        return (
            "```c\n#include <stdio.h>\n"
            "int main() {\n"
            "    int x = 42;\n"
            "    printf(\"corrigido na tentativa 2: %d\\n\", x);\n"
            "    return 0;\n"
            "}\n```"
        )


class _MockValidator:
    def validar_output(self, text, lang=None):
        return True, ""


if __name__ == "__main__":
    d = QemuDaemon()
    print(f"Daemon: {d.status().summary()}\n")

    # C com erro sintático — falta expressão depois de '='
    c_quebrado = (
        "#include <stdio.h>\n"
        "int main() {\n"
        "    int x = ;\n"
        "    return 0;\n"
        "}\n"
    )

    bridge = MockBridgeCorrige()
    saida = apply_code_hook(
        output=c_quebrado,
        task="inicializar x com 42 e imprimir",
        bridge=bridge,
        validator=_MockValidator(),
        max_retries=2,
        run_isolated=True,
    )

    print(f"\nMock chamado {bridge.calls} vez(es)")
    print("\n--- SAÍDA FINAL ---")
    print(saida)
