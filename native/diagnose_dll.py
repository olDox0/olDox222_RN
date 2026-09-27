# native/diagnose_dll.py# native/diagnose_dll.py
"""Diagnóstico de DLLs do orn.dll — identifica dependências faltando."""
import os
import sys
from pathlib import Path
from ctypes import cdll, WinError

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent

# 1. Adicionar TODOS os diretórios possíveis ao DLL search path
dll_dirs = [
    HERE,                                                          # native/ (orn.dll)
    PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "llama_cpp" / "lib",
    Path(sys.prefix) / "Lib" / "site-packages" / "llama_cpp" / "lib",
    PROJECT_ROOT / "venv" / "Scripts",
    Path(sys.prefix) / "Scripts",
]

print("[1/4] Adicionando diretórios ao DLL search path:")
for d in dll_dirs:
    if d.exists():
        print(f"  ✓ {d}")
        os.add_dll_directory(str(d))
    else:
        print(f"  ✗ {d} (não existe)")

# 2. Listar DLLs esperadas
expected_dlls = [
    "libllama.dll",
    "ggml.dll",
    "ggml-base.dll",
    "ggml-cpu.dll",
    "libgcc_s_seh-1.dll",
    "libstdc++-6.dll",
    "libwinpthread-1.dll",
]

print("\n[2/4] Verificando DLLs dependentes:")
lib_dir = PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "llama_cpp" / "lib"
mingw_bin = Path(r"C:\winlibs\mingw64\bin")

for dll_name in expected_dlls:
    found_in = None
    for search_dir in [lib_dir, mingw_bin, HERE]:
        candidate = search_dir / dll_name
        if candidate.exists():
            found_in = candidate
            break
    status = f"✓ {found_in}" if found_in else "✗ NÃO ENCONTRADA"
    print(f"  {dll_name:30s} {status}")

# 3. Tentar carregar cada DLL individualmente
print("\n[3/4] Testando carregamento individual:")
for dll_name in ["libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll"]:
    for search_dir in [mingw_bin, lib_dir]:
        candidate = search_dir / dll_name
        if candidate.exists():
            try:
                cdll.LoadLibrary(str(candidate))
                print(f"  ✓ {dll_name} carregada de {search_dir}")
                break
            except OSError as e:
                print(f"  ✗ {dll_name} falhou: {e}")

for dll_name in ["ggml-base.dll", "ggml-cpu.dll", "ggml.dll", "libllama.dll"]:
    candidate = lib_dir / dll_name
    if candidate.exists():
        try:
            cdll.LoadLibrary(str(candidate))
            print(f"  ✓ {dll_name} carregada")
        except OSError as e:
            print(f"  ✗ {dll_name} falhou: {e}")
    else:
        print(f"  ✗ {dll_name} não existe em {lib_dir}")

# 4. Finalmente, tentar carregar orn.dll
print("\n[4/4] Carregando orn.dll:")
orn_path = HERE / "orn.dll"
print(f"  Caminho: {orn_path}")
print(f"  Existe: {orn_path.exists()}")
print(f"  Tamanho: {orn_path.stat().st_size if orn_path.exists() else 'N/A'} bytes")

try:
    lib = cdll.LoadLibrary(str(orn_path))
    print(f"  ✓ orn.dll carregada com sucesso!")
    print(f"  orn_init: {lib.orn_init}")
    print(f"  orn_infer: {lib.orn_infer}")
except OSError as e:
    print(f"  ✗ FALHA: {e}")
    print("\n[DICA] Se o erro mencionar uma DLL específica, adicione o diretório")
    print("       dela ao PATH do sistema ou copie-a para native/")
