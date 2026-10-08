# -*- coding: utf-8 -*-
# engine/training/opt_matrix_bench.py
"""
🔬 MATRIZ DE OTIMIZAÇÃO ORN — BENCHMARK FORENSE COMPARATIVO
Testa 4 hipóteses de aceleração para CPUs fracas e sistemas embarcados:
  [A] Baseline (FP32 | Q,K,V,O | 4 Threads)
  [B] Precisão Reduzida (BFloat16 AMP em CPU)
  [C] Arquitetura LoRA Lean (Apenas Q, V | Menos FLOPs no Backward)
  [D] Low-RAM Embedded (Gradient Checkpointing ativado | Economia de RAM)
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

MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"


def run_experiment(
    exp_name: str,
    target_modules: list[str],
    use_amp_bf16: bool = False,
    use_grad_ckpt: bool = False,
    num_threads: int = 4,
    steps: int = 10,
) -> dict:
    torch.set_num_threads(num_threads)
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

    if use_grad_ckpt:
        model.gradient_checkpointing_enable()

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=target_modules,
    )
    model = get_peft_model(model, lora_config)
    model.train()

    # Amostras de teste fixas
    sample_texts = [
        "<|im_start|>user\nquicksort python<|im_end|>\n<|im_start|>assistant\ndef q(a): return a if len(a)<=1 else q([x for x in a[1:] if x<=a[0]]) + [a[0]] + q([x for x in a[1:] if x>a[0]])<|im_end|>",
        "<|im_start|>user\nbuffer circular python<|im_end|>\n<|im_start|>assistant\nclass RingBuffer:\n    def __init__(self, size):\n        self.buf = [None]*size\n        self.head = 0<|im_end|>",
    ] * 5

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

        # Forward com ou sem AMP (BFloat16)
        with prof.span("fwd:gemm", phase="compute", why="Forward Pass"):
            if use_amp_bf16:
                with torch.cpu.amp.autocast(dtype=torch.bfloat16):
                    outputs = model(**batch)
                    loss = outputs.loss
            else:
                outputs = model(**batch)
                loss = outputs.loss

        # Backward
        with prof.span("bwd:gemm", phase="compute", why="Backward Pass"):
            loss.backward()

        optimizer.step()
        optimizer.zero_grad()
        losses.append(loss.item())

    total_time_ms = (time.perf_counter() - t_start) * 1000.0
    fwd_ms = prof.aggregated.get("fwd:gemm", {}).get("total_ms", 0.0)
    bwd_ms = prof.aggregated.get("bwd:gemm", {}).get("total_ms", 0.0)
    ram_peak = prof.initial_metrics["rss_mb"] + max(
        [e.ram_delta_mb for e in prof.events], default=0.0
    )

    del model, optimizer, tokenizer
    gc.collect()

    return {
        "exp": exp_name,
        "total_s": round(total_time_ms / 1000.0, 2),
        "step_avg_ms": round(total_time_ms / steps, 1),
        "fwd_avg_ms": round(fwd_ms / steps, 1),
        "bwd_avg_ms": round(bwd_ms / steps, 1),
        "loss_final": round(losses[-1], 4),
        "threads": num_threads,
    }


def main():
    print("=" * 80)
    print("🔬 MATRIZ DE ESTUDO DE OTIMIZAÇÃO — CPU EMBARCADA (ORN SILICON LAB)")
    print("=" * 80)

    configs = [
        # [1] Baseline atual
        {"exp_name": "1. Baseline (FP32 | QKVO | 4 Th)", "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"], "use_amp_bf16": False, "use_grad_ckpt": False, "num_threads": 4},
        
        # [2] Teste de Precisão Reduzida (AMP BFloat16)
        {"exp_name": "2. BFloat16 AMP (CPU Autocast)",  "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"], "use_amp_bf16": True,  "use_grad_ckpt": False, "num_threads": 4},
        
        # [3] Arquitetura LoRA Lean (Apenas Q e V)
        {"exp_name": "3. Lean LoRA (Apenas Q, V)",      "target_modules": ["q_proj", "v_proj"],                       "use_amp_bf16": False, "use_grad_ckpt": False, "num_threads": 4},
        
        # [4] Perfil de Baixa RAM (Gradient Checkpointing)
        {"exp_name": "4. Low-RAM (Grad Checkpoint)",    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"], "use_amp_bf16": False, "use_grad_ckpt": True,  "num_threads": 4},
        
        # [5] Simulação de Hardware Ultrarrestrito (Celeron N2808: 2 Threads)
        {"exp_name": "5. Perfil N2808 (2 Threads)",      "target_modules": ["q_proj", "v_proj"],                       "use_amp_bf16": False, "use_grad_ckpt": False, "num_threads": 2},
    ]

    results = []
    for cfg in configs:
        print(f"\n▶ Rodando: {cfg['exp_name']}...")
        res = run_experiment(**cfg, steps=10)
        results.append(res)
        print(f"  ✔ Concluído: {res['step_avg_ms']}ms/step │ Loss: {res['loss_final']}")

    print("\n" + "═" * 80)
    print("📊 RESULTADO CONSOLIDADO DA MATRIZ FORENSE")
    print("═" * 80)
    print(f"{'CONFIGURAÇÃO':<32} │ {'PASSO (ms)':>10} │ {'FWD (ms)':>9} │ {'BWD (ms)':>9} │ {'LOSS':>7} │ {'TH':>2}")
    print("─" * 80)
    for r in results:
        print(
            f"{r['exp']:<32} │ {r['step_avg_ms']:>9.1f}ms │ {r['fwd_avg_ms']:>8.1f}ms │ "
            f"{r['bwd_avg_ms']:>8.1f}ms │ {r['loss_final']:>7.4f} │ {r['threads']:>2}"
        )
    print("═" * 80)
    print("💡 Insights esperados:")
    print("  • Se BFloat16 for mais rápido: a CPU estava limitada por largura de banda de memória.")
    print("  • Se Lean (Q,V) mantiver a loss mas for mais rápido: eliminamos cálculo inútil no backward.")
    print("  • O teste de 2 threads revela o baseline exato de viabilidade para o Celeron N2808.")
    print("═" * 80 + "\n")


if __name__ == "__main__":
    main()
