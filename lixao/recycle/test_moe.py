# test_moe.py
from alfagold.hive.hive_mind import HiveMindMoE
from colorama import init, Fore, Style
init(autoreset=True)

print(Fore.YELLOW + "🔌 Iniciando MoE...")
hive = HiveMindMoE()

prompt = "def teste"
print(Fore.CYAN + f"🤖 Gerando continuação para: '{prompt}'...")

# O run_sequence retorna o texto COMPLETO (Prompt + Geração) refinado
resultado_completo = hive.run_sequence(prompt)

print(Fore.GREEN + "\n📝 Resultado Final:")
print(Style.BRIGHT + resultado_completo)