# doxoade/commands/lab_ast.py
import click
import json
# [DOX-UNUSED] import sys
import os
from colorama import Fore, Style

# Importa a lógica do probe e ferramentas git
from ..probes.ast_diff_lab import analyze_transformation
from ..shared_tools import _run_git_command

def get_git_content(filepath):
    """Recupera o conteúdo do arquivo no HEAD (último commit)."""
    # Normaliza caminho para o Git
    rel_path = os.path.relpath(filepath, os.getcwd()).replace('\\', '/')
    return _run_git_command(['show', f'HEAD:{rel_path}'], capture_output=True, silent_fail=True)

@click.command('lab-ast')
@click.argument('target', type=click.Path(exists=True))
@click.argument('reference', type=click.Path(exists=True), required=False)
def lab_ast(target, reference):
    """
    Analisa transformação estrutural (AST Diff).
    
    Uso:
      doxoade lab-ast arquivo.py           (Compara Disco vs Git HEAD)
      doxoade lab-ast velho.py novo.py     (Comparação explícita)
    """
    click.echo(Fore.CYAN + "--- [LAB-AST] Análise Estrutural V2 ---")
    
    # Modo 1: Comparação Explícita (Dois arquivos)
    if reference:
        file_old_path = target
        file_new_path = reference
        click.echo("   > Modo: Comparação de Arquivos")
        click.echo(f"   > Base: {file_old_path}")
        click.echo(f"   > Alvo: {file_new_path}")
        
        with open(file_old_path, 'r', encoding='utf-8') as f: code_old = f.read()
        with open(file_new_path, 'r', encoding='utf-8') as f: code_new = f.read()

    # Modo 2: Comparação Git (Arquivo vs HEAD)
    else:
        file_new_path = target
        click.echo("   > Modo: Integração Git (Worktree vs HEAD)")
        click.echo(f"   > Alvo: {file_new_path}")
        
        with open(file_new_path, 'r', encoding='utf-8') as f: code_new = f.read()
        
        code_old = get_git_content(file_new_path)
        
        if code_old is None:
            click.echo(Fore.RED + "[ERRO] Arquivo não encontrado no histórico Git (é um arquivo novo?).")
            return
        
        if code_old.strip() == code_new.strip():
            click.echo(Fore.YELLOW + "[AVISO] Nenhuma alteração detectada em relação ao Git.")
            return

    # Executa a Análise
    try:
        result = analyze_transformation(code_old, code_new)
        
        if result.get('confidence', 0) > 0:
            click.echo(Fore.GREEN + "\n[SUCESSO] Transformação Semântica Detectada:")
            
            # Formatação bonita para humanos
            action = result.get('action')
            wrapper = result.get('wrapper')
            
            if action == 'WRAP':
                click.echo(f"   Tipo:   {Style.BRIGHT}ENVELOPAMENTO (Wrap){Style.RESET_ALL}")
                click.echo(f"   Molde:  {wrapper}")
                if 'handlers' in result:
                    click.echo(f"   Trata:  {', '.join(result['handlers'])}")
                if 'condition' in result:
                    click.echo(f"   Lógica: {result['condition']}")
            
            click.echo(Style.DIM + "\nJSON Bruto:")
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(Fore.YELLOW + "\n[NEUTRO] Mudança detectada, mas sem padrão estrutural conhecido.")
            click.echo("(O Gênese vê linhas diferentes, mas a árvore sintática não casou com templates conhecidos)")
            
    except Exception as e:
        click.echo(Fore.RED + f"[ERRO] Falha na análise AST: {e}")
