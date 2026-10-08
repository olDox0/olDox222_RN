# -*- coding: utf-8 -*-
# engine/training/train_production_test.py
"""
🚀 TREINO DE PRODUÇÃO CONTROLADO (100 AMOSTRAS REAIS)
Testa a teoria de silício (2 threads, FP32, Dynamic Padding) e valida
se o modelo gera código funcional sem loops ao final.
"""
from __future__ import annotations

import os
import gc
import time
import json
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, DataCollatorForSeq2Seq
from peft import LoraConfig, get_peft_model, TaskType

# 1. Configuração de Silício validada pelo Lab
torch.set_num_threads(2)

MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
DATASET_PATH = Path("data/training/brunnr_full.jsonl")
OUTPUT_ADAPTER = Path("data/training/lora_adapter_peft_v3")

MAX_SAMPLES = 100
EPOCHS = 2
BATCH_SIZE = 2
GRAD_ACC = 2
LR = 5e-5


def load_real_dataset(path: Path, max_samples: int):
    print(f"📂 Carregando dados reais de: {path} (limite: {max_samples})...")
    if not path.exists():
        raise FileNotFoundError(f"Dataset não encontrado em: {path}")

    samples = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if len(samples) >= max_samples:
                break
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                text = data.get("text", "")
                if text.strip():
                    samples.append(text)
            except Exception:
                continue

    print(f"✔ {len(samples)} amostras reais carregadas.")
    return samples


def main():
    print("=" * 75)
    print(f"🚀 INICIANDO TESTE DE PRODUÇÃO CONTROLADO (SmolLM2-135M LoRA)")
    print(f"   Amostras: {MAX_SAMPLES} │ Épocas: {EPOCHS} │ Threads: {torch.get_num_threads()} │ FP32 Puro")
    print("=" * 75)

    # 1. Carga de Modelo e Tokenizer
    t_boot = time.perf_counter()
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
    print(f"[BOOT] Modelo pronto em {time.perf_counter() - t_boot:.2f}s")

    # 2. Preparação de Dados com Dynamic Padding
    raw_texts = load_real_dataset(DATASET_PATH, MAX_SAMPLES)
    tokenized_samples = []
    for text in raw_texts:
        enc = tokenizer(text, truncation=True, max_length=256)
        tokenized_samples.append({
            "input_ids": enc["input_ids"],
            "labels": list(enc["input_ids"])
        })

    collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, padding=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
    optimizer.zero_grad()

    # Cálculo do total de passos
    batches_per_epoch = len(tokenized_samples) // BATCH_SIZE
    total_steps = batches_per_epoch * EPOCHS
    print(f"[TREINO] {batches_per_epoch} batches/época │ Total de iterações: {total_steps}")

    t_train_start = time.perf_counter()
    step_times = []
    step_count = 0

    print("\n" + "─" * 75)
    for epoch in range(1, EPOCHS + 1):
        print(f"▶ INICIANDO ÉPOCA {epoch}/{EPOCHS}")
        for b_idx in range(batches_per_epoch):
            s_t0 = time.perf_counter()
            step_count += 1

            start_i = b_idx * BATCH_SIZE
            batch_slice = tokenized_samples[start_i : start_i + BATCH_SIZE]
            batch = collator(batch_slice)

            # Forward
            outputs = model(**batch)
            loss = outputs.loss / GRAD_ACC

            # Backward
            loss.backward()

            # Optimizer Step
            if step_count % GRAD_ACC == 0:
                optimizer.step()
                optimizer.zero_grad()

            step_ms = (time.perf_counter() - s_t0) * 1000
            step_times.append(step_ms)
            cur_loss = loss.item() * GRAD_ACC
            tk_len = batch["input_ids"].shape[1]

            # Log a cada 5 passos ou nos primeiros
            if step_count <= 5 or step_count % 5 == 0 or step_count == total_steps:
                print(
                    f"  Época {epoch} [{b_idx+1:02d}/{batches_per_epoch}] │ "
                    f"Passo {step_count:03d}/{total_steps} │ Loss: {cur_loss:.4f} │ "
                    f"Tk: {tk_len:3d} │ Tempo: {step_ms:6.1f}ms"
                )

    total_train_s = time.perf_counter() - t_train_start
    avg_step_ms = sum(step_times) / len(step_times)
    min_step_ms = min(step_times)
    max_step_ms = max(step_times)

    print("─" * 75)
    print(f"\n📊 LAUDO REAL DE TEMPO E CONVERGÊNCIA:")
    print(f"   • Duração Total de Treino: {total_train_s:.1f}s ({total_train_s/60:.2f} minutos)")
    print(f"   • Tempo Médio por Passo:   {avg_step_ms:.1f}ms (Mín: {min_step_ms:.1f}ms | Máx: {max_step_ms:.1f}ms)")
    print(f"   • Loss Final:              {cur_loss:.4f}")

    # 3. Exportação do Adaptador
    print(f"\n💾 Salvando adaptador treinado em: {OUTPUT_ADAPTER}")
    OUTPUT_ADAPTER.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUTPUT_ADAPTER)
    tokenizer.save_pretrained(OUTPUT_ADAPTER)
    print("✔ Adaptador gravado com sucesso.")

    # 4. Prova de Fogo: Inferência imediata na tela
    print("\n" + "═" * 75)
    print("🧪 PROVA DE FOGO: TESTE DE INFERÊNCIA COM O NOVO ADAPTADOR")
    print("═" * 75)
    model.eval()
    
    test_prompt = "<|im_start|>user\nEscreva uma função em Python para calcular fibonacci.<|im_end|>\n<|im_start|>assistant\n"
    inputs = tokenizer(test_prompt, return_tensors="pt")
    
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=96,
            temperature=0.3,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    
    response = tokenizer.decode(out[0], skip_special_tokens=False)
    print(response)
    print("═" * 75 + "\n")


if __name__ == "__main__":
    main()
