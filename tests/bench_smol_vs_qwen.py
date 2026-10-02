# tests/bench_smol_vs_qwen.py
"""Benchmark comparativo SmolLM 135M vs Qwen 0.5B.
Objetivo: Gerar baseline de performance para decisões arquiteturais.
Typhon: onde=tests/, oque=benchmark, quem=llama_cpp.Llama
quando=após validação do ATO 3, porquê=medir ganho real de performance
"""
import time
from pathlib import Path
from llama_cpp import Llama

PROMPTS = [
    ("curto", "Ola, tudo bem?", 32),
    ("medio", "Explique recursao em 2 linhas.", 64),
    ("codigo", "Faca quicksort em python.", 128),
]

def bench_model(name: str, model_path: Path, n_threads: int, n_ctx: int = 2048):
    print(f"\n{'='*60}")
    print(f"MODELO: {name}")
    print(f"{'='*60}")
    
    if not model_path.exists():
        print(f"[ERRO] Modelo não encontrado: {model_path}")
        return
    
    print("[INFO] Carregando modelo...")
    t0 = time.perf_counter()
    llm = Llama(
        model_path=str(model_path),
        n_ctx=n_ctx,
        n_threads=n_threads,
        n_batch=256,
        n_gpu_layers=0,
        verbose=False,
    )
    load_ms = (time.perf_counter() - t0) * 1000
    print(f"[OK] Carregado em {load_ms/1000:.2f}s")
    
    for label, prompt, max_tok in PROMPTS:
        full = (
            "<|im_start|>system\nsuccinct response. portuguese language<|im_end|>\n"
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        t0 = time.perf_counter()
        out = llm(full, max_tokens=max_tok, temperature=0.5, stop=["<|im_end|>"])
        ms = (time.perf_counter() - t0) * 1000
        tok = out["usage"]["completion_tokens"]
        tps = tok / (ms / 1000) if ms > 0 else 0
        print(f"  [{label:6s}] {ms:7.0f}ms | {tok:3d} tok | {tps:5.2f} tok/s | Resposta: {out['choices'][0]['text'].strip()[:30]!r}...")
    
    llm.close()

if __name__ == "__main__":
    print("="*60)
    print(" BENCHMARK COMPARATIVO: ORN PROJ (PC-B Bluebaby) ")
    print("="*60)
    
    # 1. Qwen 0.5B (Baseline atual)
    qwen = Path("models/sicdox/qwen2.5-coder-0.5b-instruct-q2_k.gguf")
    if qwen.exists():
        bench_model("Qwen 0.5B Q2_K (Baseline N2808)", qwen, n_threads=4)
    else:
        print(f"\n[AVISO] Qwen 0.5B não encontrado em {qwen}")
    
    # 2. SmolLM 135M (Novo alvo)
    smol = Path("models/smol_sys/SmolLM2-135M-Instruct-Q4_K_M.gguf")
    if smol.exists():
        bench_model("SmolLM 135M Q4_K_M (PC-B Otimizado)", smol, n_threads=8)
    else:
        print(f"\n[ERRO] SmolLM não encontrado: {smol}")
        
    print("\n" + "="*60)
    print(" BENCHMARK CONCLUÍDO ")
    print("="*60)
