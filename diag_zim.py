# -*- coding: utf-8 -*-
"""
ORN — Diagnóstico libzim
Execute: python diag_zim.py data\zim\wikipedia_pt_computer_maxi_2026-01.zim
"""
import sys
import traceback

zim_path = sys.argv[1] if len(sys.argv) > 1 else r"data/zim/wikipedia_pt_computer_maxi_2026-01.zim"

print(f"\n=== LIBZIM DIAGNÓSTICO ===")
print(f"ZIM: {zim_path}\n")

# --- 1. Versão do pacote ---
try:
    import importlib.metadata
    ver = importlib.metadata.version("libzim")
    print(f"[1] libzim versão: {ver}")
except Exception as e:
    print(f"[1] versão: ERRO — {e}")

# --- 2. Importação ---
try:
    import libzim
    print(f"[2] import libzim: OK")
    print(f"    atributos do módulo: {[a for a in dir(libzim) if not a.startswith('_')]}")
except Exception as e:
    print(f"[2] import libzim: FALHOU — {e}")
    sys.exit(1)

# --- 3. Abrir Archive ---
try:
    archive = libzim.Archive(zim_path)
    print(f"\n[3] Archive aberto: OK")
except Exception as e:
    print(f"[3] Archive: FALHOU — {e}")
    traceback.print_exc()
    sys.exit(1)

# --- 4. Todos os atributos do Archive ---
print(f"\n[4] Atributos do Archive:")
for attr in sorted(dir(archive)):
    if attr.startswith("__"):
        continue
    try:
        val = getattr(archive, attr)
        if callable(val):
            print(f"    {attr}: <method>")
        else:
            print(f"    {attr}: {repr(val)[:120]}")
    except Exception as e:
        print(f"    {attr}: ERRO ao ler — {e}")

# --- 5. Tentar obter contagem de entradas ---
print(f"\n[5] Tentativas de contagem:")
count_attrs = [
    "entry_count", "_entry_count", "article_count", "_article_count",
    "all_entry_count", "size",
]
for attr in count_attrs:
    val = getattr(archive, attr, "NÃO EXISTE")
    print(f"    archive.{attr} = {val}")

# --- 6. Tentar iterar diretamente ---
print(f"\n[6] Tentando get_entry_by_id(0):")
try:
    entry = archive.get_entry_by_id(0)
    print(f"    entry[0]: OK")
    print(f"    atributos da entry: {[a for a in dir(entry) if not a.startswith('__')]}")
    for attr in ["title", "path", "is_redirect", "is_article"]:
        try:
            print(f"    entry.{attr} = {repr(getattr(entry, attr, 'N/A'))[:80]}")
        except Exception as e:
            print(f"    entry.{attr}: ERRO — {e}")
except Exception as e:
    print(f"    FALHOU: {e}")
    traceback.print_exc()

# --- 7. Tentar __iter__ ---
print(f"\n[7] Tentando iter(archive):")
try:
    it = iter(archive)
    first = next(it)
    print(f"    iter OK: {type(first)} — {repr(first)[:80]}")
except Exception as e:
    print(f"    iter: {e}")

# --- 8. Verificar arquivo ZIM ---
import os
size = os.path.getsize(zim_path)
print(f"\n[8] Tamanho do arquivo: {size:,} bytes ({size/1024/1024:.1f} MB)")

print(f"\n=== FIM DO DIAGNÓSTICO ===\n")
print("Cole o output completo acima.")