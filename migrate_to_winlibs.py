# migrate_to_winlibs.py
import os
from pathlib import Path

FILES_TO_UPDATE = [
    "README.md",
    "docs/History/vol0_instalação.md",
    "docs/History/vol1_atualizacoes_0200.md",
    "docs/Internals/vol20_infrastructure_report.md",
    "install.py",
    "engine/tools/first_contact.py"
]

DRY_RUN = True  # Mude para False para aplicar as alterações no disco

for file_path in FILES_TO_UPDATE:
    p = Path(file_path)
    if not p.exists():
        print(f"⚠️ Arquivo não encontrado: {file_path}")
        continue
    
    text = p.read_text(encoding="utf-8")
    original_text = text
    
    # Substituições globais
    text = text.replace("w64devkit", "winlibs")
    text = text.replace("w64devkit (Vulcan)", "winlibs (MinGW-w64)")
    text = text.replace(r"C:\...\doxoade\opt\w64devkit\bin", r"C:\winlibs\mingw64\bin")
    text = text.replace(r"C:\Caminho\Para\w64devkit\bin", r"C:\winlibs\mingw64\bin")
    
    # Correção específica e robusta para o install.py
    if "install.py" in file_path:
        old_w64 = r'r"C:\Users\olDox222\Documents\A20251122\DOSSIER\Altonomo\Projetos_E_Programas\Projeto OADE\doxoade\thirdparty\w64devkit\bin"'
        new_winlibs = r'os.environ.get("WINLIBS_BIN", r"C:\winlibs\mingw64\bin")'
        text = text.replace(old_w64, new_winlibs)
        
        # Atualiza comentário de hardware alvo
        text = text.replace("via w64devkit (GCC)", "via winlibs (MinGW-w64)")

    if text != original_text:
        if DRY_RUN:
            print(f"🔍 [DRY-RUN] Mudanças detectadas em: {file_path}")
        else:
            p.write_text(text, encoding="utf-8")
            print(f"✅ Atualizado: {file_path}")
    else:
        print(f"  ✔ Sem alterações necessárias: {file_path}")

if DRY_RUN:
    print("\n💡 Execute o script novamente com DRY_RUN = False para aplicar as mudanças.")
