# doxoade/diagnostic/directory_diagnose.py
import os
from pathlib import Path
from rich.console import Console
from rich.table import Table
from ..dnm import DNM

def auditar_percepcao_espacial(root_path: str):
    """
    Simula a visão do SiCDox sobre a árvore do projeto.
    Valida se a IA consegue cruzar dados entre subpastas.
    """
    console = Console()
    dnm = DNM(root_path)
    
    table = Table(title="🌐 Percepção Espacial SiCDox", border_style="bright_blue")
    table.add_column("Diretório", style="cyan")
    table.add_column("Visibilidade", justify="center")
    table.add_column("Nível de Acesso", justify="center")

    # Mapeia pastas críticas do SiCDox
    pastas_alvo = ['alfagold/core', 'alfagold/experts', 'doxoade/commands', 'tests']
    
    for pasta in pastas_alvo:
        p_abs = Path(root_path) / pasta
        if not p_abs.exists():
            table.add_row(pasta, "[red]AUSENTE[/red]", "N/A")
            continue
            
        # Testa se o DNM (nosso porteiro) permite a visão
        ignorado = dnm.is_ignored(p_abs)
        visibilidade = "[green]TOTAL[/green]" if not ignorado else "[yellow]BLOQUEADO (DNM)[/yellow]"
        
        # Testa permissão de escrita (Para o Agente Ouroboros)
        pode_escrever = os.access(p_abs, os.W_OK)
        acesso = "[green]RW[/green]" if pode_escrever else "[white]R[/white]"
        
        table.add_row(pasta, visibilidade, acesso)

    console.print(table)
    return True