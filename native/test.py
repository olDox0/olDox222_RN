import os, sys
from pathlib import Path
from ctypes import cdll, c_char_p, c_int, create_string_buffer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# Caminho absoluto canônico para o modelo
model_path = ROOT / "models" / "sicdox" / "qwen2.5-coder-0.5b-instruct-q2_k.gguf"
#model_path = ROOT / "models" / "smolm_sys" / "smollm2-135m-instruct-q2_k.gguf"

if not model_path.exists():
    print(f"❌ Arquivo não encontrado: {model_path}")
    sys.exit(1)

# Garante visibilidade das DLLs de suporte do venv
candidate_lib_dirs = [
    ROOT / "venv" / "Lib" / "site-packages" / "llama_cpp" / "lib",
    Path(sys.prefix) / "Lib" / "site-packages" / "llama_cpp" / "lib",
]
for p in candidate_lib_dirs:
    if p.is_dir():
        os.add_dll_directory(str(p))

os.add_dll_directory(str(HERE))

dll_file = HERE / "orn.dll"
lib = cdll.LoadLibrary(str(dll_file))

lib.orn_init.argtypes = [c_char_p, c_int, c_int]
lib.orn_init.restype  = c_int
lib.orn_infer.argtypes = [c_char_p, c_int, c_char_p, c_int]
lib.orn_infer.restype  = c_int
lib.orn_free.argtypes  = []
lib.orn_free.restype   = None

print(f"[*] Carregando modelo nativo: {model_path.name}")
rc = lib.orn_init(
    str(model_path).encode("utf-8"),
    2048,
    2,
)
print("orn_init =", rc)

if rc == 0:
    buf = create_string_buffer(8192)
    prompt = b"Explique recursao em C em 3 linhas."
    print(f"[*] Executando inferencia C nativa...")
    n = lib.orn_infer(
        prompt,
        128,
        buf,
        len(buf),
    )
    print("orn_infer =", n)
    print("\n--- RESPOSTA NATIVA ---")
    print(buf.value.decode("utf-8", errors="ignore"))
    print("-----------------------\n")

lib.orn_free()
