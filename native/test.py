import os
import sys
from ctypes import cdll, c_char_p, c_int, create_string_buffer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent

# 1. Adicionar diretórios ao DLL search path (CRÍTICO)
dll_dirs = [
    str(HERE),
    r"C:\winlibs\mingw64\bin",  # Runtime do C++ (GCC)
    str(PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "llama_cpp" / "lib"),
    str(Path(sys.prefix) / "Lib" / "site-packages" / "llama_cpp" / "lib"),
]

print("[1/4] Adicionando diretórios ao DLL search path:")
for path in dll_dirs:
    if os.path.isdir(path) and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(path)
        print(f"  [OK] {path}")

# 2. Carregar a DLL
dll_path = str(HERE / "orn.dll")
print(f"\n[2/4] Carregando: {dll_path}")
try:
    lib = cdll.LoadLibrary(dll_path)
    print("  [OK] orn.dll carregada com sucesso!\n")
except OSError as e:
    print(f"  [ERRO] Falha ao carregar: {e}")
    sys.exit(1)

lib.orn_init.argtypes = [c_char_p, c_int, c_int]
lib.orn_init.restype = c_int
lib.orn_infer.argtypes = [c_char_p, c_int, c_char_p, c_int]
lib.orn_infer.restype = c_int
lib.orn_free.argtypes = []
lib.orn_free.restype = None

# 3. Inicializar modelo
MODEL = str(PROJECT_ROOT / "models" / "sicdox" / "qwen2.5-coder-0.5b-instruct-q2_k.gguf")
print(f"[3/4] Inicializando modelo: {MODEL}")
rc = lib.orn_init(MODEL.encode("utf-8"), 2048, 10)  # 10 threads para 1235U
print(f"  orn_init = {rc}")

if rc != 0:
    print(f"  [ERRO] orn_init falhou com codigo {rc}")
    sys.exit(1)

# 4. Inferência
prompt = b"Explique recursao em C em 3 linhas."
print(f"\n[4/4] [INFER] Prompt: {prompt.decode()}")
buf = create_string_buffer(8192)
n = lib.orn_infer(prompt, 512, buf, len(buf))
print(f"  orn_infer = {n} bytes")

if n > 0:
    text = buf.value.decode("utf-8", errors="replace")
    print(f"\n--- Resposta ---\n{text}\n----------------")
elif n == 0:
    print("  [AVISO] Resposta vazia.")
else:
    print(f"  [ERRO] orn_infer falhou com codigo {n}")

# 5. Cleanup
lib.orn_free()
print("\n[DONE] orn_free() chamado. Teste concluído.")
