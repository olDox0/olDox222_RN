# tests/test_smol_basic.py
"""Teste básico de inferência do SmolLM 135M."""
import os
import sys
import time
from pathlib import Path

# --- BLOCO DE INJEÇÃO DE DLL (Obrigatório no Windows 11) ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
dll_dirs = [
    PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "llama_cpp" / "lib",
    Path(sys.prefix) / "Lib" / "site-packages" / "llama_cpp" / "lib",
    Path(r"C:\winlibs\mingw64\bin"),  # Dependências do MinGW
]
for d in dll_dirs:
    if d.exists() and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(d))
# -----------------------------------------------------------

from engine.core.llm_bridge import BridgeConfig

def test_smol_load():
    """Plano A: Carrega modelo e faz 1 inferência."""
    try:
        from llama_cpp import Llama
    except ImportError:
        print("[ERRO] llama-cpp-python não encontrado.")
        return False
    
    cfg = BridgeConfig.smol_profile()
    if not cfg.model_path.exists():
        print(f"[ERRO] Modelo não encontrado: {cfg.model_path}")
        return False
    
    print(f"[INFO] Carregando {cfg.model_path.name}...")
    t0 = time.perf_counter()
    
    llm = Llama(
        model_path=str(cfg.model_path),
        n_ctx=cfg.n_ctx,
        n_threads=cfg.n_threads,
        n_batch=cfg.n_batch,
        n_gpu_layers=cfg.n_gpu_layers,
        verbose=False,
    )
    load_ms = (time.perf_counter() - t0) * 1000
    print(f"[OK] Modelo carregado em {load_ms:.0f}ms ({load_ms/1000:.2f}s)")
    
    print("[INFO] Testando inferência (Conte até 3)...")
    prompt = (
        "<|im_start|>system\nsuccinct response. portuguese language<|im_end|>\n"
        "<|im_start|>user\nOla, conte ate 3.<|im_end|>\n"
        "<|im_start|>assistant\n"
    )
    
    t0 = time.perf_counter()
    output = llm(
        prompt,
        max_tokens=32,
        temperature=0.5,
        stop=["<|im_end|>"],
    )
    infer_ms = (time.perf_counter() - t0) * 1000
    
    text = output["choices"][0]["text"].strip()
    tokens = output["usage"]["completion_tokens"]
    tps = tokens / (infer_ms / 1000) if infer_ms > 0 else 0
    
    print(f"[OK] Resposta: {text!r}")
    print(f"[OK] Tempo: {infer_ms:.0f}ms | Tokens: {tokens} | {tps:.2f} tok/s")
    
    llm.close()
    return True

if __name__ == "__main__":
    print("="*60)
    print(" INICIANDO TESTE SMOLLM 135M (PC-B Bluebaby) ")
    print("="*60)
    ok = test_smol_load()
    print("="*60)
    print(f" RESULTADO FINAL: {'✔ SUCESSO' if ok else '✘ FALHA'} ")
    print("="*60)
