# RAIZ/engine/tools/brunnr_dataset_builder.py
"""
Construtor de Dataset Bilíngue para Brunnr.
Objetivo: Gerar dataset PT/EN estruturado para fine-tuning.
"""
import json
from pathlib import Path

def merge_datasets(sources: list[Path], output: Path) -> int:
    """Merge múltiplos JSONL em um único dataset Brunnr."""
    count = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output, 'w', encoding='utf-8') as fout:
        for src in sources:
            if not src.exists():
                print(f"[AVISO] Fonte não encontrada: {src}")
                continue
            
            with open(src, 'r', encoding='utf-8') as fin:
                for line in fin:
                    line = line.strip()
                    if line:
                        # Validação básica de JSON
                        try:
                            json.loads(line)
                            fout.write(line + '\n')
                            count += 1
                        except json.JSONDecodeError:
                            continue
            
            print(f"[OK] {src.name}: processado")
    
    print(f"\n[OK] Dataset final: {output} ({count} amostras)")
    return count

if __name__ == "__main__":
    sources = [
        Path("data/training/python_code.jsonl"),      # Processado do CodeAlpaca
        Path("data/training/tech_bilingual_dataset.jsonl"), # Dataset técnico PT/EN
    ]
    output = Path("data/training/brunnr_full.jsonl")
    
    print("[INFO] Iniciando merge de datasets para Brunnr...")
    merge_datasets(sources, output)
