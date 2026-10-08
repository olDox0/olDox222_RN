# test_infer.py
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
ADAPTER_PATH = "data/training/lora_adapter_peft_v3"

print("Carregando modelo base + adaptador LoRA v3...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
base_model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=torch.float32, device_map="cpu")
model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
model.eval()

prompt = "<|im_start|>user\nEscreva uma função em Python para ordenar uma lista usando quicksort.<|im_end|>\n<|im_start|>assistant\n"
inputs = tokenizer(prompt, return_tensors="pt")

with torch.no_grad():
    out = model.generate(**inputs, max_new_tokens=256, temperature=0.2, do_sample=True)

print(tokenizer.decode(out[0], skip_special_tokens=False))
