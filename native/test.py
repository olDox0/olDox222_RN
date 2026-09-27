# native/test.py
import os
import sys
from ctypes import cdll, c_char_p, c_int, create_string_buffer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent

# 1. Adicionar diretórios ao DLL search path
dll_dirs = [
    str(HERE),
    r"C:\winlibs\mingw64\bin",
    str(PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "llama_cpp" / "lib"),
]

print("[1/4] Adicionando diretórios ao DLL search path:")
for path in dll_dirs:
    if os.path.isdir(path):
        os.add_dll_directory(path)
        print(f"  [OK] {path}")

# 2. Carregar dependências na ORDEM CORRETA (CRÍTICO!)
print("\n[2/4] Carregando dependências na ordem correta:")
deps = [
    ("libgcc_s_seh-1.dll",    r"C:\winlibs\mingw64\bin"),
    ("libstdc++-6.dll",       r"C:\winlibs\mingw64\bin"),
    ("libwinpthread-1.dll",   r"C:\winlibs\mingw64\bin"),
    ("ggml-base.dll",         str(PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "llama_cpp" / "lib")),
    ("ggml-cpu.dll",          str(PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "llama_cpp" / "lib")),
    ("ggml.dll",              str(PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "llama_cpp" / "lib")),
    ("libllama.dll",          str(PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "llama_cpp" / "lib")),
]

for dll_name, dll_dir in deps:
    dll_path = os.path.join(dll_dir, dll_name)
    if os.path.exists(dll_path):
        try:
            cdll.LoadLibrary(dll_path)
            print(f"  [OK] {dll_name}")
        except OSError as e:
            print(f"  [ERRO] {dll_name} falhou: {e}")
            sys.exit(1)
    else:
        print(f"  [ERRO] {dll_name} não encontrado em {dll_dir}")
        sys.exit(1)

# 3. Carregar orn.dll
print("\n[3/4] Carregando orn.dll:")
orn_path = str(HERE / "orn.dll")
try:
    lib = cdll.LoadLibrary(orn_path)
    print(f"  [OK] orn.dll carregada com sucesso!")
except OSError as e:
    print(f"  [ERRO] Falha ao carregar: {e}")
    print("  [DICA] Verifique se o winlibs está instalado em C:\\winlibs\\mingw64\\bin")
    sys.exit(1)

lib.orn_init.argtypes = [c_char_p, c_int, c_int]
lib.orn_init.restype = c_int
lib.orn_infer.argtypes = [c_char_p, c_int, c_char_p, c_int]
lib.orn_infer.restype = c_int
lib.orn_free.argtypes = []
lib.orn_free.restype = None

# 4. Inicializar modelo
MODEL = str(PROJECT_ROOT / "models" / "sicdox" / "qwen2.5-coder-0.5b-instruct-q2_k.gguf")
print(f"\n[4/4] Inicializando modelo: {MODEL}")
rc = lib.orn_init(MODEL.encode("utf-8"), 2048, 2)
print(f"  orn_init = {rc}")

if rc != 0:
    print(f"  [ERRO] orn_init falhou com código {rc}")
    sys.exit(1)

# 5. Inferência
prompt = b"Explique recursao em C em 3 linhas."
print(f"\n[INFER] Prompt: {prompt.decode()}")
buf = create_string_buffer(8192)
n = lib.orn_infer(prompt, 512, buf, len(buf))
print(f"  orn_infer = {n} bytes")

if n > 0:
    text = buf.value.decode("utf-8", errors="replace")
    print(f"\n--- Resposta ---\n{text}\n----------------")
elif n == 0:
    print("  [AVISO] Resposta vazia.")
else:
    print(f"  [ERRO] orn_infer falhou com código {n}")

# 6. Cleanup
lib.orn_free()
print("\n[DONE] orn_free() chamado. Teste concluído.")
