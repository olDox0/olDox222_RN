# alfagold/tools/neuroscope.py
import numpy as np
import os
import sys
from colorama import init, Fore, Style

init(autoreset=True)

# Path fix
current = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(os.path.dirname(current))
if root not in sys.path: sys.path.insert(0, root)

from alfagold.core.transformer import Alfagold
from alfagold.core.math_utils import softmax

def print_top_k(tokenizer, logits, k=5):
    probs = softmax(logits)
    top_indices = np.argsort(probs)[::-1][:k]
    
    print(Fore.CYAN + "   Distribuição de Probabilidade:")
    
    for idx in top_indices:
        token_str = tokenizer.decode([idx])
        token_repr = repr(token_str)
        prob = probs[idx] * 100
        
        color = Fore.GREEN if prob > 50 else (Fore.YELLOW if prob > 10 else Style.DIM)
        bar_len = int(prob / 2)
        bar = "█" * bar_len
        
        print(f"   {color}{bar} {prob:5.1f}% | ID {idx:<4} | {token_repr}{Style.RESET_ALL}")

def neuroscope():
    print(Fore.YELLOW + "🔬 [NEUROSCOPE] Iniciando Diagnóstico Cognitivo...")
    
    model = Alfagold()
    path = os.path.expanduser("~/.doxoade/alfagold_v1.pkl")
    
    # [FIX] Verifica também o formato Aegis (.npz)
    base_path = path.replace('.pkl', '')
    if not os.path.exists(path) and not os.path.exists(base_path + ".npz"):
        print(Fore.RED + f"❌ Modelo não encontrado em: {base_path}.*")
        return
        
    try:
        model.load(path)
        print(Fore.GREEN + f"   💾 Modelo carregado. Vocab: {len(model.tokenizer.vocab)}")
        print(Style.DIM + f"   (Dimensão: {model.d_model}, Heads: {model.params.get('Wq').shape})")
    except Exception as e:
        print(Fore.RED + f"❌ Erro ao carregar: {e}"); return

    # --- BATERIA DE TESTES ---
    
    # TESTE 1: Assinatura de Função
    prompt1 = "def"
    print(f"\n1️⃣  Estímulo: '{prompt1}' (Esperado: nome de função)")
    ids = model.tokenizer.encode(prompt1)
    logits, _, _ = model.forward(ids)
    print_top_k(model.tokenizer, logits[-1])

    # TESTE 2: Estrutura I/O (O teste de fogo)
    prompt2 = "def salvar(arquivo): with"
    print(f"\n2️⃣  Estímulo: '{prompt2}' (Esperado: 'open')")
    ids = model.tokenizer.encode(prompt2)
    logits, _, _ = model.forward(ids)
    print_top_k(model.tokenizer, logits[-1])

    # TESTE 3: Argumentos
    prompt3 = "def ler(nome"
    print(f"\n3️⃣  Estímulo: '{prompt3}' (Esperado: ',' ou ')')")
    ids = model.tokenizer.encode(prompt3)
    logits, _, _ = model.forward(ids)
    print_top_k(model.tokenizer, logits[-1])
    
    # TESTE 4: Ponto final
    prompt4 = "f.write(dados"
    print(f"\n4️⃣  Estímulo: '{prompt4}' (Esperado: ')')")
    ids = model.tokenizer.encode(prompt4)
    logits, _, _ = model.forward(ids)
    print_top_k(model.tokenizer, logits[-1])

if __name__ == "__main__":
    neuroscope()