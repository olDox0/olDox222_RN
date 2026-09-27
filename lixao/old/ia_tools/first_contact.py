# ia_tools/first_contact.py
import sys, os, time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ia_core.executive import SiCDoxExecutive
from ia_core.llm_bridge import SiCDoxBridge
from colorama import Fore, init

model = "models/sicdox/Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
sicdox = SiCDoxExecutive(model)

meta = "Dox, preciso de um esqueleto de classe para gerenciar um inventário de hardware no padrão Chief-Gold."

plano, memoria = sicdox.process_goal(meta)

print("\n--- PLANO SUGERIDO ---")
print(plano)
print("\n--- CADEIA CAUSAL (M2A2) ---")
print(memoria)

init(autoreset=True)
bridge = SiCDoxBridge("models/sicdox/Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf")

print(f"{Fore.CYAN}--- Teste de Latência SiCDox ---")
start = time.time()

try:
    # Prompt ultra-simples para resposta curta
    resposta = bridge.ask_sicdox("Diga 'Online'")
    end = time.time()
    
    print(f"\n{Fore.GREEN}Resposta: {resposta}")
    print(f"{Fore.YELLOW}Tempo total: {end - start:.2f}s")
except Exception as e:
    print(f"{Fore.RED}Falha: {e}")