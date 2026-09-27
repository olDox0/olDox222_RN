# -*- coding: utf-8 -*-
# fix_httplib_createfile2.py
"""
ORN — fix_httplib_createfile2.py
Corrige o erro de compilação do cpp-httplib no MinGW.
O CreateFile2 não está disponível no MinGW padrão.
Solução: Forçar uso do CreateFileW (compatível com Windows 7+).

Uso:
    python fix_httplib_createfile2.py
    
Este script deve ser executado ANTES do pip install,
enquanto o código fonte ainda está no diretório temporário.
"""
import os
import re
import sys
from pathlib import Path


def find_and_fix_httplib() -> bool:
    """Procura e corrige httplib.cpp em diretórios temporários do pip."""
    temp_dir = Path(os.environ.get("TEMP", os.environ.get("TMP", r"C:\Temp")))
    
    print(f"🔍 Procurando httplib.cpp em: {temp_dir}")
    
    fixed_count = 0
    for httplib_file in temp_dir.rglob("httplib.cpp"):
        if "cpp-httplib" not in str(httplib_file):
            continue
            
        print(f"🔧 Corrigindo: {httplib_file}")
        
        try:
            content = httplib_file.read_text(encoding="utf-8", errors="ignore")
            
            if "::CreateFile2" not in content:
                print(f"  ⏭️  CreateFile2 não encontrado, pulando")
                continue
            
            # Substitui CreateFile2 por CreateFileW
            # CreateFile2(filename, access, share, creation, attrs, template)
            # CreateFileW(filename, access, share, security, creation, attrs, template)
            content = re.sub(
                r"::CreateFile2\(\s*wpath\.c_str\(\)\s*,\s*GENERIC_READ\s*,\s*FILE_SHARE_READ\s*,\s*OPEN_EXISTING\s*,\s*FILE_ATTRIBUTE_NORMAL\s*\)",
                "::CreateFileW(wpath.c_str(), GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL)",
                content
            )
            
            httplib_file.write_text(content, encoding="utf-8")
            print(f"  ✅ Corrigido com sucesso")
            fixed_count += 1
            
        except Exception as e:
            print(f"  ❌ Erro ao processar: {e}")
    
    if fixed_count == 0:
        print("\n⚠️  Nenhum httplib.cpp encontrado. Execute este script DURANTE o pip install.")
        print("   Dica: Inicie o pip install em outro terminal e execute este script")
        print("   enquanto a compilação estiver em andamento.")
        return False
    
    print(f"\n✅ {fixed_count} arquivo(s) corrigido(s)")
    return True


if __name__ == "__main__":
    success = find_and_fix_httplib()
    sys.exit(0 if success else 1)
