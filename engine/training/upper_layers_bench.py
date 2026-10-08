# -*- coding: utf-8 -*-
# engine/training/upper_layers_bench.py
"""
🔬 BENCHMARK DE TRUNCAMENTO DE CAMADAS (UPPER-LAYERS LoRA)
Compara a latência do backward pass podando o grafo de autograd:
  [A] Todas as Camadas (Layers 0 a 11 - 100%)
  [B] Upper-6 Camadas  (Layers 6 a 11 -  50%)
  [C] Top-4 Camadas    (Layers 8 a 11 -  33%)
"""
from __future__ import annotations

import os
import gc
import time
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, DataCollatorForSeq2Seq
from peft import LoraConfig, get_peft_model, TaskType

from engine.telemetry.orn_profiler import OrnProfiler

torch.set_num_threads(2)
MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"


def run_layer_experiment(exp_name: str, layers_to_transform: list[int] | None, steps: int = 15):
    gc.collect()
    prof = OrnProfiler(target_name=exp_name)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        dtype=torch.float32,
        device_map="cpu",
    )

    # Configuração com restrição de camadas
    lora_kwargs = {
        "task_type": TaskType.CAUSAL_LM,
        "r": 8,
        "lora_alpha": 16,
        "lora_dropout": 0.05,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
    }
    
    if layers_to_transform is not None:
        lora_kwargs["layers_to_transform"] = layers_to_transform
        lora_kwargs["layers_pattern"] = "layers"

    lora_config = LoraConfig(**lora_kwargs)
    model = get_peft_model(model, lora_config)
    model.train()

    # Amostras de validação
    sample_texts = [
        "<|im_start|>user\nquicksort python<|im_end|>\n<|im_start|>assistant\ndef q(a): return a if len(a)<=1 else q([x for x in a[1:] if x<=a[0]]) + [a[0]] + q([x for x in a[1:] if x>a[0]])<|im_end|>",
        "<|im_start|>user\nfibonacci python<|im_end|>\n<|im_start|>assistant\ndef fib(n): return n if n<=1 else fib(n-1)+fib(n-2)<|im_end|>",
    ] * 8

    tokenized_samples = []
    for t in sample_texts:
        enc = tokenizer(t, truncation=True, max_length=128)
        tokenized_samples.append({"input_ids": enc["input_ids"], "labels": list(enc["input_ids"])})

    collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, padding=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5)
    optimizer.zero_grad()

    t_start = time.perf_counter()
    losses = []

    for step in range(1, steps + 1):
        batch = collator(tokenized_samples[:2])

        with prof.span("fwd:gemm", phase="compute", why="Forward Pass"):
            outputs = model(**batch)
            loss = outputs.loss

        with prof.span("bwd:gemm", phase="compute", why="Backward Pass"):
            loss.backward()

        optimizer.step()
        optimizer.zero_grad()
        losses.append(loss.item())

    total_time_ms = (time.perf_counter() - t_start) * 1000.0
    fwd_ms = prof.aggregated.get("fwd:gemm", {}).get("total_ms", 0.0)
    bwd_ms = prof.aggregated.get("bwd:gemm", {}).get("total_ms", 0.0)

    # Conta parâmetros treináveis
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    del model, optimizer, tokenizer
    gc.collect()

    return {
        "exp": exp_name,
        "layers": len(layers_to_transform) if layers_to_transform else 12,
        "trainable_k": round(trainable_params / 1000, 1),
        "step_avg_ms": round(total_time_ms / steps, 1),
        "fwd_avg_ms": round(fwd_ms / steps, 1),
        "bwd_avg_ms": round(bwd_ms / steps, 1),
        "loss_final": round(losses[-1], 4),
    }


def main():
    print("=" * 80)
    print("🔬 PROJETO ORN — MATRIZ DE TRUNCAMENTO DE CAMADAS (UPPER-LAYERS)")
    print("=" * 80)

    configs = [
        # 1. Todas as 12 camadas (0 a 11)
        {"exp_name": "1. Full LoRA (12 Camadas: 0-11)",  "layers_to_transform": None},
        
        # 2. Apenas metade superior (6 a 11)
        {"exp_name": "2. Upper-6 (Camadas: 6 a 11)",      "layers_to_transform": list(range(6, 12))},
        
        # 3. Apenas o terço superior (8 a 11)
        {"exp_name": "3. Top-4   (Camadas: 8 a 11)",      "layers_to_transform": list(range(8, 12))},
    ]

    results = []
    for cfg in configs:
        print(f"\n▶ Rodando: {cfg['exp_name']}...")
        res = run_layer_experiment(cfg["exp_name"], cfg["layers_to_transform"], steps=15)
        results.append(res)
        print(f"  ✔ BWD Médio: {res['bwd_avg_ms']}ms │ Passo Médio: {res['step_avg_ms']}ms │ Loss: {res['loss_final']}")

    print("\n" + "═" * 80)
    print("📊 RESULTADO COMPARATIVO DE SILÍCIO")
    print("═" * 80)
    print(f"{'ESTRATÉGIA':<30} │ {'CAMADAS':>7} │ {'PARÂMETROS':>11} │ {'BWD (ms)':>9} │ {'PASSO (ms)':>10} │ {'LOSS':>7}")
    print("─" * 80)
    for r in results:
        print(
            f"{r['exp']:<30} │ {r['layers']:>7} │ {r['trainable_k']:>9}k │ "
            f"{r['bwd_avg_ms']:>8.1f}ms │ {r['step_avg_ms']:>9.1f}ms │ {r['loss_final']:>7.4f}"
        )
    print("═" * 80)


if __name__ == "__main__":
    main()
