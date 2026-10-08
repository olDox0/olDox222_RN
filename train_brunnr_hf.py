# train_brunnr_hf.py
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer, DataCollatorForLanguageModeling
from peft import LoraConfig, get_peft_model, TaskType
from datasets import Dataset

# 1. Configuração
MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
DATA_FILE = "data/training/brunnr_native_train.txt"
OUTPUT_DIR = "data/training/brunnr_lora_hf"

print("🚀 Iniciando treinamento LoRA com Hugging Face (Estável e sem bugs de asserção)")

# 2. Carregar Tokenizer e Modelo (FP32 para máxima estabilidade em CPU)
print("📥 Carregando modelo e tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float32,
    device_map="cpu"
)

# 3. Configurar LoRA (focado apenas em q_proj e v_proj para ser leve e estável)
lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=8,
    lora_alpha=16,
    lora_dropout=0.05,
    target_modules=["q_proj", "v_proj"],
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# 4. Preparar Dataset
print(f"📂 Lendo dataset de: {DATA_FILE}")
with open(DATA_FILE, "r", encoding="utf-8") as f:
    texts = [line.strip() for line in f if line.strip()]

def tokenize_function(examples):
    return tokenizer(
        examples["text"],
        truncation=True,
        max_length=512,
        padding="max_length",
    )

dataset = Dataset.from_dict({"text": texts})
tokenized_dataset = dataset.map(tokenize_function, batched=True, remove_columns=["text"])

# 5. Argumentos de Treinamento Otimizados para CPU
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    num_train_epochs=1,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4, # Simula batch size de 16
    learning_rate=5e-5,
    logging_steps=10,
    save_strategy="epoch",
    optim="adamw_torch",
    fp16=False, # Desativado para evitar instabilidade em CPU pura
    report_to="none",
    dataloader_num_workers=0, # Mais estável no Windows
)

# 6. Executar Trainer
print("🔥 Iniciando loop de treinamento...")
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_dataset,
    data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
)

trainer.train()

# 7. Salvar Adapter
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print(f"✅ Adapter LoRA salvo com sucesso em: {OUTPUT_DIR}")
