# RAIZ/engine/tools/offline_dataset_processor.py
"""
Processador de Dataset Offline para Treinamento SmolLM.
Objetivo: Ler um dataset bruto (CodeAlpaca, StarCoder, etc),
extrair código + instruções e formatar para o dataset_loader.py.
Typhon: onde=engine/tools/, oque=processamento offline, quem=offline_dataset_processor
quando=Fase 3, porquê=evitar dependência de rede e garantir dados limpos
consequência=se falhar, o dataset de treino fica vazio ou mal formatado.
"""
import json
import re
from pathlib import Path
from typing import Iterator, Dict

# Tenta importar pandas/pyarrow para ler parquet, senão fallback para jsonl
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

def extract_docstring_and_code(source_code: str) -> tuple[str, str]:
    """
    Tenta extrair a docstring e o código de um bloco Python.
    Retorna (explicacao, codigo). Se não tiver docstring, retorna ("", codigo).
    """
    match = re.search(r'(def|class)\s+\w+.*?:\s*("""[\s\S]*?""")', source_code)
    if match:
        docstring = match.group(2).strip('"""').strip()
        return docstring, source_code
    
    lines = source_code.strip().split('\n')
    if lines and lines[0].startswith('#'):
        return lines[0].strip('#').strip(), source_code
    
    return "Código Python sem documentação explícita.", source_code

def is_python_code(text: str) -> bool:
    """Detecta se o texto contém código Python relevante."""
    if not text or len(text.strip()) < 20:
        return False
    
    python_signals = [
        "def ", "class ", "import ", "from ", "return ",
        "lambda ", "if __name__", "print(", "self.",
        "@staticmethod", "@classmethod", "@property"
    ]
    
    text_lower = text.lower()
    return any(sig in text for sig in python_signals)

def process_jsonl_dataset(input_path: str | Path, output_path: str | Path, max_samples: int = 1000) -> int:
    """
    Processa um arquivo .jsonl bruto.
    Suporta múltiplos formatos:
    - CodeAlpaca: {"instruction": ..., "input": ..., "output": ...}
    - StarCoder: {"content": ...} ou {"code": ...}
    - Genérico: {"text": ...}
    """
    count = 0
    skipped = 0
    
    with open(input_path, 'r', encoding='utf-8') as fin, \
         open(output_path, 'w', encoding='utf-8') as fout:
        
        for i, line in enumerate(fin):
            if i >= max_samples * 3:  # Lê mais para compensar filtros
                break
            try:
                data = json.loads(line)
                
                # Formato CodeAlpaca (instruction + input + output)
                if 'instruction' in data and 'output' in data:
                    instruction = str(data.get('instruction', '')).strip()
                    input_ctx = str(data.get('input', '')).strip()
                    output = str(data.get('output', '')).strip()
                    
                    # Filtra apenas se o output contém código Python
                    if not is_python_code(output):
                        skipped += 1
                        continue
                    
                    # Monta o texto de treino: instrução + código
                    if input_ctx:
                        full_instruction = f"{instruction}\n\nContexto: {input_ctx}"
                    else:
                        full_instruction = instruction
                    
                    entry = {
                        "text": f"# Tarefa: {full_instruction}\n\n{output}"
                    }
                    fout.write(json.dumps(entry, ensure_ascii=False) + '\n')
                    count += 1
                
                # Formato StarCoder (content/code/text)
                else:
                    code = str(data.get('content', data.get('code', data.get('text', ''))))
                    if not code.strip():
                        skipped += 1
                        continue
                    
                    if not is_python_code(code):
                        skipped += 1
                        continue
                    
                    explanation, full_code = extract_docstring_and_code(code)
                    entry = {"text": f"# Tarefa: {explanation}\n\n{full_code}"}
                    fout.write(json.dumps(entry, ensure_ascii=False) + '\n')
                    count += 1
                
                if count >= max_samples:
                    break
                    
            except json.JSONDecodeError:
                skipped += 1
                continue
    
    print(f"[OK] Processados {count} amostras para {output_path}")
    print(f"[INFO] Puladas: {skipped} (não eram código Python válido)")
    return count

if __name__ == "__main__":
    raw_input = Path("data/training/raw_dataset.jsonl")
    final_output = Path("data/training/python_code.jsonl")
    
    if raw_input.exists():
        print(f"[INFO] Iniciando processamento offline de {raw_input.name}...")
        print(f"[INFO] Tamanho do arquivo: {raw_input.stat().st_size / 1024:.2f} KB")
        
        process_jsonl_dataset(raw_input, final_output, max_samples=500)
        
        # Validação rápida
        from engine.training.dataset_loader import prepare_dataset
        samples = prepare_dataset(final_output, max_samples=3)
        
        if samples:
            print("\n--- Amostra do Dataset Final ---")
            for i, s in enumerate(samples):
                print(f"\n[{i+1}] {s[:200]}...")
        else:
            print("\n[ERRO] Dataset final está vazio!")
    else:
        print(f"[AVISO] Arquivo bruto não encontrado em {raw_input}")
        print("[INFO] Execute primeiro: python download_sample_dataset.py")
