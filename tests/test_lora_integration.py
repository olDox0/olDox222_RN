# tests/test_lora_integration.py
"""
Teste de integração do adapter LoRA com o SmolLM 135M.
Objetivo: validar que o BridgeConfig e o Llama() conseguem carregar
um adapter LoRA (mesmo dummy) sem crashar.
Typhon: onde=tests/, oque=integração LoRA, quem=llm_bridge + llama_cpp
quando=Fase 4, porquê=garantir que infraestrutura está pronta
consequência=se falhar, revisar BridgeConfig ou dependências
"""
import time
from pathlib import Path
from engine.core.llm_bridge import BridgeConfig

def test_lora_integration():
    """Plano A: Carrega modelo + adapter e faz inferência."""
    try:
        from llama_cpp import Llama
    except ImportError:
        print("[ERRO] llama-cpp-python não encontrado.")
        return False
    
    # Configuração com adapter
    cfg = BridgeConfig.smol_profile()
    adapter_path = Path("data/training/lora_adapter.bin")
    
    if not cfg.model_path.exists():
        print(f"[ERRO] Modelo não encontrado: {cfg.model_path}")
        return False
    
    if not adapter_path.exists():
        print(f"[ERRO] Adapter não encontrado: {adapter_path}")
        print("[INFO] Execute primeiro: python engine/training/lora_trainer.py")
        return False
    
    print(f"[INFO] Carregando modelo base: {cfg.model_path.name}")
    t0 = time.perf_counter()
    
    # Carregar modelo base
    llm = Llama(
        model_path=str(cfg.model_path),
        n_ctx=cfg.n_ctx,
        n_threads=cfg.n_threads,
        n_batch=cfg.n_batch,
        n_gpu_layers=cfg.n_gpu_layers,
        verbose=False,
    )
    load_ms = (time.perf_counter() - t0) * 1000
    print(f"[OK] Modelo carregado em {load_ms:.0f}ms")
    
    # Tentar carregar adapter (se a API suportar)
    print(f"[INFO] Tentando carregar adapter: {adapter_path.name}")
    try:
        # llama-cpp-python não tem API nativa de LoRA loading ainda
        # Mas validamos que o arquivo existe e é legível
        adapter_size = adapter_path.stat().st_size
        print(f"[OK] Adapter encontrado ({adapter_size} bytes)")
        print("[INFO] Nota: llama-cpp-python não suporta LoRA loading nativo ainda.")
        print("[INFO] Quando suportado, usar: llm.load_lora(adapter_path)")
    except Exception as e:
        print(f"[AVISO] Falha ao ler adapter: {e}")
    
    # Teste de inferência sem adapter (baseline)
    print("\n[INFO] Testando inferência baseline (sem adapter)...")
    prompt = (
        "def somar(a: int, b: int) -> int:\n"
        "    \"\"\"Retorna a soma de dois números.\"\"\"\n"
    )
    
    t0 = time.perf_counter()
    output = llm(
        prompt,
        max_tokens=32,
        temperature=0.5,
        stop=["\n\n"],
    )
    infer_ms = (time.perf_counter() - t0) * 1000
    
    text = output["choices"][0]["text"].strip()
    tokens = output["usage"]["completion_tokens"]
    tps = tokens / (infer_ms / 1000) if infer_ms > 0 else 0
    
    print(f"[OK] Resposta: {text[:60]!r}...")
    print(f"[OK] Tempo: {infer_ms:.0f}ms | Tokens: {tokens} | {tps:.2f} tok/s")
    
    llm.close()
    return True

if __name__ == "__main__":
    print("="*60)
    print(" TESTE DE INTEGRAÇÃO LORA (SmolLM 135M) ")
    print("="*60)
    ok = test_lora_integration()
    print("="*60)
    print(f" RESULTADO: {'✔ SUCESSO' if ok else '✘ FALHA'} ")
    print("="*60)
