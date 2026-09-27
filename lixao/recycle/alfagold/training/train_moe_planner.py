# alfagold/training/train_moe_planner.py
import numpy as np
import sys
import os
from colorama import init, Fore

init(autoreset=True)

# Path fix
current = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(os.path.dirname(current))
if project_root := root not in sys.path: sys.path.insert(0, root)

from alfagold.experts.generator_expert import GeneratorExpert
from alfagold.experts.planning_expert import PlanningExpert
from alfagold.experts.syntax_expert import SyntaxExpert
from alfagold.core.state_packet import StatePacket

def train():
    print(Fore.YELLOW + "🧠 Treinando o Lobo Frontal (MoE Planner) - Fase 2...")
    
    gen = GeneratorExpert()
    syn = SyntaxExpert(gen.model.tokenizer)
    planner = PlanningExpert(d_model=gen.model.d_model, vocab_size=len(gen.model.tokenizer.vocab))
    
    # Reset para limpar vícios anteriores
    # planner = PlanningExpert(...) # Se quiser resetar pesos, descomente
    
    prompt = "def salvar"
    base_ids = gen.model.tokenizer.encode(prompt)
    
    hits = 0
    misses = 0
    
    # Aumentei para 300 episódios para garantir fixação
    for ep in range(300):
        syn.reset()
        for t in base_ids: syn.observe(gen.decode(t))
        packet = StatePacket(token_ids=list(base_ids))
        
        for _ in range(15):
            packet.syntax_state = syn.estado
            packet = planner.process(packet, training=True)
            packet = gen.process(packet)
            
            logits = packet.logits
            exps = np.exp(logits - np.max(logits))
            probs = exps / np.sum(exps)
            next_id = int(np.random.choice(len(probs), p=probs))
            
            token_str = gen.decode(next_id).strip()
            if not token_str: token_str = " "
            
            reward = 0
            opt = planner.current_option
            state = syn.estado
            
            # REGRAS ESTRATÉGICAS
            if state in ["NOME", "ARGS_PRE", "ARGS"]:
                if opt == 0: reward += 1.0 
                else: reward -= 2.0
            elif state == "CORPO":
                if opt == 1: reward += 2.0 
                elif opt == 0: reward -= 1.0

            # VALIDAÇÃO SINTÁTICA (Aqui a mágica acontece)
            valido, motivo = syn.validar(token_str)
            if valido:
                reward += 0.5
                syn.observe(token_str)
                
                # Bônus Combo: with -> open
                if syn.ultimo_token == "open" and syn.penultimo_token == "with":
                    reward += 5.0 # JACKPOT!
            else:
                reward -= 1.0 # Punição

            planner.register_feedback(next_id, reward)
            packet.token_ids.append(next_id)
            
            if reward > 0: hits += 1
            else: misses += 1
            
        planner.train_episode()
        
        if (ep+1) % 50 == 0:
            acc = hits / (hits + misses + 1e-9)
            print(f"   Ep {ep+1}: Precisão {acc*100:.1f}%")
            hits, misses = 0, 0
            
    planner.save()
    print(Fore.GREEN + "✅ Planner treinado com regras rígidas de I/O.")

if __name__ == "__main__":
    train()