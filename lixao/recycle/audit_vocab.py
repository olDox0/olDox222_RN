# audit_vocab.py
import os
import pickle
from colorama import init, Fore

init(autoreset=True)

MODEL_PATH = os.path.expanduser("~/.doxoade/alfagold_v1.pkl")

def audit():
    print(Fore.YELLOW + "🔍 Auditoria do Vocabulário Alfagold...\n")
    
    if not os.path.exists(MODEL_PATH):
        print(Fore.RED + "❌ Cérebro não encontrado."); return

    with open(MODEL_PATH, 'rb') as f:
        state = pickle.load(f)

    # Recupera o estado do tokenizer
    # Nota: No model.py v2, salvamos como 'tokenizer_state'
    if 'tokenizer_state' not in state:
        print(Fore.RED + "❌ Tokenizer não encontrado no arquivo."); return

    vocab = state['tokenizer_state']['vocab'] # Dict {token: id}
    
    print(f"📊 Total de Tokens: {len(vocab)}")
    print("-" * 40)
    
    # Lista os tokens ordenados por ID
    sorted_vocab = sorted(vocab.items(), key=lambda x: x[1])
    
    # Mostra uma amostra e procura por anomalias
    anomalies = []
    
    print(Fore.CYAN + "ID   | TOKEN")
    for token, tid in sorted_vocab:
        # Visualização segura
        display_token = repr(token)
        print(f"{tid:<4} | {display_token}")
        
        # Detecção de Anomalias
        if len(token) > 1 and not token.isalnum() and not token.strip() == "":
            # Tokens mistos estranhos (ex: 'def:')
            if any(c.isalnum() for c in token) and any(not c.isalnum() for c in token):
                anomalies.append(token)

    print("-" * 40)
    if anomalies:
        print(Fore.RED + f"⚠️  ATENÇÃO: {len(anomalies)} tokens potencialmente 'sujos' detectados:")
        print(Fore.WHITE + f"{anomalies[:20]} ...")
        print("Isso confunde o Arquiteto Lógico, que espera tokens limpos.")
    else:
        print(Fore.GREEN + "✅ Vocabulário parece limpo.")

if __name__ == "__main__":
    audit()