# doxoade/neural/alfagold/trainer.py
import time
import numpy as np
import os
from colorama import Fore

from .model import Alfagold
from .optimizer import AdamW
from ..adapter import BrainLoader 

class AlfaTrainer:
    def __init__(self, model_path=None):
        self.model_path = model_path or os.path.expanduser("~/.doxoade/alfagold_v1.pkl")
        
        # Inicializa Modelo
        self.model = Alfagold(vocab_size=2000, d_model=64, max_len=128)
        
        if os.path.exists(self.model_path):
            try:
                self.model.load(self.model_path)
                print(Fore.GREEN + "   💾 Modelo carregado.")
            except Exception as e:
                import sys, os
                _, exc_obj, exc_tb = sys.exc_info()
                f_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                line_n = exc_tb.tb_lineno
                print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: __init__\033[0m")
                print(f"\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033[0m")
            
        self.optimizer = AdamW(self.model.params, lr=0.001)
        self.loader = BrainLoader()

    def train_cycle(self, epochs=10, samples=500, difficulty=1):
        print(Fore.YELLOW + f"   🚀 Iniciando Treino Alfagold (Nível {difficulty})...")
        
        # 1. Gerar Dados
        raw_data = self.loader.get_training_data(limit=samples, difficulty=difficulty)
        
        # 2. Treinar Tokenizer
        full_text = " ".join([p[0] + " " + p[1] for p in raw_data])
        print(f"   🔨 Refinando BPE com {len(full_text)} caracteres...")
        self.model.tokenizer.train(full_text, vocab_size=2000)
        
        start_time = time.time()
        
        for epoch in range(epochs):
            total_loss = 0
            count = 0
            
            np.random.shuffle(raw_data)
            
            for input_str, target_str in raw_data:
                full_seq = input_str + " " + target_str
                ids = self.model.tokenizer.encode(full_seq)
                
                if len(ids) < 2: continue
                
                x_ids = ids[:-1]
                y_ids = np.array(ids[1:])
                
                # --- CICLO DE TREINO EXPLÍCITO ---
                
                # A. Forward
                logits, cache = self.model.forward(x_ids)
                
                # B. Loss (Cross Entropy Manual)
                N = logits.shape[0]
                # Estabilidade numérica do Softmax
                exps = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
                probs = exps / np.sum(exps, axis=-1, keepdims=True)
                
                correct_probs = probs[np.arange(N), y_ids]
                loss = -np.sum(np.log(correct_probs + 1e-9)) / N
                
                # C. Gradiente da Loss
                dlogits = probs
                dlogits[np.arange(N), y_ids] -= 1
                dlogits /= N
                
                # D. Backward
                grads = self.model.backward(dlogits, cache)
                
                # E. Update
                self.optimizer.step(grads)
                
                total_loss += loss
                count += 1
            
            avg_loss = total_loss / count if count > 0 else 0
            
            # Reporta progresso
            if (epoch + 1) % 1 == 0: 
                elapsed = time.time() - start_time
                print(f"   Epoca {epoch+1}/{epochs}: Loss {avg_loss:.4f} ({elapsed:.1f}s)")
                start_time = time.time()
                
        self.model.save(self.model_path)
        print(Fore.GREEN + "   💾 Modelo salvo e atualizado.")