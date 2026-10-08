# profile_train_v2.py
import time, gc, torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer
from peft import LoraConfig, get_peft_model, TaskType
from datasets import Dataset

MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
DATASET_PATH = Path("data/training/raw_dataset.jsonl") # Ou o dataset que estiver usando
OUTPUT_DIR = Path("data/training/brunnr_lora_profile")
MAX_SAMPLES = 64
STEPS = 15

def main():
    print("=" * 70)
    print("🔬 ORN PROFILER V2: Upper-Layer LoRA + GC Controlado (CPU Nativo)")
    print("=" * 70)
    
    # 1. Carregamento
    t0 = time.perf_counter()
    print("📥 Carregando modelo e tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        dtype=torch.float32,  # Float32 usa AVX2/FMA nativamente no CPU
        device_map="cpu"
    )
    print(f"[OK] Modelo carregado em {time.perf_counter() - t0:.2f}s")

    # 2. Upper-Layer LoRA (A MÁGICA: Apenas camadas 6 a 11)
    print("[INFO] Aplicando Upper-Layer LoRA (camadas 6 a 11)...")
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"],
        layers_to_transform=list(range(6, 12)),  # 🚀 Poda o grafo de backward nas camadas 0-5
        layers_pattern="layers",
    )
    model = get_peft_model(model, lora_config)
    
    # 🚀 CIRURGIA NO AUTOGRAD: Garante que o PyTorch não aloque tensores de gradiente para pesos congelados
    for name, param in model.named_parameters():
        if "lora" not in name:
            param.requires_grad = False
            
    model.print_trainable_parameters()

    # NOTA: torch.compile desativado propositalmente. No Windows, ele exige MSVC (cl.exe).
    # O ganho de velocidade do Upper-Layer LoRA + float32 AVX2 já é suficiente para validar o pipeline.
    print("[INFO] torch.compile desativado (evita dependência de MSVC no Windows).")

    # 3. Dados
    print("[INFO] Preparando dados...")
    import json
    texts = []
    if DATASET_PATH.exists():
        with open(DATASET_PATH, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= MAX_SAMPLES: break
                try: 
                    data = json.loads(line)
                    texts.append(data.get("text", data.get("instruction", "") + " " + data.get("output", "")))
                except: pass
    else:
        texts = ["<|im_start|>user\nEscreva uma função Python de quicksort.<|im_end|>\n<|im_start|>assistant\ndef quicksort(arr): return arr"] * MAX_SAMPLES

    def tokenize_function(examples):
        tokenized = tokenizer(
            examples["text"],
            truncation=True,
            max_length=256,
            padding="max_length",
        )
        tokenized["labels"] = tokenized["input_ids"].copy() # Obrigatório para a loss
        return tokenized

    dataset = Dataset.from_dict({"text": texts})
    print("⚡ Tokenizando dataset (single-process seguro para Windows)...")
    tokenized_dataset = dataset.map(tokenize_function, batched=True, remove_columns=["text"], num_proc=None)

    # 4. Argumentos TURBO
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=1,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=2, # Batch efetivo = 8
        learning_rate=5e-5,
        logging_steps=1,
        save_strategy="no",
        optim="adamw_torch",
        fp16=False,
        use_cpu=True,                      # CRÍTICO: Força o uso da CPU
        gradient_checkpointing=False,      
        dataloader_num_workers=0,          # 🚀 CRÍTICO: 0 workers no Windows evita overhead de spawn
        dataloader_pin_memory=False,       
        remove_unused_columns=False,       # 🚀 FIX: Impede o Trainer de deletar 'labels'
        report_to="none",
    )

    print("🔥 Iniciando loop de treinamento...\n")
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
    )
    
    t_start = time.perf_counter()
    trainer.train()
    
    elapsed = time.perf_counter() - t_start
    print(f"\n✅ CONCLUÍDO em {elapsed:.1f} segundos!")
    print(f"⚡ Média de velocidade: {len(texts) / elapsed:.1f} amostras/segundo")

if __name__ == "__main__":
    main()
