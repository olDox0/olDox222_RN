# test_brunnr_200.py
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
import torch

MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
# Apontando para o adapter que acabou de ser treinado
ADAPTER_PATH = "data/training/brunnr_lora_200"

print("📥 Carregando modelo base + Adapter LoRA (200 amostras)...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# Usando float32 para combinar com o treinamento
base_model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID, 
    dtype=torch.float32, 
    device_map="cpu"
)
model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
model.eval()

# Prompt de teste alinhado com o estilo de código
prompt = "<|im_start|>user\nEscreva uma função em Python para calcular o fatorial de um número, com comentários.\n<|im_end|>\n<|im_start|>assistant\n"

print("⚡ Gerando resposta...\n")
inputs = tokenizer(prompt, return_tensors="pt")

with torch.no_grad():
    out = model.generate(
        **inputs, 
        max_new_tokens=256, 
        temperature=0.2,      # Baixa temperatura para foco e determinismo
        do_sample=True, 
        pad_token_id=tokenizer.eos_token_id,
        repetition_penalty=1.1 # Ajuda a evitar loops de repetição
    )

print("=" * 70)
print(tokenizer.decode(out[0], skip_special_tokens=False))
print("=" * 70)
