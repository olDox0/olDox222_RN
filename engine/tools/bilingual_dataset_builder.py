# engine/tools/bilingual_dataset_builder.py
"""
Gerador de Dataset Bilíngue PT/EN para Brunnr.
Objetivo: Criar dataset com instruções em PT e EN para treinar SmolLM.
Typhon: onde=engine/tools/, oque=gerador de dataset bilíngue, quem=bilingual_dataset_builder
quando=Fase 5.1, porquê=treinar Brunnr como assistente bilíngue
consequência=se falhar, dataset fica monolíngue (fallback para PT apenas)
"""
import json
from pathlib import Path
from typing import Iterator

def generate_bilingual_samples() -> Iterator[dict]:
    """Gera amostras bilíngues de código Python com docstrings PT/EN."""
    
    # Dataset base: funções Python com instruções PT e EN
    samples = [
        {
            "instruction_pt": "Crie uma função Python que soma dois números.",
            "instruction_en": "Create a Python function that adds two numbers.",
            "code": 'def somar(a: int, b: int) -> int:\n    """Retorna a soma de dois números inteiros."""\n    return a + b'
        },
        {
            "instruction_pt": "Implemente uma função que verifica se um número é par.",
            "instruction_en": "Implement a function that checks if a number is even.",
            "code": 'def verificar_par(numero: int) -> bool:\n    """Verifica se um número é par."""\n    return numero % 2 == 0'
        },
        {
            "instruction_pt": "Escreva uma função que inverte uma string.",
            "instruction_en": "Write a function that reverses a string.",
            "code": 'def inverter_string(texto: str) -> str:\n    """Retorna a string invertida."""\n    return texto[::-1]'
        },
        {
            "instruction_pt": "Crie uma função recursiva para calcular o fatorial de um número.",
            "instruction_en": "Create a recursive function to calculate the factorial of a number.",
            "code": 'def calcular_fatorial(n: int) -> int:\n    """Calcula o fatorial de um número inteiro não negativo."""\n    if n == 0 or n == 1:\n        return 1\n    return n * calcular_fatorial(n - 1)'
        },
        {
            "instruction_pt": "Implemente uma função que encontra o maior elemento em uma lista.",
            "instruction_en": "Implement a function that finds the largest element in a list.",
            "code": 'def encontrar_maior(lista: list[int]) -> int:\n    """Encontra e retorna o maior número em uma lista."""\n    return max(lista)'
        },
        {
            "instruction_pt": "Crie uma função que remove duplicatas de uma lista mantendo a ordem.",
            "instruction_en": "Create a function that removes duplicates from a list while maintaining order.",
            "code": 'def limpar_lista(lista: list) -> list:\n    """Remove valores duplicados de uma lista mantendo a ordem."""\n    return list(dict.fromkeys(lista))'
        },
        {
            "instruction_pt": "Escreva uma função que converte Fahrenheit para Celsius.",
            "instruction_en": "Write a function that converts Fahrenheit to Celsius.",
            "code": 'def converter_para_celsius(fahrenheit: float) -> float:\n    """Converte temperatura de Fahrenheit para Celsius."""\n    return (fahrenheit - 32) * 5.0 / 9.0'
        },
        {
            "instruction_pt": "Implemente uma função que verifica se um número é primo.",
            "instruction_en": "Implement a function that checks if a number is prime.",
            "code": 'def eh_primo(n: int) -> bool:\n    """Verifica se um número é primo."""\n    if n <= 1:\n        return False\n    for i in range(2, int(n**0.5) + 1):\n        if n % i == 0:\n            return False\n    return True'
        },
        {
            "instruction_pt": "Crie uma função que combina dois dicionários.",
            "instruction_en": "Create a function that merges two dictionaries.",
            "code": 'def juntar_dicionarios(d1: dict, d2: dict) -> dict:\n    """Combina dois dicionários em um novo."""\n    resultado = d1.copy()\n    resultado.update(d2)\n    return resultado'
        },
        {
            "instruction_pt": "Escreva uma função que conta palavras em uma frase.",
            "instruction_en": "Write a function that counts words in a sentence.",
            "code": 'def contar_palavras(frase: str) -> int:\n    """Conta o número de palavras em uma frase."""\n    return len(frase.split())'
        },
        {
            "instruction_pt": "Implemente uma função que calcula a média de uma lista de números.",
            "instruction_en": "Implement a function that calculates the average of a list of numbers.",
            "code": 'def calcular_media(numeros: list[float]) -> float:\n    """Calcula a média aritmética de uma lista de números."""\n    return sum(numeros) / len(numeros) if numeros else 0.0'
        },
        {
            "instruction_pt": "Crie uma função que verifica se uma string é um palíndromo.",
            "instruction_en": "Create a function that checks if a string is a palindrome.",
            "code": 'def eh_palindromo(texto: str) -> bool:\n    """Verifica se uma string é um palíndromo."""\n    texto_limpo = texto.lower().replace(" ", "")\n    return texto_limpo == texto_limpo[::-1]'
        },
        {
            "instruction_pt": "Escreva uma função que encontra o segundo maior elemento em uma lista.",
            "instruction_en": "Write a function that finds the second largest element in a list.",
            "code": 'def segundo_maior(lista: list[int]) -> int | None:\n    """Encontra o segundo maior elemento em uma lista."""\n    if len(lista) < 2:\n        return None\n    lista_ordenada = sorted(set(lista), reverse=True)\n    return lista_ordenada[1] if len(lista_ordenada) >= 2 else None'
        },
        {
            "instruction_pt": "Implemente uma função que gera a sequência de Fibonacci até n termos.",
            "instruction_en": "Implement a function that generates the Fibonacci sequence up to n terms.",
            "code": 'def fibonacci(n: int) -> list[int]:\n    """Gera a sequência de Fibonacci com n termos."""\n    if n <= 0:\n        return []\n    if n == 1:\n        return [0]\n    sequencia = [0, 1]\n    for _ in range(2, n):\n        sequencia.append(sequencia[-1] + sequencia[-2])\n    return sequencia'
        },
        {
            "instruction_pt": "Crie uma função que calcula o MDC (Máximo Divisor Comum) de dois números.",
            "instruction_en": "Create a function that calculates the GCD (Greatest Common Divisor) of two numbers.",
            "code": 'def mdc(a: int, b: int) -> int:\n    """Calcula o MDC usando o algoritmo de Euclides."""\n    while b:\n        a, b = b, a % b\n    return a'
        },
    ]
    
    # Replicar para ter mais amostras (15 * 34 = 510 amostras)
    for _ in range(34):
        for sample in samples:
            yield sample

def build_bilingual_dataset(output_path: str | Path, max_samples: int = 500) -> int:
    """Constrói dataset bilíngue em formato JSONL.
    
    Formato:
    {"text": "# Tarefa PT: <instrução_pt>\n# Task EN: <instruction_en>\n\n<code>"}
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    count = 0
    with open(output_path, 'w', encoding='utf-8') as f:
        for sample in generate_bilingual_samples():
            if count >= max_samples:
                break
            
            # Formato bilíngue: instrução PT + EN + código
            text = (
                f"# Tarefa PT: {sample['instruction_pt']}\n"
                f"# Task EN: {sample['instruction_en']}\n\n"
                f"{sample['code']}"
            )
            
            entry = {"text": text}
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            count += 1
    
    print(f"[OK] Dataset bilíngue salvo em: {output_path}")
    print(f"[OK] {count} amostras geradas")
    print(f"[OK] Tamanho: {output_path.stat().st_size / 1024:.2f} KB")
    return count

if __name__ == "__main__":
    output = Path("data/training/bilingual_dataset.jsonl")
    build_bilingual_dataset(output, max_samples=500)
