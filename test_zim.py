# test_zim.py
import libzim
from pathlib import Path

# Arquivo e conversão para caminho absoluto Posix (C:/Users/...)
zim_path = r"data\zim\softwareengineering.stackexchange.com_en_all_2026-02.zim"
posix_path = Path(zim_path).absolute().as_posix()

print(f"Versão libzim instalada: {libzim.get_libzim_version()}")
print(f"Tentando abrir:\n {posix_path}")

try:
    # A hora da verdade
    archive = libzim.Archive(posix_path)
    print("\n[SUCESSO!] O libzim abriu o arquivo e o Python sobreviveu!")
    print(f"Quantidade de artigos no ZIM: {archive.entry_count}")
except Exception as e:
    print(f"\n[ERRO CAPTURADO]: {e}")