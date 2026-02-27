# doxoade/neural/hrl_trainer.py
import numpy as np
# [DOX-UNUSED] import time
import sys
import os
from colorama import Fore, Style

# --- FIX DE IMPORTAÇÃO ---
# Adiciona a raiz do projeto ao path para permitir imports absolutos
current_dir = os.path.dirname(os.path.abspath(__file__)) # .../doxoade/neural
project_root = os.path.dirname(os.path.dirname(current_dir)) # .../
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Imports Absolutos
from doxoade.neural.alfagold.model import Alfagold
from doxoade.neural.hrl import HRLAgent
from doxoade.neural.logic import ArquitetoLogico

class ManagerBootcamp:
    def __init__(self):
        # Carrega o Alfagold (Worker) já treinado
        self.worker = Alfagold()
        try:
            path = os.path.expanduser("~/.doxoade/alfagold_v1.pkl")
            if os.path.exists(path):
                self.worker.load(path)
                print(Fore.GREEN + "   ✅ Worker (Alfagold) carregado.")
            else:
                print(Fore.RED + "   ❌ Worker não encontrado no disco.")
                return
        except Exception as e:
            print(Fore.RED + f"   ❌ Erro ao carregar Worker: {e}")
            return

        self.agent = HRLAgent(self.worker)
        self.logic = ArquitetoLogico()

    def train_loop(self, episodes=100):
        print(Fore.YELLOW + f"   🏋️ Iniciando Bootcamp de Gerentes ({episodes} episódios)...")
        print(Fore.CYAN + "   Objetivo: Aprender a transição START -> IO -> BODY")

        rewards_history = []
        
        for ep in range(episodes):
            prompt = "def salvar"
            input_ids = self.worker.tokenizer.encode(prompt)
            generated_ids = []
            
            # Estado inicial do Arquiteto
            self.logic.reset()
            # Alimenta o arquiteto com o prompt
            for tid in input_ids: 
                t_str = self.worker.tokenizer.decode([tid])
                self.logic.observar(t_str)

            episode_reward = 0
            actions_taken = []
            
            # Loop de Geração (Mini-Episódio)
            for _ in range(20): 
                current_seq = input_ids + generated_ids
                
                # 1. Agente escolhe opção
                logits, option_idx = self.agent.step(current_seq, symbolic_state=self.logic.estado, training=True)
                actions_taken.append(option_idx)
                
                # 2. Escolha do Token
                # Normalização segura dos logits
                logits_safe = logits - np.max(logits)
                probs = np.exp(logits_safe) / np.sum(np.exp(logits_safe))
                
                next_id = int(np.random.choice(len(probs), p=probs))
                token_str = self.worker.tokenizer.decode([next_id]).strip()
                generated_ids.append(next_id)
                
                # 3. CÁLCULO DE RECOMPENSA
                step_reward = 0
                
                # A: Sintaxe Válida?
                valido, _ = self.logic.validar(token_str)
                if valido:
                    step_reward += 0.2
                    self.logic.observar(token_str)
                else:
                    step_reward -= 0.5 # Punição
                    
                # B: Coerência da Opção (Estratégia)
                # Opção 0: START_FUNC, 1: IO, 2: BODY
                if option_idx == 1 and token_str in ['open', 'with', 'as', 'file']:
                    step_reward += 1.5
                if option_idx == 0 and token_str in ['(', ')', ':']:
                    step_reward += 1.0
                if option_idx == 0 and token_str in ['write', 'read', 'with']:
                    step_reward -= 1.0 # Tentou IO na assinatura
                    
                # 4. Feedback Granular
                self.agent.register_feedback(next_id, step_reward)
                episode_reward += step_reward
            
            # Fim do Episódio
# [DOX-UNUSED]             loss = self.agent.end_episode()
#            rewards_history.append(episode_reward)
            
            if (ep + 1) % 10 == 0:
                avg = np.mean(rewards_history[-10:])
                code = self.worker.tokenizer.decode(generated_ids)
                # Formatação visual
                code_preview = code.replace('\n', ' ')[:50] + "..." if len(code) > 50 else code
                print(f"   Ep {ep+1}: Reward {avg:.2f} | Ops: {actions_taken[:8]}...")
                print(Style.DIM + f"      Gerado: {code_preview}" + Style.RESET_ALL)

        self.agent.save()
        print(Fore.GREEN + "   💾 HRL Manager treinado e salvo.")

if __name__ == "__main__":
    bootcamp = ManagerBootcamp()
    if hasattr(bootcamp, 'agent'):
        # Aumentei para 100 episódios para garantir convergência
        bootcamp.train_loop(episodes=100)