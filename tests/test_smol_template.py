# tests/test_smol_template.py
"""Testa diferentes templates de prompt para SmolLM 135M."""
from llama_cpp import Llama
from pathlib import Path

model_path = Path("models/smol_sys/SmolLM2-135M-Instruct-Q4_K_M.gguf")
llm = Llama(model_path=str(model_path), n_ctx=2048, n_threads=8, verbose=False)

# Template 1: ChatML (Qwen-style)
prompt1 = (
    "<|im_start|>system\nVocê é um assistente útil. Responda em português.<|im_end|>\n"
    "<|im_start|>user\nConte até 3.<|im_end|>\n"
    "<|im_start|>assistant\n"
)

# Template 2: Simple (SmolLM-style)
prompt2 = (
    "System: Você é um assistente útil. Responda em português.\n"
    "User: Conte até 3.\n"
    "Assistant:"
)

# Template 3: Direct (sem system)
prompt3 = (
    "Conte até 3 em português:\n"
)

for i, prompt in enumerate([prompt1, prompt2, prompt3], 1):
    print(f"\n{'='*60}")
    print(f"TEMPLATE {i}")
    print(f"{'='*60}")
    output = llm(prompt, max_tokens=32, temperature=0.5, stop=["<|im_end|>", "User:", "Assistant:"])
    text = output["choices"][0]["text"].strip()
    print(f"Resposta: {text!r}")

llm.close()
