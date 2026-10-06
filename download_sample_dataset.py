# download_sample_dataset.py
from datasets import load_dataset
from pathlib import Path

print("[INFO] Baixando amostra do CodeAlpaca 20K (dataset de código com instruções)...")

# Dataset confiável: HuggingFaceH4/CodeAlpaca_20K
# Contém instruções + código Python/C++/JavaScript
try:
    dataset = load_dataset("HuggingFaceH4/CodeAlpaca_20K", split="train[:500]")
    
    output_path = Path("data/training/raw_dataset.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Filtrar apenas Python
    python_samples = []
    for item in dataset:
        if "python" in item.get("language", "").lower() or "def " in item.get("output", ""):
            python_samples.append(item)
    
    # Salvar como JSONL
    import json
    with open(output_path, 'w', encoding='utf-8') as f:
        for sample in python_samples[:500]:
            entry = {
                "instruction": sample.get("instruction", ""),
                "input": sample.get("input", ""),
                "output": sample.get("output", ""),
                "language": sample.get("language", "python")
            }
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    
    print(f"[OK] Dataset salvo em: {output_path}")
    print(f"[OK] {len(python_samples)} amostras Python extraídas")
    print(f"[OK] Tamanho: {output_path.stat().st_size / 1024:.2f} KB")
    
except Exception as e:
    print(f"[ERRO] Falha ao baixar dataset: {e}")
    print("[INFO] Usando fallback: dataset sintético local")
    create_synthetic_dataset()

def create_synthetic_dataset():
    """Fallback: cria dataset sintético Python localmente."""
    import json
    from pathlib import Path
    
    output_path = Path("data/training/raw_dataset.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Dataset sintético com exemplos de qualidade
    samples = [
        {
            "instruction": "Crie uma função Python que soma dois números.",
            "input": "",
            "output": "def somar(a: int, b: int) -> int:\n    \"\"\"Retorna a soma de dois números inteiros.\"\"\"\n    return a + b",
            "language": "python"
        },
        {
            "instruction": "Implemente uma função que verifica se um número é par.",
            "input": "",
            "output": "def verificar_par(numero: int) -> bool:\n    \"\"\"Verifica se um número é par.\"\"\"\n    return numero % 2 == 0",
            "language": "python"
        },
        {
            "instruction": "Escreva uma função que inverte uma string.",
            "input": "",
            "output": "def inverter_string(texto: str) -> str:\n    \"\"\"Retorna a string invertida.\"\"\"\n    return texto[::-1]",
            "language": "python"
        },
        {
            "instruction": "Crie uma função recursiva para calcular o fatorial de um número.",
            "input": "",
            "output": "def calcular_fatorial(n: int) -> int:\n    \"\"\"Calcula o fatorial de um número inteiro não negativo.\"\"\"\n    if n == 0 or n == 1:\n        return 1\n    return n * calcular_fatorial(n - 1)",
            "language": "python"
        },
        {
            "instruction": "Implemente uma função que encontra o maior elemento em uma lista.",
            "input": "",
            "output": "def encontrar_maior(lista: list[int]) -> int:\n    \"\"\"Encontra e retorna o maior número em uma lista.\"\"\"\n    return max(lista)",
            "language": "python"
        },
        {
            "instruction": "Crie uma função que remove duplicatas de uma lista mantendo a ordem.",
            "input": "",
            "output": "def limpar_lista(lista: list) -> list:\n    \"\"\"Remove valores duplicados de uma lista mantendo a ordem.\"\"\"\n    return list(dict.fromkeys(lista))",
            "language": "python"
        },
        {
            "instruction": "Escreva uma função que converte Fahrenheit para Celsius.",
            "input": "",
            "output": "def converter_para_celsius(fahrenheit: float) -> float:\n    \"\"\"Converte temperatura de Fahrenheit para Celsius.\"\"\"\n    return (fahrenheit - 32) * 5.0 / 9.0",
            "language": "python"
        },
        {
            "instruction": "Implemente uma função que verifica se um número é primo.",
            "input": "",
            "output": "def eh_primo(n: int) -> bool:\n    \"\"\"Verifica se um número é primo.\"\"\"\n    if n <= 1:\n        return False\n    for i in range(2, int(n**0.5) + 1):\n        if n % i == 0:\n            return False\n    return True",
            "language": "python"
        },
        {
            "instruction": "Crie uma função que combina dois dicionários.",
            "input": "",
            "output": "def juntar_dicionarios(d1: dict, d2: dict) -> dict:\n    \"\"\"Combina dois dicionários em um novo.\"\"\"\n    resultado = d1.copy()\n    resultado.update(d2)\n    return resultado",
            "language": "python"
        },
        {
            "instruction": "Escreva uma função que conta palavras em uma frase.",
            "input": "",
            "output": "def contar_palavras(frase: str) -> int:\n    \"\"\"Conta o número de palavras em uma frase.\"\"\"\n    return len(frase.split())",
            "language": "python"
        }
    ]
    
    # Replicar para ter mais amostras
    extended_samples = samples * 50  # 500 amostras
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for sample in extended_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    print(f"[OK] Dataset sintético salvo em: {output_path}")
    print(f"[OK] {len(extended_samples)} amostras geradas")
    print(f"[OK] Tamanho: {output_path.stat().st_size / 1024:.2f} KB")

if __name__ == "__main__":
    create_synthetic_dataset()
