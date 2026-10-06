# tests/bench_tokenizer_reuse.py
"""
Benchmark de reutilização do tokenizer.
Objetivo: Demonstrar que o tokenizer é lento apenas na primeira carga.
Typhon: onde=tests/, oque=reutilização de tokenizer, quem=bench_tokenizer_reuse
quando=Fase 3, porquê=otimizar pipeline de treino, origem=engine/training/
consequência=se falhar, revisar cache do HuggingFace Hub.
"""
import time
from transformers import AutoTokenizer

def bench_tokenizer_load():
    """Mede o tempo de carregamento do tokenizer em múltiplas chamadas."""
    model_id = "HuggingFaceTB/SmolLM2-135M-Instruct"
    
    print("="*60)
    print(" BENCHMARK: Tokenizer Reuse ")
    print("="*60)
    
    # Carga 1 (inicialização completa)
    print("\n[LOAD 1] Primeira carga (inicialização BPE)...")
    t0 = time.perf_counter()
    tokenizer1 = AutoTokenizer.from_pretrained(model_id)
    load1_ms = (time.perf_counter() - t0) * 1000
    print(f"  Tempo: {load1_ms:.0f}ms")
    
    # Carga 2 (reutilização)
    print("\n[LOAD 2] Segunda carga (reutilização)...")
    t0 = time.perf_counter()
    tokenizer2 = AutoTokenizer.from_pretrained(model_id)
    load2_ms = (time.perf_counter() - t0) * 1000
    print(f"  Tempo: {load2_ms:.0f}ms")
    
    # Carga 3 (reutilização)
    print("\n[LOAD 3] Terceira carga (reutilização)...")
    t0 = time.perf_counter()
    tokenizer3 = AutoTokenizer.from_pretrained(model_id)
    load3_ms = (time.perf_counter() - t0) * 1000
    print(f"  Tempo: {load3_ms:.0f}ms")
    
    # Tokenização
    print("\n[TOKENIZE] Teste de tokenização (128 tokens)...")
    text = "def somar(a: int, b: int) -> int:\n    return a + b" * 10
    
    t0 = time.perf_counter()
    tokens = tokenizer1(text, truncation=True, max_length=128, return_tensors="pt")
    tokenize_ms = (time.perf_counter() - t0) * 1000
    print(f"  Tempo: {tokenize_ms:.0f}ms")
    print(f"  Tokens: {tokens['input_ids'].shape[1]}")
    
    # Resumo
    print("\n" + "="*60)
    print(" RESUMO ")
    print("="*60)
    print(f"  Load 1 (inicial):  {load1_ms:7.0f}ms")
    print(f"  Load 2 (reuso):    {load2_ms:7.0f}ms")
    print(f"  Load 3 (reuso):    {load3_ms:7.0f}ms")
    print(f"  Tokenize (128):    {tokenize_ms:7.0f}ms")
    print(f"\n  ⚠ Gargalo: Load 1 ({load1_ms:.0f}ms)")
    print(f"  ✔ Otimização: Reutilizar tokenizer ({load2_ms:.0f}ms)")
    
    return {
        "load1_ms": load1_ms,
        "load2_ms": load2_ms,
        "load3_ms": load3_ms,
        "tokenize_ms": tokenize_ms,
    }

if __name__ == "__main__":
    results = bench_tokenizer_load()
