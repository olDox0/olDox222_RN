# -*- coding: utf-8 -*-
"""
Prepara os dados do brunnr_full.jsonl para o stream de treino nativo em C.
"""
import json
from pathlib import Path

SRC = Path("data/training/brunnr_full.jsonl")
OUT = Path("data/training/brunnr_native_train.txt")

def convert():
    if not SRC.exists():
        print(f"❌ {SRC} não encontrado.")
        return
    
    count = 0
    with open(SRC, "r", encoding="utf-8") as f_in, open(OUT, "w", encoding="utf-8") as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            text = data.get("text", "").strip()
            if text:
                # Cada exemplo é delimitado para o tokenizer do llama.cpp
                f_out.write(text + "\n")
                count += 1
                
    print(f"✔ {count} exemplos convertidos para: {OUT}")
    print(f"Tamanho do arquivo de texto: {OUT.stat().st_size / 1024:.2f} KB")

if __name__ == "__main__":
    convert()
