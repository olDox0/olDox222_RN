# tests/test_lora_lean.py
"""
Inferência Lean com LoRA Nativo (Sem PyTorch/Transformers).
Objetivo: Validar carregamento de adapter no N2808 com footprint mínimo.
Typhon: onde=tests/, oque=inferência lean, quem=llama_cpp.Llama
quando=Pré-deploy N2808, porquê=eliminar gordura do PyTorch.
"""
import time
from pathlib import Path
from llama_cpp import Llama

# Configuração Ultra-Leve para N2808
MODEL_PATH = Path("models/smol_sys/SmolLM2-135M-Instruct-Q2_K.gguf") # Ou Q4_K_M se preferir
LORA_PATH = Path("data/training/lora_adapter_peft/adapter_model.safetensors") # O adapter que treinamos

def test_lean_inference():
    if not MODEL_PATH.exists():
        print(f"[ERRO] Modelo não encontrado: {MODEL_PATH}")
        return False
        
    print("="*60)
    print(" INFERÊNCIA LEAN (N2808 OPTIMIZED) ")
    print("="*60)
    
    print(f"\n[1/3] Carregando modelo base ({MODEL_PATH.name})...")
    t0 = time.perf_counter()
        
    # tests/test_lora_lean.py
    # Linha ~25: comente o lora_path
    llm = Llama(
        model_path=str(MODEL_PATH),
        # lora_path=str(LORA_PATH) if LORA_PATH.exists() else None,  # ← COMENTE ESTA LINHA
        n_ctx=1024,
        n_threads=8,  # i5-1235U tem 10 cores
        n_batch=256,
        n_gpu_layers=0,
        verbose=False,
        use_mmap=True,
        use_mlock=False,
    )
    
    load_ms = (time.perf_counter() - t0) * 1000
    print(f"  ✔ Carregado em {load_ms:.0f}ms ({load_ms/1000:.2f}s)")
    
    print("\n[2/3] Testando inferência com Adapter...")
    prompt = "def somar(a: int, b: int) -> int:\n"
    
    t0 = time.perf_counter()
    output = llm(
        prompt,
        max_tokens=64,
        temperature=0.2,     # Baixa temperatura para código
        stop=["\n\n", "def ", "class "],
    )
    infer_ms = (time.perf_counter() - t0) * 1000
    
    text = output["choices"][0]["text"].strip()
    tokens = output["usage"]["completion_tokens"]
    tps = tokens / (infer_ms / 1000) if infer_ms > 0 else 0
    
    print(f"  Prompt: {prompt.strip()}")
    print(f"  Resposta:\n{text}")
    print(f"\n  ✔ Tempo: {infer_ms:.0f}ms | Tokens: {tokens} | {tps:.2f} tok/s")
    
    print("\n[3/3] Liberando memória...")
    llm.close()
    print("  ✔ Memória liberada.")
    
    return True

if __name__ == "__main__":
    success = test_lean_inference()
    print(f"\n{'✔ SUCESSO' if success else '✘ FALHA'}")
