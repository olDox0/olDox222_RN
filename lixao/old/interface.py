"""
DOXOADE NEURO-SUITE v2.0
Painel de controle unificado (Visão + Linguagem).
"""
import os
import sys
import time
from doxovis import Cores

#def limpar_tela():
#    os.system('cls' if os.name == 'nt' else 'clear')

def banner():
    print(
    f"""{Cores.CIANO}
    ____  ____  _  _  ____  __ _  ____  ____ 
   (  _ \(  _ )( \/ )/ ___)(  ( \(  __)(_  _)
    )(_) ))(_)( )  ( \___ \/    / ) _)   )(  
   (____/(____)(_/\_)(____/\_)__)(____) (__) 
   
   >> NEURO-SUITE v2.0 | Vision & Language{Cores.RESET}
    """
    )

banner()

def executar_script(script):
    print(f"\n{Cores.AMARELO}🚀 Inicializando {script}...{Cores.RESET}")
    time.sleep(0.5)
    os.system(f"{sys.executable} {script}")
    input(f"\n{Cores.CINZA}[Pressione ENTER para voltar]{Cores.RESET}")

def menu():
    while True:
#        limpar_tela()
        print(f"{Cores.NEGRITO}   --- VISÃO COMPUTACIONAL (MLP) ---{Cores.RESET}")
        print("   [1] 🧪 LABORATÓRIO (Treinar Visão)")
        print("   [2] 🔮 ORÁCULO (Ver Imagens)")
        print("   [3] 🔬 NEUROSCOPE (Raio-X)")
        print("   [4] 🕵️  SABOTADOR (Adversarial)")
        print(f"\n{Cores.NEGRITO}   --- LINGUAGEM NATURAL (RNN) ---{Cores.RESET}")
        print("   [5] 🗣️  DOXOLANG (Treinar/Gerar Código)")
        print("   [6] 🧠 DOXOLOGIC (Raciocínio Híbrido)") # Novo!
        print("\n   [0] ❌ SAIR")
        
        opcao = input(f"\n   {Cores.AZUL}>> Escolha:{Cores.RESET} ")
        
        if opcao == '1': executar_script("treinar.py")
        elif opcao == '2': executar_script("oraculo.py")
        elif opcao == '3': executar_script("neuroscope.py")
        elif opcao == '4': executar_script("adversario.py")
        elif opcao == '5': executar_script("doxolang_pro.py") # Atualizado!
        elif opcao == '6': executar_script("doxologic.py")
        elif opcao == '0':
            print(f"\n   {Cores.VERDE}Encerrando sessão Doxoade... Até logo!{Cores.RESET}")
            break
        else:
            print("   Opção inválida!")
            time.sleep(1)

if __name__ == "__main__":
    menu()