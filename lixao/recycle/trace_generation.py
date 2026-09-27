# trace_generation.py
import os
import sys
import numpy as np
from colorama import init, Fore, Style

init(autoreset=True)

# Path Hack
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path: sys.path.insert(0, current_dir)

from alfagold.core.transformer import Alfagold
from alfagold.experts.syntax_expert import SyntaxExpert
from alfagold.experts.planning_expert import PlanningExpert
# [DOX-UNUSED] from alfagold.core.adaptive_router import AdaptiveRouter
from alfagold.core.state_packet import StatePacket
# [DOX-UNUSED] from alfagold.core.math_utils import softmax

def trace():
    print(Fore.YELLOW + "🎛️  [PAINEL DE CONTROLE] Rastreamento de Geração Neural v1.2")
    
    model = Alfagold()
    path = os.path.expanduser("~/.doxoade/alfagold_v1.pkl")
    base_path = path.replace('.pkl', '')
    
    if os.path.exists(path) or os.path.exists(base_path + ".npz"):
        try:
            model.load(path)
            print(Fore.GREEN + f"   💾 Modelo carregado. Vocab: {len(model.tokenizer.vocab)}")
        except Exception as e:
            print(Fore.RED + f"   ❌ Erro de carga: {e}"); return
    else:
        print(Fore.RED + "   ❌ Modelo não encontrado. Treine primeiro!"); return

    # [FIX] Desativa Dropout para diagnóstico determinístico
    model.dropout_rate = 0.0

    syntax = SyntaxExpert(model.tokenizer)
    planner = PlanningExpert(d_model=model.d_model, vocab_size=len(model.tokenizer.vocab))
    
    prompt = "def salvar"
    print(Fore.CYAN + f"   📝 Prompt: '{prompt}'")
    
    input_ids = model.tokenizer.encode(prompt)
    generated_ids = []
    
    syntax.reset()
    for tid in input_ids:
        token_str = model.tokenizer.decode([tid]) 
        syntax.observe(token_str.strip())

    print(f"\n   {'STEP':<5} | {'ID':<5} | {'TOKEN':<10} | {'PROB':<6} | {'ESTADO':<10} | {'MASK'}")
    print("   " + "-"*65)

    for step in range(20): 
        current_seq = input_ids + generated_ids
        
        packet = StatePacket(token_ids=current_seq, syntax_state=syntax.estado)
        
        # [FIX] training=True força o retorno de 'x_final' e 'cache' completo
        logits, _, cache = model.forward(current_seq, training=True)
        base_logits = logits[-1]
        
        packet.embedding_vector = cache['x_final'][-1]
        packet.logits = base_logits
        packet = planner.process(packet)
        
        current_logits = packet.logits
        mask = syntax.get_inhibition_mask(current_logits.shape[0])
        final_logits = current_logits + mask
        
        temp = 0.1
        scaled = np.clip(final_logits / temp, -50, 50)
        exps = np.exp(scaled - np.max(scaled))
        probs = exps / np.sum(exps)
        
        next_id = int(np.argmax(probs))
        prob_val = probs[next_id]
        
        raw_token = model.tokenizer.decode([next_id])
        clean_token = raw_token.strip()
        
        mask_val = mask[next_id] if next_id < len(mask) else 0
        
        color = Fore.WHITE
        if not raw_token: color = Fore.RED 
        elif mask_val < 0: color = Fore.MAGENTA 
        elif mask_val > 0: color = Fore.GREEN # Boost
        
        print(f"   {step:<5} | {next_id:<5} | {color}{repr(raw_token):<10}{Style.RESET_ALL} | {prob_val:.2f}   | {syntax.estado:<10} | {mask_val:.0f}")
        
        # Hack de espaço para o Arquiteto
        if not clean_token and next_id == model.tokenizer.vocab.get(" ", -1): clean_token = " "
        
        syntax.observe(clean_token)
        generated_ids.append(next_id)

    print("\n   🔍 Texto Final Decodificado:")
    full_text = model.tokenizer.decode(generated_ids)
    print(f"   '{full_text}'")

if __name__ == "__main__":
    trace()