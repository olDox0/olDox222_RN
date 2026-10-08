# test_lora_infer.py
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
import torch

# Aponte para o adapter que você acabou de treinar (micro ou turbo)
ADAPTER_PATH = "data/training/brunnr_lora_micro" 
MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"

print("📥 Carregando modelo base + Adapter LoRA...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
base_model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype=torch.float32, device_map="cpu")
model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
model.eval()

prompt = "<|im_start|>user\nEscreva uma função python de quicksort com comentários.<|im_end|>\n<|im_start|>assistant\n"
inputs = tokenizer(prompt, return_tensors="pt")

print("⚡ Gerando resposta...\n")
with torch.no_grad():
    # Aumentado para 256 tokens para garantir que o código feche corretamente
    out = model.generate(**inputs, max_new_tokens=256, temperature=0.2, do_sample=True, pad_token_id=tokenizer.eos_token_id)

print("="*60)
print(tokenizer.decode(out[0], skip_special_tokens=True))
print("="*60)
