# RAIZ/engine/training/lora_trainer.py
"""
Orquestrador de treinamento LoRA para SmolLM 135M (Otimizado e Corrigido).
Objetivo: Treinamento real com Batch Processing, Gradient Accumulation e Labels corretos.
Typhon: onde=engine/training/, oque=treinamento LoRA, quem=lora_trainer
quando=Fase 5, porquê=reduzir tempo de treino e calcular loss corretamente
consequência=se falhar, revisar dependências do transformers/peft.
"""
import gc
import time
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer
from peft import LoraConfig, get_peft_model, TaskType
from datasets import Dataset

from engine.training.dataset_loader import prepare_dataset
from engine.training.telemetry import log_step, save_metrics

def train_lora_optimized(
    model_id: str = "HuggingFaceTB/SmolLM2-135M-Instruct",
    dataset_path: str | Path = "data/training/brunnr_full.jsonl",
    output_dir: str | Path = "data/training/lora_adapter_peft_v2",
    epochs: int = 2,
    lr: float = 1e-4,
    rank: int = 8,
    batch_size: int = 4,
    grad_accumulation: int = 4,
    max_samples: int = 500,
) -> bool:
    """
    Treinamento LoRA otimizado com Batch e Gradient Accumulation.
    """
    log_step("INICIO", f"Treinamento LoRA Otimizado | Rank={rank}, LR={lr}, Epochs={epochs}")
    
    dataset_path = Path(dataset_path)
    output_dir = Path(output_dir)
    
    if not dataset_path.exists():
        log_step("ERRO", f"Dataset não encontrado: {dataset_path}")
        return False

    # 1. Carregar Tokenizer e Modelo
    log_step("INFO", "Carregando Tokenizer e Modelo Base...")
    t0 = time.perf_counter()
    
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    # Garante que o tokenizer tenha um pad_token para o batching funcionar
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch.float32, # float32 é mais estável em CPU pura
        device_map="cpu",
    )
    log_step("OK", f"Modelo carregado em {time.perf_counter() - t0:.2f}s")

    # 2. Configurar LoRA
    log_step("INFO", f"Aplicando configuração LoRA (rank={rank}, target_modules=['q_proj', 'v_proj'])...")
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=rank,
        lora_alpha=2 * rank, # Regra geral: alpha = 2 * rank
        lora_dropout=0.1,
        target_modules=["q_proj", "v_proj"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 3. Preparar Dataset
    log_step("INFO", "Processando dataset...")
    texts = prepare_dataset(dataset_path, max_samples=max_samples)
    
    # CORREÇÃO CRÍTICA: Adicionar a coluna 'labels'
    def tokenize_function(examples):
        tokenized = tokenizer(
            examples["text"], 
            truncation=True, 
            max_length=512, 
            padding="max_length" # Garante batches de tamanho fixo, melhor para CPU
        )
        # Para Causal LM, os labels são os próprios input_ids. 
        # O modelo internamente faz o shift para calcular a loss.
        tokenized["labels"] = tokenized["input_ids"].copy()
        return tokenized

    dataset = Dataset.from_dict({"text": texts})
    
    # batched=True acelera a tokenização
    tokenized_dataset = dataset.map(tokenize_function, batched=True, remove_columns=["text"])
    log_step("OK", f"Dataset tokenizado com labels: {len(tokenized_dataset)} amostras")

    # 4. Configurar Treinamento (Hugging Face Trainer)
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_accumulation,
        learning_rate=lr,
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=1,
        optim="adamw_torch",
        fp16=False, 
        remove_unused_columns=False, # CRUCIAL: impede o Trainer de descartar a coluna 'labels'
        dataloader_pin_memory=False, # Remove o warning de CPU
        report_to="none", # Desativa wandb/etc para focar no console
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
    )

    # 5. Executar Treinamento
    log_step("INICIO", "Iniciando loop de treinamento...")
    t0 = time.perf_counter()
    
    try:
        trainer.train()
        elapsed = time.perf_counter() - t0
        log_step("SUCESSO", f"Treinamento concluído em {elapsed/60:.2f} minutos")
        
        # Salvar adapter
        model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)
        log_step("OK", f"Adapter salvo em: {output_dir}")
        
        save_metrics({"status": "success", "elapsed_min": elapsed/60, "samples": len(tokenized_dataset)})
        return True
        
    except Exception as e:
        log_step("ERRO", f"Falha no treinamento: {e}")
        save_metrics({"status": "error", "reason": str(e)})
        return False
    finally:
        # Limpar memória
        del model, trainer, tokenized_dataset
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

if __name__ == "__main__":
    # Executar treino com o dataset bilíngue consolidado
    success = train_lora_optimized(
        dataset_path="data/training/brunnr_full.jsonl",
        output_dir="data/training/lora_adapter_peft_v2",
        epochs=2,
        lr=1e-4,
        rank=8,
        batch_size=4,
        grad_accumulation=4,
        max_samples=500, # Mantido em 500 para um ciclo de validação rápido (~10-15 min no i5)
    )
    print(f"\n{'✔ SUCESSO' if success else '✘ FALHA'}")
