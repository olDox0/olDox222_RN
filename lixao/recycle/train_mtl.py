import numpy as np
import sys
import os
import time
from colorama import init, Fore

init(autoreset=True)
current = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(os.path.dirname(current))
if root not in sys.path: sys.path.insert(0, root)

from alfagold.core.transformer import Alfagold
from alfagold.core.math_utils import softmax
from alfagold.core.optimizer import AdamW
from alfagold.core.adaptive_router import AdaptiveRouter
from alfagold.training.data_gen_mtl import generate_mtl_data

def train_mtl():
    print(Fore.YELLOW + "🧠 Iniciando Treino Adaptativo (K-Means Clustering)...")
    
    # 1. Configuração
    # Reset do modelo para limpar estados corrompidos anteriores
    model = Alfagold(vocab_size=2000, d_model=64)
    optimizer = AdamW(model.params, lr=0.001)
    
    # O Roteador Inteligente
    # 4 Clusters: Assinatura, I/O, Lógica, Estrutura
    router = AdaptiveRouter(d_model=64, num_clusters=4)
    
    # 2. Dados
    raw_data = generate_mtl_data(count=1000)
    full_text = " ".join([d[0] for d in raw_data])
    model.tokenizer.train(full_text, vocab_size=500)
    
    start_time = time.time()
    
    for epoch in range(30):
        total_loss = 0
        cluster_counts = np.zeros(4)
        
        # Shuffle
        indices = np.arange(len(raw_data))
        np.random.shuffle(indices)
        
        for idx in indices:
            text, _ = raw_data[idx]
            
            # Tokenização rápida
            token_ids = model.tokenizer.encode(text)
            if len(token_ids) < 2: continue
            
            # Arrays numpy para indexação avançada
            token_ids = np.array(token_ids)
            x = token_ids[:-1]
            y = token_ids[1:]
            
            # 1. Forward Transformer
            # [CRÍTICO] training=True ativa o Master Cache e o retorno correto
            logits_tok, logits_phase, cache = model.forward(x, training=True)
            
            # 2. Roteamento Inteligente (Detect Patterns)
            # Verifica se x_final está disponível no cache (exige fix no transformer.py)
            if 'x_final' in cache:
                hidden_state = cache['x_final'][-1] # Estado do último token
                cluster_id, att_weights = router.route(hidden_state, training=True)
                cluster_counts[cluster_id] += 1
            else:
                # Fallback se o transformer.py ainda não estiver exportando x_final
                # (Evita crash, mas perde a funcionalidade de clustering)
                cluster_id = 0
            
            # 3. Loss (Cross Entropy)
            probs = softmax(logits_tok)
            N = len(x)
            
            # Loss simples (sem variância complexa por enquanto)
            loss_per_token = -np.log(probs[np.arange(N), y] + 1e-9)
            loss = np.mean(loss_per_token)
            
            # 4. Backward & Update
            d_logits = probs
            d_logits[np.arange(N), y] -= 1
            d_logits /= N
            
            # Backward ignora phase head (zeros) para focar em texto
            d_phase_dummy = np.zeros_like(logits_phase)
            
            grads = model.backward(d_logits, d_phase_dummy, cache)
            
            # Clip de Segurança
            total_norm = np.sqrt(sum(np.sum(g**2) for g in grads.values()))
            if total_norm > 1.0:
                scale = 1.0 / (total_norm + 1e-6)
                for k in grads: grads[k] *= scale
            
            optimizer.step(grads)
            total_loss += loss
            
        avg_loss = total_loss / len(raw_data)
        elapsed = time.time() - start_time
        
        # Visualização dos Padrões encontrados
        total_clusters = np.sum(cluster_counts) + 1e-9
        cluster_dist = cluster_counts / total_clusters
        dist_str = " ".join([f"{p:.2f}" for p in cluster_dist])
        
        print(f"Ep {epoch+1:02d}: Loss {avg_loss:.4f} | Clusters: [{dist_str}] ({elapsed:.1f}s)")
        start_time = time.time()
        
    model.save(os.path.expanduser("~/.doxoade/alfagold_v1.pkl"))
    print(Fore.GREEN + "💾 Modelo Adaptativo Salvo.")

if __name__ == "__main__":
    train_mtl()