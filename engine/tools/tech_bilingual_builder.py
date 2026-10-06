# engine/tools/tech_bilingual_builder.py
"""
Gerador de Dataset Técnico Bilíngue PT-EN para Brunnr.
Foco: termos de programação, explicações técnicas, docstrings.
"""
import json
from pathlib import Path

TECH_GLOSSARY = {
    "quicksort": ("quicksort", "ordenação rápida"),
    "recursion": ("recursão", "recursion"),
    "buffer": ("buffer", "buffer"),
    "stack": ("pilha", "stack"),
    "queue": ("fila", "queue"),
    "array": ("array", "vetor"),
    "loop": ("loop", "laço"),
    "function": ("função", "function"),
    "variable": ("variável", "variable"),
    "class": ("classe", "class"),
    "object": ("objeto", "object"),
    "method": ("método", "method"),
    "parameter": ("parâmetro", "parameter"),
    "return": ("retornar", "return"),
    "import": ("importar", "import"),
    "debug": ("depurar", "debug"),
    "compile": ("compilar", "compile"),
    "execute": ("executar", "execute"),
}

BILINGUAL_PAIRS = [
    {
        "pt": "Esta função calcula o fatorial de um número usando recursão.",
        "en": "This function calculates the factorial of a number using recursion.",
        "code": "def fatorial(n: int) -> int:\n    if n <= 1: return 1\n    return n * fatorial(n - 1)"
    },
    {
        "pt": "Esta função ordena uma lista de inteiros usando o algoritmo quicksort.",
        "en": "This function sorts a list of integers using the quicksort algorithm.",
        "code": "def quicksort(arr: list[int]) -> list[int]:\n    if len(arr) <= 1: return arr\n    pivot = arr[len(arr) // 2]\n    left = [x for x in arr if x < pivot]\n    middle = [x for x in arr if x == pivot]\n    right = [x for x in arr if x > pivot]\n    return quicksort(left) + middle + quicksort(right)"
    },
    {
        "pt": "Um buffer circular é uma estrutura de dados que usa um único array de tamanho fixo.",
        "en": "A circular buffer is a data structure that uses a single, fixed-size array.",
        "code": "class CircularBuffer:\n    def __init__(self, size: int):\n        self.buffer = [None] * size\n        self.head = 0\n        self.tail = 0"
    },
    {
        "pt": "Recursão é quando uma função chama a si mesma para resolver subproblemas menores.",
        "en": "Recursion is when a function calls itself to solve smaller subproblems.",
        "code": "# Exemplo: Fibonacci recursivo\ndef fibonacci(n: int) -> int:\n    if n <= 1: return n\n    return fibonacci(n-1) + fibonacci(n-2)"
    },
    {
        "pt": "Uma pilha segue o princípio LIFO: Last In, First Out.",
        "en": "A stack follows the LIFO principle: Last In, First Out.",
        "code": "class Stack:\n    def __init__(self):\n        self.items = []\n    def push(self, item):\n        self.items.append(item)\n    def pop(self):\n        return self.items.pop()"
    },
    {
        "pt": "Uma fila segue o princípio FIFO: First In, First Out.",
        "en": "A queue follows the FIFO principle: First In, First Out.",
        "code": "from collections import deque\nclass Queue:\n    def __init__(self):\n        self.items = deque()\n    def enqueue(self, item):\n        self.items.append(item)\n    def dequeue(self):\n        return self.items.popleft()"
    },
    {
        "pt": "Complexidade de tempo O(n log n) é típica de algoritmos de ordenação eficientes.",
        "en": "Time complexity O(n log n) is typical of efficient sorting algorithms.",
        "code": "# MergeSort: O(n log n)\ndef merge_sort(arr: list[int]) -> list[int]:\n    if len(arr) <= 1: return arr\n    mid = len(arr) // 2\n    left = merge_sort(arr[:mid])\n    right = merge_sort(arr[mid:])\n    return merge(left, right)"
    },
    {
        "pt": "Um dicionário hash map armazena pares chave-valor com acesso O(1).",
        "en": "A hash map dictionary stores key-value pairs with O(1) access.",
        "code": "# Python dict é um hash map\nhash_map = {}\nhash_map['chave'] = 'valor'\nprint(hash_map['chave'])  # O(1)"
    },
    {
        "pt": "Busca binária requer um array ordenado e tem complexidade O(log n).",
        "en": "Binary search requires a sorted array and has O(log n) complexity.",
        "code": "def busca_binaria(arr: list[int], alvo: int) -> int:\n    esq, dir = 0, len(arr) - 1\n    while esq <= dir:\n        meio = (esq + dir) // 2\n        if arr[meio] == alvo: return meio\n        elif arr[meio] < alvo: esq = meio + 1\n        else: dir = meio - 1\n    return -1"
    },
    {
        "pt": "Uma árvore binária de busca mantém a propriedade: esquerda < raiz < direita.",
        "en": "A binary search tree maintains the property: left < root < right.",
        "code": "class TreeNode:\n    def __init__(self, val: int):\n        self.val = val\n        self.left = None\n        self.right = None"
    },
]

def build_tech_bilingual_dataset(output_path: str | Path, max_samples: int = 500) -> int:
    """Constrói dataset técnico bilíngue PT-EN."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    count = 0
    with open(output_path, 'w', encoding='utf-8') as f:
        # Replicar pares para atingir max_samples
        for i in range(max_samples):
            pair = BILINGUAL_PAIRS[i % len(BILINGUAL_PAIRS)]
            
            # Formato: instrução PT + instrução EN + código
            text = (
                f"# Tarefa PT: {pair['pt']}\n"
                f"# Task EN: {pair['en']}\n\n"
                f"{pair['code']}"
            )
            
            entry = {"text": text}
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            count += 1
    
    print(f"[OK] Dataset técnico bilíngue salvo em: {output_path}")
    print(f"[OK] {count} amostras geradas")
    print(f"[OK] Tamanho: {output_path.stat().st_size / 1024:.2f} KB")
    return count

if __name__ == "__main__":
    output = Path("data/training/tech_bilingual_dataset.jsonl")
    build_tech_bilingual_dataset(output, max_samples=500)
