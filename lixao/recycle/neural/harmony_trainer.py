# doxoade/neural/harmony_trainer.py
import numpy as np
import sys
import os
from colorama import Fore

# Fix de Importação
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path: sys.path.insert(0, project_root)

from doxoade.neural.alfagold.model import Alfagold
from doxoade.neural.hrl import HRLAgent
from doxoade.neural.logic import ArquitetoLogico

def train_harmony(episodes=200):
    print(Fore.YELLOW + f"   🧘 Iniciando Treino de Harmonia ({episodes} ciclos)...")
    print(Fore.CYAN + "   Objetivo: Sincronizar Intenção (HRL) com Regras (Arquiteto)")

    try:
        worker = Alfagold()
        path = os.path.expanduser("~/.doxoade/alfagold_v1.pkl")
        if os.path.exists(path):
            worker.load(path)
        else:
            print(Fore.RED + "   ❌ Worker não encontrado."); return
            
        agent = HRLAgent(worker)
        arquiteto = ArquitetoLogico()
    except Exception as e:
        print(Fore.RED + f"   ❌ Erro ao carregar sistemas: {e}"); return

    prompt = "def salvar"
    input_ids = worker.tokenizer.encode(prompt)
    
    hits = 0
    misses = 0

    for ep in range(episodes):
        arquiteto.reset()
        for tid in input_ids: 
            t_str = worker.tokenizer.decode([tid])
            arquiteto.observar(t_str)
        
        current_seq = list(input_ids)
# [DOX-UNUSED]         episode_reward = 0
        
        for step in range(10):
            # [FIX CRÍTICO] Passa o estado do Arquiteto para o HRL "ver" o contexto
            estado_atual = arquiteto.estado
            logits, option_idx = agent.step(current_seq, symbolic_state=estado_atual, training=True)
            
            # 2. Escolha do Token
            next_id = np.argmax(logits)
            token_str = worker.tokenizer.decode([next_id]).strip()
            
            # 3. Cálculo de Recompensa
            reward = 0.0
            
            # A: Recompensa por Estratégia Correta (O mais importante)
            if estado_atual in ["NOME", "ARGS_PRE", "ARGS", "TRANSICAO"]:
                if option_idx == 0: reward += 1.0 # START_FUNC
                else: reward -= 2.0 # Erro estratégico
            elif estado_atual == "CORPO":
                if option_idx == 1: reward += 2.0 # I/O
                elif option_idx == 0: reward -= 1.0
            
            # B: Validação Sintática (Feedback do Token)
            valido, _ = arquiteto.validar(token_str)
            if valido:
                reward += 0.2
                arquiteto.observar(token_str)
            else:
                reward -= 0.5

            # 4. Feedback Imediato
            agent.register_feedback(next_id, reward)
            
            current_seq.append(next_id)
            if reward > 0: hits += 1
            else: misses += 1
        
        # Consolida aprendizado
        agent.end_episode()
            
        if (ep + 1) % 20 == 0:
            acc = hits / (hits + misses + 1e-9)
            print(f"   Ep {ep+1}: Precisão de Sincronia {acc*100:.1f}%")
            hits, misses = 0, 0

    agent.save()
    print(Fore.GREEN + "   💾 HRL Sincronizado e Salvo.")

if __name__ == "__main__":
    train_harmony()