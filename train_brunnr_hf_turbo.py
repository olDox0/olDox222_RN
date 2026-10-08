# train_brunnr_hf_turbo.py
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer, DataCollatorForLanguageModeling
from peft import LoraConfig, get_peft_model, TaskType
from datasets import Dataset

MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
DATA_FILE = "data/training/brunnr_native_train.txt"
OUTPUT_DIR = "data/training/brunnr_lora_turbo"
MAX_SAMPLES = 200  # ⚡ TESTE DE VIABILIDADE: Reduzido para 200 amostras

def main():
    print(f"🚀 Iniciando treinamento LoRA TURBO (Modo Teste: {MAX_SAMPLES} Amostras)")
    
    # 1. Carregar em float32 (Máxima estabilidade em CPU)
    print("📥 Carregando modelo e tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float32,
        device_map="cpu"
    )

    # 2. LoRA leve (apenas Q e V para máxima eficiência)
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
        texts = [line.strip() for line in f if line.strip()]

    # Fatiar para MAX_SAMPLES
    texts = texts[:MAX_SAMPLES]
    print(f"⚡ Usando apenas {len(texts)} amostras para o teste de viabilidade.")

    def tokenize_function(examples):
        return tokenizer(
            examples["text"],
            truncation=True,
            max_length=256,
            padding="max_length",
        )

    dataset = Dataset.from_dict({"text": texts})
    print("⚡ Tokenizando dataset...")
    tokenized_dataset = dataset.map(tokenize_function, batched=True, remove_columns=["text"], num_proc=1)

    # 4. Argumentos TURBO para CPU (Teste Rápido)
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=3,                # Aumentado para 3 épocas para compensar o dataset minúsculo
        per_device_train_batch_size=16,    # 200 amostras / 16 = ~13 steps por época
        gradient_accumulation_steps=1,     
        learning_rate=5e-5,
        logging_steps=2,                   # Log mais frequente para acompanhar a loss cair
        save_strategy="epoch",
        optim="adamw_torch",
        bf16=False,                        
        fp16=False,
        use_cpu=True,                      
        gradient_checkpointing=False,      
        dataloader_num_workers=0,          
        dataloader_pin_memory=False,       
        report_to="none",
    )

    print("🔥 Iniciando loop de treinamento (~15 minutos)...")
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )

    trainer.train()

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"✅ Concluído! Adapter LoRA salvo em: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
