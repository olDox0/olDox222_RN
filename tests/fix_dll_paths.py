# tests/fix_dll_paths.py
"""Diagnóstico e correção de DLL paths para llama-cpp-python."""
import os
import sys
from pathlib import Path

print("="*60)
print(" DIAGNÓSTICO DE DLL PATHS - llama-cpp-python ")
print("="*60)

# Caminhos críticos
PROJECT_ROOT = Path(__file__).resolve().parent.parent
paths_to_check = [
    PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "llama_cpp" / "lib",
    Path(sys.prefix) / "Lib" / "site-packages" / "llama_cpp" / "lib",
    Path(r"C:\winlibs\mingw64\bin"),
]

print("\n[1/3] Verificando caminhos:")
for p in paths_to_check:
    exists = "✓" if p.exists() else "✗"
    print(f"  {exists} {p}")

print("\n[2/3] Verificando DLLs críticas:")
critical_dlls = [
    "libllama.dll",
    "ggml.dll",
    "ggml-base.dll",
    "ggml-cpu.dll",
    "libgcc_s_seh-1.dll",
    "libstdc++-6.dll",
    "libwinpthread-1.dll",
]

lib_dir = paths_to_check[0]
mingw_bin = paths_to_check[2]

for dll in critical_dlls:
    found_in = None
    for search_dir in [lib_dir, mingw_bin]:
        candidate = search_dir / dll
        if candidate.exists():
            found_in = candidate
            break
    status = f"✓ {found_in}" if found_in else "✗ NÃO ENCONTRADA"
    print(f"  {dll:30s} {status}")

print("\n[3/3] Adicionando diretórios ao DLL search path:")
for p in paths_to_check:
    if p.exists() and hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(str(p))
            print(f"  ✓ Adicionado: {p}")
        except Exception as e:
            print(f"  ✗ Falha: {p} - {e}")

print("\n[TESTE] Tentando importar llama_cpp...")
try:
    from llama_cpp import Llama
    print("  ✓ SUCESSO! llama_cpp importado corretamente.")
    print(f"  Versão: {Llama.__module__}")
except Exception as e:
    print(f"  ✗ FALHA: {e}")
    print("\n[DICA] Se o erro mencionar uma DLL específica, copie-a para:")
    print(f"       {lib_dir}")

print("="*60)
