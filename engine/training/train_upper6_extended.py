# -*- coding: utf-8 -*-
# engine/training/train_upper6_extended.py
"""
🚀 TREINO ESTENDIDO ORN — UPPER-6 LoRA (200 AMOSTRAS REAIS)
Executa 2 épocas com podamento de autograd nas camadas 0-5.
Ao final, exporta o adaptador e realiza prova de fogo com 2 testes.
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

# 1. Trava nos núcleos de alta performance
torch.set_num_threads(2)

MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
DATASET_PATH = Path("data/training/brunnr_full.jsonl")
OUTPUT_ADAPTER = Path("data/training/lora_adapter_peft_upper6_200")

MAX_SAMPLES = 200
EPOCHS = 2
BATCH_SIZE = 2
GRAD_ACC = 2
LR = 5e-5


def load_dataset_samples(path: Path, max_samples: int):
    print(f"📂 Lendo amostras de: {path} (limite: {max_samples})...")
    if not path.exists():
        raise FileNotFoundError(f"Dataset não encontrado: {path}")

    samples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
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

    print(f"✔ {len(samples)} amostras válidas carregadas.")
    return samples


def main():
    print("=" * 80)
    print("🚀 TREINO ESTENDIDO UPPER-6 LoRA — PROJETO ORN / BRUNNR")
    print(f"   Amostras: {MAX_SAMPLES} │ Épocas: {EPOCHS} │ Camadas: 6 a 11 │ Threads: {torch.get_num_threads()}")
    print("=" * 80)

    # Carga do Modelo e Tokenizer
    t_boot = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        dtype=torch.float32,
        device_map="cpu",
    )

    # Configuração Upper-6 (Poda das camadas 0 a 5)
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        layers_to_transform=list(range(6, 12)),
        layers_pattern="layers",
    )
    model = get_peft_model(model, lora_config)
    model.train()
    
    trainable_k = sum(p.numel() for p in model.parameters() if p.requires_grad) / 1000
    print(f"[BOOT] Modelo pronto em {time.perf_counter() - t_boot:.2f}s │ Parâmetros LoRA: {trainable_k:.1f}k")

    # Preparação de Dados
    raw_texts = load_dataset_samples(DATASET_PATH, MAX_SAMPLES)
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

    batches_per_epoch = len(tokenized_samples) // BATCH_SIZE
    total_steps = batches_per_epoch * EPOCHS
    print(f"[TREINO] {batches_per_epoch} batches/época │ Total de iterações: {total_steps}")
    print("─" * 80)

    t_train_start = time.perf_counter()
    step_times = []
    step_count = 0

    for epoch in range(1, EPOCHS + 1):
        print(f"\n▶ INICIANDO ÉPOCA {epoch}/{EPOCHS}")
        for b_idx in range(batches_per_epoch):
            s_t0 = time.perf_counter()
            step_count += 1

            start_i = b_idx * BATCH_SIZE
            batch_slice = tokenized_samples[start_i : start_i + BATCH_SIZE]
            batch = collator(batch_slice)

            # Forward
            outputs = model(**batch)
            loss = outputs.loss / GRAD_ACC

            # Backward (Autograd encerra na camada 6)
            loss.backward()

            # Optimizer Step
            if step_count % GRAD_ACC == 0:
                optimizer.step()
                optimizer.zero_grad()

            step_ms = (time.perf_counter() - s_t0) * 1000
            step_times.append(step_ms)
            cur_loss = loss.item() * GRAD_ACC
            tk_len = batch["input_ids"].shape[1]

            # Log a cada 10 passos ou nos primeiros
            if step_count <= 3 or step_count % 10 == 0 or step_count == total_steps:
                print(
                    f"  Época {epoch} [{b_idx+1:03d}/{batches_per_epoch}] │ "
                    f"Passo {step_count:03d}/{total_steps} │ Loss: {cur_loss:.4f} │ "
                    f"Tk: {tk_len:3d} │ Tempo: {step_ms:6.1f}ms"
                )

    total_train_s = time.perf_counter() - t_train_start
    avg_step_ms = sum(step_times) / len(step_times)
    min_step_ms = min(step_times)
    max_step_ms = max(step_times)

    print("\n" + "─" * 80)
    print("📊 LAUDO CONSOLIDADO DO TREINO ESTENDIDO:")
    print(f"   • Tempo Total de Treino: {total_train_s:.1f}s ({total_train_s/60:.2f} minutos)")
    print(f"   • Passo Médio:           {avg_step_ms:.1f}ms (Mín: {min_step_ms:.1f}ms | Máx: {max_step_ms:.1f}ms)")
    print(f"   • Loss Final:            {cur_loss:.4f}")

    # Exportação do Adaptador
    print(f"\n💾 Gravando adaptador em: {OUTPUT_ADAPTER}")
    OUTPUT_ADAPTER.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUTPUT_ADAPTER)
    tokenizer.save_pretrained(OUTPUT_ADAPTER)
    print("✔ Adaptador gravado com sucesso.")

    # 2 Provas de Fogo Cognitivas
    print("\n" + "═" * 80)
    print("🧪 PROVA DE FOGO 1: BUSCA BINÁRIA EM PYTHON")
    print("═" * 80)
    model.eval()

    def test_generate(prompt_text: str):
        inputs = tokenizer(prompt_text, return_tensors="pt")
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=140,
                temperature=0.2,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id,
            )
        return tokenizer.decode(out[0], skip_special_tokens=False)

    p1 = "<|im_start|>user\nImplemente uma função de busca binária em Python.<|im_end|>\n<|im_start|>assistant\n"
    print(test_generate(p1))

    print("\n" + "═" * 80)
    print("🧪 PROVA DE FOGO 2: ESTRUTURA DE DADOS (PILHA/STACK)")
    print("═" * 80)
    p2 = "<|im_start|>user\nCrie uma classe Stack em Python com métodos push e pop.<|im_end|>\n<|im_start|>assistant\n"
    print(test_generate(p2))
    print("═" * 80 + "\n")


if __name__ == "__main__":
    main()
