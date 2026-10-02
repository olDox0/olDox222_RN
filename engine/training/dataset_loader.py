# RAIZ/engine/training/dataset_loader.py
"""
Carregamento e preparação de datasets JSONL para treinamento LoRA.
Objetivo: Ler dados, validar schema e preparar para o loop de treino.
Typhon: onde=engine/training/, oque=carregamento de dados, quem=dataset_loader
quando=Fase 2, porquê=alimentar o pipeline LoRA, origem=data/training/
consequência=se falhar, o treinamento não inicia.
"""
import json
from pathlib import Path
from typing import Iterator, List, Dict

def load_jsonl(path: str | Path) -> Iterator[Dict[str, str]]:
    """Yield dicionários de um arquivo JSONL linha por linha."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset não encontrado: {path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[ERRO] Falha ao parsear linha {line_num}: {e}")

def prepare_dataset(dataset_path: str | Path, max_samples: int = 1000) -> List[str]:
    """
    Extrai e prepara textos do dataset para o loop de treino.
    Valida se a chave 'text' existe em cada entrada.
    """
    texts = []
    for i, item in enumerate(load_jsonl(dataset_path)):
        if i >= max_samples:
            break
        
        # Assume schema: {"text": "..."}
        text = item.get("text", "").strip()
        if text:
            texts.append(text)
            
    print(f"[OK] Dataset carregado: {len(texts)} amostras válidas de {Path(dataset_path).name}")
    return texts

if __name__ == "__main__":
    # Teste rápido do loader
    test_path = Path("data/training/python_code.jsonl")
    if test_path.exists():
        samples = prepare_dataset(test_path, max_samples=5)
        print("\n--- Amostra de Dados ---")
        for i, s in enumerate(samples):
            print(f"[{i+1}] {s[:60]}...")
    else:
        print(f"[ERRO] Arquivo de teste não encontrado em {test_path}")
