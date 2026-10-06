# tests/test_lora_inference_peft_v2.py
"""
Teste de inferência com o adapter LoRA recém-treinado (v2).
Objetivo: Validar se o SmolLM 135M + LoRA responde melhor em PT-BR com código.
Typhon: onde=tests/, oque=inferência com LoRA v2, quem=test_lora_inference_peft_v2
quando=Pós-treino, porquê=validar aprendizado do dataset bilíngue
"""
import time
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

def test_lora_inference_v2():
    print("=" * 70)
    print(" 🌊 TESTE DE INFERÊNCIA COM ADAPTER LoRA v2 (BRUNNR) ")
    print("=" * 70)
    
    model_id = "HuggingFaceTB/SmolLM2-135M-Instruct"
    adapter_path = Path("data/training/lora_adapter_peft_v2")
    
    if not adapter_path.exists():
        print(f"[ERRO] Adapter não encontrado em: {adapter_path}")
        return False
    
    print(f"[INFO] 1/4 Carregando tokenizer: {model_id}")
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    print(f"[INFO] 2/4 Carregando modelo base (pode levar alguns segundos)...")
    t0 = time.perf_counter()
    base_model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch.float32,
        device_map="cpu",
    )
    print(f"[OK] Modelo base carregado em {time.perf_counter() - t0:.2f}s")
    
    print(f"[INFO] 3/4 Injetando adapter LoRA treinado: {adapter_path.name}")
    t0 = time.perf_counter()
    model = PeftModel.from_pretrained(base_model, adapter_path)
    print(f"[OK] Adapter injetado em {time.perf_counter() - t0:.2f}s")
    
    # Prompt de teste alinhado com o dataset de treino
    prompt = (
        "# Tarefa: Crie uma função Python que calcula o fatorial de um número.\n"
        "# Task: Create a Python function that calculates the factorial of a number.\n\n"
    )
    print(f"\n[INFO] 4/4 Prompt de teste:\n{prompt.strip()}")
    
    inputs = tokenizer(prompt, return_tensors="pt")
    
    print("\n[INFO] Gerando resposta...")
    t0 = time.perf_counter()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=128,
            temperature=0.3,      # Mais determinístico para código
            top_p=0.85,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    gen_time = time.perf_counter() - t0
    
    # Decodificar e limpar o output
    generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    # Extrair apenas a parte gerada (pós-prompt)
    response = generated_text[len(prompt):].strip()
    
    print("\n" + "=" * 70)
    print(" 🌊 RESPOSTA DO BRUNNR:")
    print("=" * 70)
    print(response)
    print("=" * 70)
    print(f"[OK] Tempo de geração: {gen_time:.2f}s")
    
    # Limpar memória
    del model
    del base_model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    print("\n✔ SUCESSO: Ciclo completo de treino e inferência LoRA v2 validado!")
    return True

if __name__ == "__main__":
    test_lora_inference_v2()
