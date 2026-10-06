# tests/test_translation_brunnr.py
"""
Teste de Tradução do Brunnr (Baseline)
Objetivo: Avaliar se o modelo com adapter LoRA consegue traduzir 
conceitos de programação entre PT e EN.
"""
import time
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

def test_translation():
    print("="*60)
    print(" TESTE DE TRADUÇÃO — BRUNNR v0.1 ")
    print("="*60)
    
    model_id = "HuggingFaceTB/SmolLM2-135M-Instruct"
    adapter_path = Path("data/training/brunnr_lora_adapter") # Ou lora_adapter_peft
    
    print("[INFO] Carregando Tokenizer e Modelo Base + LoRA...")
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    
    base_model = AutoModelForCausalLM.from_pretrained(
        model_id,
        dtype=torch.float32,
        device_map="cpu"
    )
    model = PeftModel.from_pretrained(base_model, adapter_path)
    print("[OK] Modelo carregado com sucesso.\n")
    
    # Teste 1: PT -> EN (Traduzir explicação)
    prompt_pt = "Traduza para inglês: 'Esta função calcula o fatorial de um número usando recursão.'"
    
    # Teste 2: EN -> PT (Traduzir docstring)
    prompt_en = "Translate to Portuguese: 'This function sorts a list of integers using the quicksort algorithm.'"
    
    tests = [
        ("PT -> EN", prompt_pt),
        ("EN -> PT", prompt_en)
    ]
    
    for label, prompt in tests:
        print(f"[{label}] Prompt: {prompt}")
        
        # Formato de chat do SmolLM
        chat_prompt = (
            "<|im_start|>system\nYou are Brunnr, a bilingual programming assistant. "
            "Translate the following text accurately, maintaining technical terms.\n<|im_end|>\n"
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        
        inputs = tokenizer(chat_prompt, return_tensors="pt")
        
        t0 = time.perf_counter()
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=64,
                temperature=0.3, # Baixa temperatura para tradução mais determinística
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id
            )
        elapsed = time.perf_counter() - t0
        
        full_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Extrair apenas a resposta do assistente
        response = full_text.split("<|im_start|>assistant\n")[-1].strip()
        
        print(f"[OK] Resposta ({elapsed:.2f}s):\n{response}\n")
        print("-" * 60)

if __name__ == "__main__":
    test_translation()
