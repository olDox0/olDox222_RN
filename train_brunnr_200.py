# train_brunnr_200.py
import torch, time, gc
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer
from peft import LoraConfig, get_peft_model, TaskType
from datasets import Dataset

MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
DATA_FILE = "data/training/brunnr_native_train.txt"
OUTPUT_DIR = "data/training/brunnr_lora_200"
MAX_SAMPLES = 200  # ⚡ Meta de iteração rápida

def main():
    print(f"⚡ TREINO RÁPIDO BRUNNR: {MAX_SAMPLES} amostras, 2 épocas, Rank 8")
    t_start = time.perf_counter()
    
    # 1. Carregar em float32 (Máxima estabilidade em CPU)
    print("📥 Carregando modelo e tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        dtype=torch.float32,  # Estável em CPU, evita bugs de validação
        device_map="cpu"
    )

    # 2. LoRA Leve (Rank 8 é o sweet spot para aprendizado de sintaxe)
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 3. Dataset Limitado a 200 amostras
    print(f"📂 Lendo dataset e limitando a {MAX_SAMPLES} amostras...")
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        texts = [line.strip() for line in f if line.strip()][:MAX_SAMPLES]

    def tokenize_function(examples):
        tokenized = tokenizer(
            examples["text"],
            truncation=True,
            max_length=256,  # Otimizado para velocidade
            padding="max_length",
        )
        tokenized["labels"] = tokenized["input_ids"].copy() # Obrigatório para a loss
        return tokenized

    dataset = Dataset.from_dict({"text": texts})
    print("⚡ Tokenizando (single-process para estabilidade no Windows)...")
    tokenized_dataset = dataset.map(tokenize_function, batched=True, remove_columns=["text"], num_proc=1)

    # 4. Argumentos TURBO para CPU
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=2,                # 2 épocas para consolidar o padrão
        per_device_train_batch_size=8,     # Batch maior para reduzir overhead
        gradient_accumulation_steps=1,     
        learning_rate=5e-5,
        logging_steps=5,                   # Feedback a cada 5 steps
        save_strategy="epoch",
        optim="adamw_torch",
        fp16=False,
        use_cpu=True,                      # CRÍTICO: Força o uso da CPU
        gradient_checkpointing=False,      # Desativado para evitar overhead em CPU pura
        dataloader_num_workers=0,          # 0 é o mais estável no Windows
        dataloader_pin_memory=False,       
        report_to="none",
    )

    print("🔥 Iniciando loop de treinamento...")
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
    )
    
    trainer.train()
    
    # 5. Salvar
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    
    elapsed = time.perf_counter() - t_start
    print(f"\n✅ CONCLUÍDO em {elapsed:.1f} segundos!")
    print(f"⚡ Média de velocidade: {(len(texts)*2) / elapsed:.1f} amostras/segundo")
    print(f"💾 Adapter salvo em: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
