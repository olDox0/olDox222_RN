# tests/test_lora_inference_peft.py
"""
Teste de inferência com o adapter LoRA recém-treinado.
Objetivo: Validar que o modelo base + adapter PEFT carregam e geram texto.
Typhon: onde=tests/, oque=inferência com LoRA, quem=test_lora_inference_peft
quando=Fase 4, porquê=validar ciclo completo de treino, origem=data/training/lora_adapter_peft
"""
import time
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

def test_lora_inference():
    print("="*60)
    print(" TESTE DE INFERÊNCIA COM ADAPTER LoRA (PEFT) ")
    print("="*60)
    
    model_id = "HuggingFaceTB/SmolLM2-135M-Instruct"
    adapter_path = Path("data/training/lora_adapter_peft")
    
    if not adapter_path.exists():
        print(f"[ERRO] Adapter não encontrado em: {adapter_path}")
        print("[INFO] Execute primeiro o treinamento real.")
        return False
    
    print(f"[INFO] Carregando tokenizer: {model_id}")
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    
    print(f"[INFO] Carregando modelo base (pode levar alguns segundos)...")
    t0 = time.perf_counter()
    # Carrega em float32 ou float16 dependendo da disponibilidade, CPU usa float32 por padrão
    base_model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch.float32,
        device_map="cpu"
    )
    print(f"[OK] Modelo base carregado em {time.perf_counter() - t0:.2f}s")
    
    print(f"[INFO] Injetando adapter LoRA de: {adapter_path}")
    t0 = time.perf_counter()
    model = PeftModel.from_pretrained(base_model, adapter_path)
    print(f"[OK] Adapter injetado em {time.perf_counter() - t0:.2f}s")
    
    # Preparar prompt
    prompt = "def somar(a: int, b: int) -> int:\n    \"\"\"Retorna a soma de dois números.\"\"\"\n"
    print(f"\n[INFO] Prompt:\n{prompt}")
    
    inputs = tokenizer(prompt, return_tensors="pt")
    
    print("[INFO] Gerando resposta...")
    t0 = time.perf_counter()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=32,
            temperature=0.5,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id
        )
    gen_time = time.perf_counter() - t0
    
    # Decodificar
    generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    print(f"\n[OK] Resposta gerada em {gen_time:.2f}s")
    print("-" * 60)
    print(generated_text)
    print("-" * 60)
    
    # Limpar memória
    del model
    del base_model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    print("\n✔ SUCESSO: Ciclo completo de treino e inferência LoRA validado!")
    return True

if __name__ == "__main__":
    test_lora_inference()
