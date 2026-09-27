# alfagold/tools/opt_guard.py
import os
import re
from colorama import init, Fore

init(autoreset=True)

FORBIDDEN_PATTERNS = [
    # (Regex, Mensagem de Erro, Gravidade)
    (r"np\.exp\(", "Uso de 'np.exp' detectado. Use 'LUT.exp' para performance.", "CRÍTICO"),
    (r"np\.tanh\(", "Uso de 'np.tanh' detectado. Use 'LUT.gelu' ou adicione à LUT.", "CRÍTICO"),
    (r"out\s*=", "Uso inseguro de 'out=' em NumPy. Use atribuição por slice '[:]'.", "CRÍTICO"),
    (r"dtype\s*=\s*np\.float64", "Uso de float64 gasta 2x memória. Use float32.", "WARNING"),
    (r"dtype\s*=\s*float\)", "Uso implícito de float64. Especifique dtype=np.float32.", "WARNING"),
]

# Arquivos isentos (onde a matemática é definida)
WHITELIST = ["math_lut.py", "math_utils.py", "opt_guard.py"]

def scan_directory(root_dir):
    print(Fore.CYAN + f"🛡️  [OPT-GUARD] Escaneando {root_dir} por regressões de performance...")
    issues_found = 0
    
    for root, _, files in os.walk(root_dir):
        for file in files:
            if not file.endswith(".py"): continue
            if file in WHITELIST: continue
            
            path = os.path.join(root, file)
            
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    
                for i, line in enumerate(lines):
                    # Ignora comentários
                    if line.strip().startswith("#"): continue
                    
                    for pattern, msg, severity in FORBIDDEN_PATTERNS:
                        if re.search(pattern, line):
                            color = Fore.RED if severity == "CRÍTICO" else Fore.YELLOW
                            print(f"{color}   [{severity}] {file}:{i+1}")
                            print(f"      Code: {line.strip()}")
                            print(f"      Dica: {msg}")
                            issues_found += 1
            except Exception as e:
                print(Fore.RED + f"   Erro ao ler {file}: {e}")

    if issues_found == 0:
        print(Fore.GREEN + "✅ Nenhuma regressão de otimização encontrada.")
    else:
        print(Fore.RED + f"\n❌ Encontrados {issues_found} problemas de otimização.")

if __name__ == "__main__":
    # Escaneia a pasta alfagold
    target = os.path.join("alfagold")
    if os.path.exists(target):
        scan_directory(target)
    else:
        # Fallback se rodar de dentro da pasta
        scan_directory(".")