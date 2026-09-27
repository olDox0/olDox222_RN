# ia_tools/doxoade_atlas_gen.py
import json
import os
import sys

# PASC-8.17: Garante acesso ao Doxoade Core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def gerar_atlas_funcional():
    """Extrai metadados da CLI para o SiCDox (RAG Local)."""
    try:
        from doxoade.cli import cli
    except ImportError:
        print("❌ Falha ao localizar o núcleo do Doxoade.")
        return

    atlas = {}
    # Contexto dummy para o Click não tentar rodar comandos
    ctx = cli.make_context('atlas_gen', [])
    
    for cmd_name, command in cli.commands.items():
        # Captura apenas comandos reais, ignorando grupos vazios
        help_text = command.get_help(ctx)
        # Limpa formatação ANSI para não confundir o LLM
        clean_help = help_text.split("Options:")[0].replace("\x1b", "").strip()
        
        atlas[cmd_name] = {
            "description": clean_help,
            "options": [p.name for p in command.params if hasattr(p, 'name')]
        }
        
    with open("ia_core/doxoade_atlas.json", "w", encoding='utf-8') as f:
        json.dump(atlas, f, indent=4, ensure_ascii=False)
        
    print("🗺️  [OIA] Atlas de Capacidades consolidado em ia_core/doxoade_atlas.json")

if __name__ == "__main__":
    gerar_atlas_funcional()