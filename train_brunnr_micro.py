# train_brunnr_real.py
import torch, time
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer
from peft import LoraConfig, get_peft_model, TaskType
from datasets import Dataset

MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
DATA_FILE = "data/training/brunnr_full.jsonl" # Seu dataset consolidado
OUTPUT_DIR = "data/training/brunnr_lora_real_v1"
MAX_SAMPLES = 1000  # Escalado para validar o aprendizado real

def main():
    print(f"🚀 TREINO REAL BRUNNR: {MAX_SAMPLES} amostras, 2 épocas, Rank 8 (Filosofia: Rápido e Eficiente)")
    t_start = time.perf_counter()
    
    # 1. Carregamento leve
    print("📥 Carregando modelo e tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token is None: tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, dtype=torch.float32, device_map="cpu"
    )

    # 2. LoRA Leve (Rank 8 é o sweet spot: capacidade dobrada, ainda minúsculo)
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 3. Dataset
    print(f"📂 Lendo dataset: {DATA_FILE}")
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        texts = [line.strip() for line in f if line.strip()][:MAX_SAMPLES]

    def tokenize_function(examples):
        tokenized = tokenizer(
            examples["text"], truncation=True, max_length=256, padding="max_length"
        )
        tokenized["labels"] = tokenized["input_ids"].copy() # Obrigatório para a loss
        return tokenized

    dataset = Dataset.from_dict({"text": texts})
    print("⚡ Tokenizando...")
    tokenized_dataset = dataset.map(tokenize_function, batched=True, remove_columns=["text"], num_proc=1)

    # 4. Argumentos TURBO (Mantendo a velocidade <1s/amostra)
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=2,                # 2 épocas para consolidar o padrão
        per_device_train_batch_size=8,     # 8 amostras por vez (AVX2 feliz)
        gradient_accumulation_steps=1,     
        learning_rate=5e-5,
        logging_steps=10,
        save_strategy="epoch",
        optim="adamw_torch",
        fp16=False,
        dataloader_num_workers=0,          # Estabilidade no Windows
        dataloader_pin_memory=False,
        report_to="none",
    )

    print("🔥 Iniciando loop de treinamento real...")
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
    )
    
    trainer.train()
    
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    
    elapsed = time.perf_counter() - t_start
    print(f"✅ CONCLUÍDO em {elapsed/60:.1f} minutos!")
    print(f"⚡ Média de velocidade: {(len(texts)*2) / elapsed:.1f} amostras/segundo")
    print(f"💾 Adapter salvo em: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
