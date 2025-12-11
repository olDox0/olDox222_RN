"""
DOXOVIS v2.0 (Colorized)
Módulo de visualização e ASCII Art com suporte a cores ANSI.
"""
import numpy as np
import os

# --- SISTEMA DE CORES ---
class Cores:
    RESET = "\033[0m"
    VERMELHO = "\033[91m"
    VERDE = "\033[92m"
    AMARELO = "\033[93m"
    AZUL = "\033[94m"
    MAGENTA = "\033[95m"
    CIANO = "\033[96m"
    CINZA = "\033[90m"
    NEGRITO = "\033[1m"

def cabecalho(texto):
    print(f"\n{Cores.CIANO}{Cores.NEGRITO}=== {texto} ==={Cores.RESET}")

def info(texto):
    print(f"{Cores.AZUL}[i] {texto}{Cores.RESET}")

def sucesso(texto):
    print(f"{Cores.VERDE}[+] {texto}{Cores.RESET}")

def alerta(texto):
    print(f"{Cores.AMARELO}[!] {texto}{Cores.RESET}")

def erro(texto):
    print(f"{Cores.VERMELHO}[x] {texto}{Cores.RESET}")

def desenhar_numero(pixels_flat):
    """Desenha um dígito 8x8 colorido."""
    grid = pixels_flat.reshape(8, 8)
    chars = " .:-=+*#%@"
    
    print(f"   {Cores.CINZA}┌────────┐{Cores.RESET}")
    for i in range(8):
        linha = f"   {Cores.CINZA}│{Cores.RESET}"
        for j in range(8):
            val = grid[i, j]
            idx = int(val * (len(chars) - 1))
            idx = max(0, min(idx, len(chars) - 1))
            
            char = chars[idx]
            
            # Colorir baseado na intensidade
            if val > 0.7: color = Cores.NEGRITO + Cores.BRANCO if hasattr(Cores, 'BRANCO') else Cores.NEGRITO
            elif val > 0.4: color = Cores.CIANO
            elif val > 0.1: color = Cores.AZUL
            else: color = Cores.CINZA
            
            linha += f"{color}{char}{Cores.RESET}"
        print(linha + f"{Cores.CINZA}│{Cores.RESET}")
    print(f"   {Cores.CINZA}└────────┘{Cores.RESET}")

def desenhar_grafico_custo(historico):
    """Barra de progresso colorida."""
    print(f"\n{Cores.MAGENTA}📉 Curva de Aprendizado:{Cores.RESET}")
    if not historico: return
    max_val = max(historico)
    for val in historico:
        barras = int((val / max_val) * 40)
        cor = Cores.VERDE if val < max_val * 0.2 else Cores.AMARELO
        if val > max_val * 0.8: cor = Cores.VERMELHO
        
        print(f"   {val:.4f} | {cor}" + "█" * barras + Cores.RESET)

def desenhar_retina(pesos_array, titulo="Neurônio"):
    """Visualiza pesos positivos (Verde) e negativos (Vermelho)."""
    grid = pesos_array.reshape(8, 8)
    
    print(f"   {Cores.NEGRITO}{titulo}{Cores.RESET}")
    print(f"   {Cores.CINZA}┌────────┐{Cores.RESET}")
    for i in range(8):
        linha = f"   {Cores.CINZA}│{Cores.RESET}"
        for j in range(8):
            val = grid[i, j]
            
            if abs(val) < 0.2:
                char = " "
                cor = Cores.RESET
            elif val > 0: # Excitátorio
                char = "@" if val > 0.5 else "+"
                cor = Cores.VERDE
            else: # Inibitório
                char = "#" if val < -0.5 else "-"
                cor = Cores.VERMELHO
                
            linha += f"{cor}{char}{Cores.RESET}"
        print(linha + f"{Cores.CINZA}│{Cores.RESET}")
    print(f"   {Cores.CINZA}└────────┘{Cores.RESET}")