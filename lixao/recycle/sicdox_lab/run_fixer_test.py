# tests/sicdox_lab/run_fixer_test.py
from doxoade.fixer import AutoFixer
import os

# Mock minimalista do logger para o Fixer
class DummyLogger:
    def add_finding(self, *args): pass

def reset_dummy_file(path):
    """Reseta o arquivo para o estado sujo original."""
    content = [
        "def calcular_risco_teste():\n",
        "    try:\n",
        "        x = 1 / 0  # Forçar erro\n",
        "    except: return False\n",
        "\n",
        "if __name__ == \"__main__\":\n",
        "    calcular_risco_teste()\n"
    ]
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(content)

fixer = AutoFixer(DummyLogger())
target = "tests/sicdox_lab/target_dummy.py"

# 1. Resetar ambiente
reset_dummy_file(target)

print(f"--- [ 🧪 LABORATÓRIO ] Iniciando Teste em {target} ---")

# 2. Testar o REPLACE_WITH_UNDERSCORE (Agora deve comentar a linha)
print("\n[ 1 ] Aplicando: REPLACE_WITH_UNDERSCORE (L3)...")
fixer.apply_fix(target, 3, "REPLACE_WITH_UNDERSCORE")

# 3. Testar o RESTRICT_EXCEPTION (Forensic Edition)
# Nota: Como a linha 3 foi apenas comentada (mesma linha), o except continua na L4.
print("[ 2 ] Aplicando: RESTRICT_EXCEPTION (L4)...")
fixer.apply_fix(target, 4, "RESTRICT_EXCEPTION")

print("\n✅ Processo concluído! Verificando resultado final:\n" + "="*50)
with open(target, 'r') as f:
    print(f.read())
print("="*50)