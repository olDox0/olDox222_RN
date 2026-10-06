# tests/bench_training_pipeline.py
"""
Diagnóstico de performance do pipeline de treinamento LoRA.
Objetivo: Identificar gargalos em cada etapa (carga, tokenização, treino).
Typhon: onde=tests/, oque=benchmark de treino, quem=bench_training_pipeline
quando=Fase 3, porquê=otimizar tempo de treino, origem=engine/training/
consequência=se falhar, revisar dependências ou hardware.
"""
import time
import torch
from pathlib import Path

def check_pytorch_optimizations():
    """Verifica se o PyTorch está usando instruções otimizadas (AVX2, etc)."""
    print("="*60)
    print(" DIAGNÓSTICO: PyTorch CPU Optimizations ")
    print("="*60)
    
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"Device: {'cuda' if torch.cuda.is_available() else 'cpu'}")
    
    # Verifica se AVX2 está disponível (via numpy)
    try:
        import numpy as np
        # Tenta detectar CPU features via numpy
        print(f"NumPy version: {np.__version__}")
        # NumPy não expõe CPU flags diretamente, mas podemos testar performance
    except ImportError:
        print("NumPy não instalado")
    
    # Teste de performance básica (matmul)
    print("\n[TEST] Benchmark de matmul (detecta otimizações CPU)...")
    a = torch.randn(1000, 1000)
    b = torch.randn(1000, 1000)
    
    t0 = time.perf_counter()
    for _ in range(10):
        c = torch.matmul(a, b)
    elapsed = (time.perf_counter() - t0) * 1000
    
    print(f"  10x matmul(1000x1000): {elapsed:.2f}ms")
    print(f"  Média por matmul: {elapsed/10:.2f}ms")
    
    # Classificação de performance
    if elapsed < 500:
        print("  ✔ Performance EXCELENTE (AVX2/FMA provavelmente ativo)")
    elif elapsed < 1500:
        print("  ⚠ Performance BOA (SSE4.2 provavelmente ativo)")
    else:
        print("  ✘ Performance RUIM (sem otimizações SIMD)")
        print("  → Considere reinstalar PyTorch com flags específicas")
    
    return elapsed

def benchmark_training_stages():
    """Mede cada etapa do pipeline de treinamento."""
    print("\n" + "="*60)
    print(" DIAGNÓSTICO: Training Pipeline Stages ")
    print("="*60)
    
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import LoraConfig, get_peft_model, TaskType
    
    model_id = "HuggingFaceTB/SmolLM2-135M-Instruct"
    dataset_path = Path("data/training/python_code.jsonl")
    
    # Stage 1: Carregamento do Tokenizer
    print("\n[STAGE 1] Carregando tokenizer...")
    t0 = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    load_tok_ms = (time.perf_counter() - t0) * 1000
    print(f"  Tempo: {load_tok_ms:.0f}ms")
    
    # Stage 2: Carregamento do Modelo
    print("\n[STAGE 2] Carregando modelo base...")
    t0 = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        dtype=torch.float32,
        device_map="cpu"
    )
    load_model_ms = (time.perf_counter() - t0) * 1000
    print(f"  Tempo: {load_model_ms:.0f}ms ({load_model_ms/1000:.2f}s)")
    
    # Stage 3: Aplicação do LoRA
    print("\n[STAGE 3] Aplicando configuração LoRA...")
    t0 = time.perf_counter()
    peft_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        inference_mode=False,
        r=4,
        lora_alpha=8,
        lora_dropout=0.1,
        target_modules=["q_proj", "v_proj"],
    )
    model = get_peft_model(model, peft_config)
    apply_lora_ms = (time.perf_counter() - t0) * 1000
    print(f"  Tempo: {apply_lora_ms:.0f}ms")
    model.print_trainable_parameters()
    
    # Stage 4: Preparação do Dataset
    print("\n[STAGE 4] Preparando dataset...")
    t0 = time.perf_counter()
    from engine.training.dataset_loader import prepare_dataset
    texts = prepare_dataset(dataset_path, max_samples=5)
    load_data_ms = (time.perf_counter() - t0) * 1000
    print(f"  Tempo: {load_data_ms:.0f}ms")
    print(f"  Amostras: {len(texts)}")
    
    # Stage 5: Tokenização
    print("\n[STAGE 5] Tokenizando dados...")
    t0 = time.perf_counter()
    encodings = tokenizer(
        texts,
        truncation=True,
        padding="max_length",
        max_length=128,
        return_tensors="pt"
    )
    tokenize_ms = (time.perf_counter() - t0) * 1000
    print(f"  Tempo: {tokenize_ms:.0f}ms")
    
    # Stage 6: Loop de Treino (1 step)
    print("\n[STAGE 6] Treinamento (1 step)...")
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    model.train()
    
    t0 = time.perf_counter()
    input_ids = encodings["input_ids"][0:1]
    attention_mask = encodings["attention_mask"][0:1]
    labels = input_ids.clone()
    
    outputs = model(
        input_ids=input_ids,
        attention_mask=attention_mask,
        labels=labels
    )
    loss = outputs.loss
    loss.backward()
    optimizer.step()
    optimizer.zero_grad()
    train_step_ms = (time.perf_counter() - t0) * 1000
    print(f"  Tempo: {train_step_ms:.0f}ms")
    print(f"  Loss: {loss.item():.4f}")
    
    # Resumo
    print("\n" + "="*60)
    print(" RESUMO DE PERFORMANCE ")
    print("="*60)
    total_ms = load_tok_ms + load_model_ms + apply_lora_ms + load_data_ms + tokenize_ms + train_step_ms
    print(f"  Load tokenizer:  {load_tok_ms:7.0f}ms ({load_tok_ms/total_ms*100:5.1f}%)")
    print(f"  Load model:      {load_model_ms:7.0f}ms ({load_model_ms/total_ms*100:5.1f}%)")
    print(f"  Apply LoRA:      {apply_lora_ms:7.0f}ms ({apply_lora_ms/total_ms*100:5.1f}%)")
    print(f"  Load dataset:    {load_data_ms:7.0f}ms ({load_data_ms/total_ms*100:5.1f}%)")
    print(f"  Tokenize:        {tokenize_ms:7.0f}ms ({tokenize_ms/total_ms*100:5.1f}%)")
    print(f"  Train step:      {train_step_ms:7.0f}ms ({train_step_ms/total_ms*100:5.1f}%)")
    print(f"  ─────────────────────────")
    print(f"  TOTAL:           {total_ms:7.0f}ms ({total_ms/1000:.2f}s)")
    
    # Identificar gargalo
    stages = {
        "Load tokenizer": load_tok_ms,
        "Load model": load_model_ms,
        "Apply LoRA": apply_lora_ms,
        "Load dataset": load_data_ms,
        "Tokenize": tokenize_ms,
        "Train step": train_step_ms,
    }
    bottleneck = max(stages, key=stages.get)
    print(f"\n  ⚠ GARGALO: {bottleneck} ({stages[bottleneck]:.0f}ms)")
    
    return stages

if __name__ == "__main__":
    check_pytorch_optimizations()
    stages = benchmark_training_stages()
