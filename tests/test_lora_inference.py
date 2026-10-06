# tests/test_lora_inference.py
"""
Validação de inferência com adapter LoRA treinado.
Objetivo: Comparar respostas do modelo base vs modelo + adapter.
Typhon: onde=tests/, oque=validação de adapter, quem=test_lora_inference
quando=Fase 3, porquê=verificar se treino funcionou, origem=data/training/
consequência=se falhar, revisar dataset ou hiperparâmetros.
"""
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

def test_lora_inference():
    """Carrega modelo base + adapter e testa inferência."""
    model_id = "HuggingFaceTB/SmolLM2-135M-Instruct"
    adapter_path = Path("data/training/lora_adapter_peft")
    
    if not adapter_path.exists():
        print(f"[ERRO] Adapter não encontrado: {adapter_path}")
        return False
    
    print("="*60)
    print(" VALIDAÇÃO DE ADAPTER LORA ")
    print("="*60)
    
    # 1. Carregar Tokenizer
    print("\n[1/5] Carregando tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    print("  ✔ Tokenizer carregado")
    
    # 2. Carregar Modelo Base
    print("\n[2/5] Carregando modelo base...")
    base_model = AutoModelForCausalLM.from_pretrained(
        model_id,
        dtype=torch.float32,
        device_map="cpu"
    )
    print("  ✔ Modelo base carregado")
    
    # 3. Aplicar Adapter LoRA
    print("\n[3/5] Aplicando adapter LoRA...")
    model = PeftModel.from_pretrained(base_model, adapter_path)
    model.eval()
    print("  ✔ Adapter aplicado")
    
    # 4. Testes de Inferência
    print("\n[4/5] Executando testes de inferência...")
    
    test_prompts = [
        ("somar", "def somar(a: int, b: int) -> int:\n"),
        ("par", "def verificar_par(numero: int) -> bool:\n"),
        ("inverter", "def inverter_string(texto: str) -> str:\n"),
        ("fatorial", "def calcular_fatorial(n: int) -> int:\n"),
    ]
    
    for name, prompt in test_prompts:
        print(f"\n  ─── Teste: {name} ───")
        
        # Tokenizar
        inputs = tokenizer(prompt, return_tensors="pt")
        
        # Gerar
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=50,
                temperature=0.3,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id,
            )
        
        # Decodificar
        generated = tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        print(f"  Prompt:    {prompt.strip()}")
        print(f"  Gerado:    {generated.strip()}")
        print(f"  Completo:  {'✔' if 'return' in generated else '✘'}")
    
    # 5. Comparação com Baseline (sem adapter)
    print("\n[5/5] Comparando com baseline (sem adapter)...")
    
    base_model.eval()
    prompt_test = "def somar(a: int, b: int) -> int:\n"
    inputs = tokenizer(prompt_test, return_tensors="pt")
    
    with torch.no_grad():
        outputs_base = base_model.generate(
            **inputs,
            max_new_tokens=30,
            temperature=0.3,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    
    generated_base = tokenizer.decode(outputs_base[0], skip_special_tokens=True)
    
    print(f"\n  Baseline (sem adapter):")
    print(f"    {generated_base.strip()}")
    
    print("\n" + "="*60)
    print(" ✔ VALIDAÇÃO CONCLUÍDA ")
    print("="*60)
    
    return True

if __name__ == "__main__":
    success = test_lora_inference()
    print(f"\n{'✔ SUCESSO' if success else '✘ FALHA'}")
