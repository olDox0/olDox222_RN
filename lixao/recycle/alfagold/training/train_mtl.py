# alfagold/training/train_mtl.py
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

def make_batches(data, batch_size, pad_id=0):
    np.random.shuffle(data)
    for i in range(0, len(data), batch_size):
        chunk = data[i:i + batch_size]
        chunk.sort(key=lambda x: len(x[0]), reverse=True)
        texts = [x[0] for x in chunk]
        phases = [x[1] for x in chunk]
        yield texts, phases

def train_mtl():
    print(Fore.YELLOW + "🧠 Iniciando Treino Bicameral V2.4 (Estabilidade Extrema)...")
    
    # Reduzindo Batch para atualizar pesos mais frequentemente com passos menores
    BATCH_SIZE = 16 
    
    # 1. Configuração Otimizada
    # Reduzi vocab_size para 500 para evitar ruído de tokens não usados
    model = Alfagold(vocab_size=500, d_model=128, n_heads=2, dropout_rate=0.0)
    
    # LR muito mais conservador
    optimizer = AdamW(model.params, lr=0.0002)
    
    router = AdaptiveRouter(d_model=128, num_clusters=4)
    
    # 2. Dados
    raw_data = generate_mtl_data(count=1000)
    full_text = " ".join([d[0] for d in raw_data])
    model.tokenizer.train(full_text, vocab_size=450) # Deixa margem para especiais
    
    print("   🔨 Pré-processando dataset...")
    processed_data = []
    pad_id = model.tokenizer.vocab.get("<PAD>", 0)
    
    for text, target_phases in raw_data:
        words = text.split()
        token_ids = []
        phase_ids = []
        for i, w in enumerate(words):
            ids = model.tokenizer.encode(w)
            token_ids.extend(ids)
            phase_ids.extend([target_phases[i]] * len(ids))
        if len(token_ids) > 1:
            processed_data.append((token_ids, phase_ids))
            
    start_time = time.time()
    
    # Scheduler Manual
    best_loss = float('inf')
    
    for epoch in range(30):
        total_loss = 0
        total_batches = 0
        cluster_counts = np.zeros(4)
        
        for batch_tokens, batch_phases in make_batches(processed_data, BATCH_SIZE):
            max_len = max(len(t) for t in batch_tokens)
            if max_len > model.max_len: max_len = model.max_len
            
            curr_len = max_len - 1
            X_in = np.full((len(batch_tokens), curr_len), pad_id, dtype=np.int32)
            Y_tok = np.full((len(batch_tokens), curr_len), pad_id, dtype=np.int32)
            
            for i, (seq, ph) in enumerate(zip(batch_tokens, batch_phases)):
                l = min(len(seq), curr_len + 1)
                X_in[i, :l-1] = seq[:l-1]
                Y_tok[i, :l-1] = seq[1:l]
            
            batch_loss = 0
            grads_acc = {k: np.zeros_like(v) for k, v in model.params.items()}
            
            for i in range(len(X_in)):
                valid_len = np.sum(X_in[i] != pad_id)
                if valid_len == 0: continue
                
                x_single = X_in[i, :valid_len]
                y_single = Y_tok[i, :valid_len]
                
                # Forward
                logits_tok, logits_phase, cache = model.forward(x_single, training=True)
                
                # Roteamento com Ruído (Para evitar colapso de cluster)
                if 'x_final' in cache:
                    h_state = cache['x_final'][-1]
                    # Adiciona ruído gaussiano leve ao estado para variar o roteamento
                    noisy_state = h_state + np.random.randn(*h_state.shape) * 0.1
                    cluster_ids, _ = router.route(noisy_state, training=True)
                    cluster_counts[cluster_ids] += 1
                
                # Loss
                probs = softmax(logits_tok)
                rows = np.arange(valid_len)
                
                # Safety Clip para Log
                probs = np.clip(probs, 1e-9, 1.0)
                loss = -np.sum(np.log(probs[rows, y_single])) / valid_len
                batch_loss += loss
                
                # Backward
                d_logits = probs
                d_logits[rows, y_single] -= 1
                d_logits /= valid_len
                
                # Otimização: Ignora backward da Phase Head para focar em texto
                d_phase_dummy = np.zeros_like(logits_phase)
                
                sample_grads = model.backward(d_logits, d_phase_dummy, cache)
                
                for k in grads_acc:
                    grads_acc[k] += sample_grads[k]
            
            if len(X_in) > 0:
                for k in grads_acc: grads_acc[k] /= len(X_in)
                
                # Clipping Agressivo (0.5)
                total_norm = np.sqrt(sum(np.sum(g**2) for g in grads_acc.values()))
                if total_norm > 0.5:
                    scale = 0.5 / (total_norm + 1e-6)
                    for k in grads_acc: grads_acc[k] *= scale
                
                optimizer.step(grads_acc)
                total_loss += batch_loss / len(X_in)
                total_batches += 1
            
        avg_loss = total_loss / total_batches if total_batches > 0 else 0
        elapsed = time.time() - start_time
        
        # Monitoramento de Clusters
        total_c = np.sum(cluster_counts) + 1e-9
        dist = cluster_counts / total_c
        dist_str = " ".join([f"{p:.2f}" for p in dist])
        
        print(f"Ep {epoch+1:02d}: Loss {avg_loss:.4f} | Clusters: [{dist_str}] ({elapsed:.1f}s)")
        
        # Checkpoint apenas se melhorou (ou nas ultimas)
        if avg_loss < best_loss:
            best_loss = avg_loss
            model.save(os.path.expanduser("~/.doxoade/alfagold_v1.pkl"))
            
        start_time = time.time()
        
    print(Fore.GREEN + f"💾 Treino Concluído. Melhor Loss: {best_loss:.4f}")

if __name__ == "__main__":
    train_mtl()