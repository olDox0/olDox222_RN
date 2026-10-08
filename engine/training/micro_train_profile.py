# -*- coding: utf-8 -*-
import os
import sys
import time
import json
from pathlib import Path

# Importa o profiler soberano do ORN
from engine.telemetry.orn_profiler import OrnProfiler

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, DataCollatorForSeq2Seq
from peft import LoraConfig, get_peft_model, TaskType

torch.set_num_threads(4)

MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
DATASET_PATH = Path("data/training/brunnr_full.jsonl")


def run_training_loop(steps: int = 30, max_samples: int = 64):
    prof = OrnProfiler(target_name="SmolLM2_135M_LoRA_Train")

    with prof.span("boot:model_load", phase="init", why="Carga inicial dos pesos do SmolLM na RAM"):
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            dtype=torch.float32,
            device_map="cpu",
        )

        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        )
        model = get_peft_model(model, lora_config)
        model.train()

    with prof.span("data:prepare", phase="io", why="Leitura e tokenização prévia das amostras"):
        raw_texts = []
        if DATASET_PATH.exists():
            with open(DATASET_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    if len(raw_texts) >= max_samples:
                        break
                    raw_texts.append(json.loads(line).get("text", ""))

        if not raw_texts:
            raw_texts = [
                "<|im_start|>user\nquicksort em python<|im_end|>\n<|im_start|>assistant\ndef quicksort(arr): return arr<|im_end|>"
            ] * max_samples

        tokenized_samples = []
        for text in raw_texts:
            enc = tokenizer(text, truncation=True, max_length=256)
            tokenized_samples.append({
                "input_ids": enc["input_ids"],
                "labels": list(enc["input_ids"])
            })

        collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, padding=True)
        optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5)

    batch_size = 2
    grad_acc = 2
    optimizer.zero_grad()

    print(f"\n[LOOP] Executando {steps} passos instrumentados via Typhon...")
    for step in range(1, steps + 1):
        # 1. Fase de Batching / Collate Dinâmico
        with prof.span("data:collate", phase="cpu_tensor", why="Dynamic padding do mini-batch"):
            idx = (step * batch_size) % len(tokenized_samples)
            batch_slice = tokenized_samples[idx : idx + batch_size] or tokenized_samples[:batch_size]
            batch = collator(batch_slice)
            token_count = batch["input_ids"].shape[1]

        # 2. Fase de Forward Pass (Multiplicação de Matrizes / Atenção)
        with prof.span("fwd:attention_mlp", phase="cpu_gemm", why="Forward pass das 12 camadas", tokens=token_count):
            outputs = model(**batch)
            loss = outputs.loss / grad_acc

        # 3. Fase de Backward Pass (Cálculo de Gradientes)
        with prof.span("bwd:gradients", phase="cpu_gemm", why="Propagação reversa dos gradientes"):
            loss.backward()

        # 4. Fase de Otimizador (Atualização dos pesos LoRA)
        if step % grad_acc == 0:
            with prof.span("opt:adamw_step", phase="weights", why="Atualização de pesos LoRA"):
                optimizer.step()
                optimizer.zero_grad()

        current_loss = loss.item() * grad_acc
        print(f"  Step {step:02d}/{steps} │ Loss: {current_loss:.4f} │ Tk: {token_count:3d}")

    # Exibe o diagnóstico Typhon completo e salva JSON
    prof.print_typhon_report()
    prof.save_json("telemetry/micro_train_typhon.json")


if __name__ == "__main__":
    run_training_loop(steps=30, max_samples=32)
