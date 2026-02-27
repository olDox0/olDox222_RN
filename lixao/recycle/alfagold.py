# doxoade/commands/alfagold.py
import click
import os
import sys
import numpy as np
from colorama import Fore, Style

# Path Hack para garantir visibilidade
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path: sys.path.insert(0, project_root)

MODEL_PATH = os.path.expanduser("~/.doxoade/alfagold_v1.pkl")

# [FIX] Imports atualizados para a arquitetura MoE
try:
    from alfagold.core.transformer import Alfagold
    from alfagold.experts.refinement_expert import RefinementExpert
    from alfagold.hive.hive_mind import HiveMindMoE
    
    # Mapeamento de Legado -> Novo (Aliasing)
    # ArquitetoLogico agora é SyntaxExpert
    from alfagold.experts.syntax_expert import SyntaxExpert as ArquitetoLogico
    # HRLAgent agora é gerido pelo PlanningExpert (via Hive)
    # Importamos apenas para evitar NameError, mas o uso recomendado é via Hive
# [DOX-UNUSED]     from alfagold.experts.planning_expert import PlanningExpert
    
except ImportError as e:
    # Se falhar (ex: durante instalação), define stubs para não quebrar a CLI
    print(Fore.RED + f"Erro de carga de IA: {e}")
    Alfagold = None

@click.group()
def alfagold():
    """🌟 Motor Neural Transformer (Next-Gen)."""
    pass

@alfagold.command()
@click.argument('text')
def analyze(text):
    if not Alfagold: return
    model = Alfagold()
    if os.path.exists(MODEL_PATH):
        try: model.load(MODEL_PATH)
        except Exception as e:
            import sys, os
            _, exc_obj, exc_tb = sys.exc_info()
            f_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            line_n = exc_tb.tb_lineno
            print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: analyze\033[0m")
            print(f"\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033[0m")
    print(Fore.CYAN + f"   🧠 Processando: '{text}'")
    ids = model.tokenizer.encode(text)
    print(f"   🔢 Tokens IDs: {ids}")
    logits, _, _ = model.forward(ids)
    print(Fore.GREEN + "   ✅ Análise concluída.")

@alfagold.command()
def init_model():
    if not Alfagold: return
    model = Alfagold(vocab_size=2000, d_model=64)
    model.save(MODEL_PATH)
    print(Fore.GREEN + "🌟 Novo modelo inicializado.")

@alfagold.command()
@click.option('--epochs', default=10)
@click.option('--samples', default=100)
@click.option('--level', default=4)
def train(epochs, samples, level):
    from alfagold.training.train_mtl import train_mtl
    train_mtl()

@alfagold.command()
@click.argument('prompt')
@click.option('--length', default=100)
@click.option('--temp', default=0.7)
@click.option('--strict', is_flag=True, help="Ativa o SyntaxExpert (Arquiteto).")
@click.option('--hrl', is_flag=True, help="Ativa o PlanningExpert (Legacy mode).")
@click.option('--hive', is_flag=True, help="Ativa a Mente de Colmeia (Recomendado).")
def generate(prompt, length, temp, strict, hrl, hive):
    """Gera código usando o modelo Alfagold."""
    if not Alfagold: return
    
    # 1. Carrega Modelo Base
    model = Alfagold()
    if not os.path.exists(MODEL_PATH):
        if not os.path.exists(MODEL_PATH.replace('.pkl', '.npz')):
            print(Fore.RED + "❌ Modelo não encontrado."); return

    try:
        model.load(MODEL_PATH)
        print(Fore.GREEN + "   💾 Cérebro carregado.")
    except Exception as e:
        print(Fore.RED + f"   ❌ Erro ao carregar: {e}"); return

    # 2. Inicializa Cerebelo (Refinamento)
    cerebelo = RefinementExpert()

    # 3. Inicializa HiveMind (O Cérebro Completo)
    hive_mind = HiveMindMoE() if hive else None
    
    # Fallback para modo legado (apenas se Hive não estiver ativo)
    arquiteto = ArquitetoLogico(model.tokenizer) if strict and not hive else None

    print(Fore.CYAN + f"   📝 Prompt: '{prompt}'")
    if hive: print(Fore.MAGENTA + "   🧬 HIVE MIND (MoE): ATIVA")
    
    print(Fore.YELLOW + "   🤖 Escrevendo: ", end="", flush=True)
    
    # --- GERAÇÃO ---
    if hive:
        print("") 
        raw_text = hive_mind.run_sequence(prompt, length=length)
        
        # [DEBUG] Adicione isto para ver o que saiu da colmeia
        print(Fore.RED + f"\n[DEBUG RAIO-X] Raw Text Hex: {raw_text.encode('utf-8').hex()}")
        print(f"[DEBUG RAIO-X] Raw Text Content: '{raw_text}'")
        
        full_text = prompt + raw_text
    else:
        # Modo Legado (Manual)
        input_ids = model.tokenizer.encode(prompt)
        generated_ids = []
        end_token_id = model.tokenizer.vocab.get("ENDMARKER", -1)
        
        # Sincroniza Arquiteto Legado
        if strict and arquiteto:
            for token_id in input_ids:
                token_str = model.tokenizer.decode([token_id]).strip()
                if token_str: arquiteto.observe(token_str)
        
        for _ in range(length):
            current_seq = input_ids + generated_ids
            
            # Forward Simples (Sem Planner)
            logits, _, _ = model.forward(current_seq)
            next_token_logits = logits[-1]
            
            # Amostragem
            scaled_logits = np.clip(next_token_logits / temp, -50, 50)
            exp_logits = np.exp(scaled_logits - np.max(scaled_logits))
            probs = exp_logits / np.sum(exp_logits)
            
            # Validação Strict (Arquiteto)
            next_id = None
            if strict and arquiteto:
                # Tenta 10x
                top_indices = np.argsort(probs)[::-1][:15]
                top_probs = probs[top_indices] / np.sum(probs[top_indices])
                for _ in range(10):
                    cand_id = int(np.random.choice(top_indices, p=top_probs))
                    cand_str = model.tokenizer.decode([cand_id]).strip()
                    if not cand_str: 
                        next_id = cand_id; break
                    valido, _ = arquiteto.validar(cand_str)
                    if valido:
                        next_id = cand_id; break
                
                # Resgate
                if next_id is None:
                    sug = arquiteto.sugerir_correcao()
                    if sug:
                        sug_ids = model.tokenizer.encode(sug)
                        if sug_ids: next_id = sug_ids[0]

            # Fallback
            if next_id is None:
                next_id = int(np.random.choice(len(probs), p=probs))

            if next_id == end_token_id: break
            generated_ids.append(next_id)
            
            # Atualiza Arquiteto
            if strict and arquiteto:
                token_str = model.tokenizer.decode([next_id]).strip()
                if token_str: arquiteto.observe(token_str)
                
            print(".", end="", flush=True)

        print(Fore.GREEN + " [OK]\n")
        raw_gen = model.tokenizer.decode(generated_ids)
        full_text = prompt + raw_gen

    # --- PÓS-PROCESSAMENTO (Cerebelo) ---
    print(Fore.CYAN + "   🔧 Cerebelo: Refinando...")
    refined_text = cerebelo.process(full_text)
    
    print(Style.BRIGHT + "-" * 40)
    print(Fore.WHITE + refined_text)
    print(Style.BRIGHT + "-" * 40 + Style.RESET_ALL)