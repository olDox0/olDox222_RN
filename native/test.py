import os
import sys
from ctypes import cdll, c_char_p, c_int, create_string_buffer

HERE = os.path.dirname(__file__)
os.add_dll_directory(HERE)

candidate_lib_dirs = [
    os.path.join(os.path.dirname(HERE), "venv", "Lib", "site-packages", "llama_cpp", "lib"),
    os.path.join(sys.prefix, "Lib", "site-packages", "llama_cpp", "lib"),
]
for path in candidate_lib_dirs:
    if os.path.isdir(path):
        os.add_dll_directory(path)

lib = cdll.LoadLibrary(os.path.join(HERE, "orn.dll"))

lib.orn_init.argtypes = [c_char_p, c_int, c_int]
lib.orn_init.restype = c_int

lib.orn_infer.argtypes = [c_char_p, c_int, c_char_p, c_int]
lib.orn_infer.restype = c_int

lib.orn_free.argtypes = []
lib.orn_free.restype = None

rc = lib.orn_init(
    br"..\models\sicdox\qwen2.5-coder-0.5b-instruct-q2_k.gguf",
    2048,
    2,
)
print("orn_init =", rc)

buf = create_string_buffer(8192)
n = lib.orn_infer(
    b"Explique recursao em C em 3 linhas.",
    512,
    buf,
    len(buf),
)
print("orn_infer =", n)
print(buf.value.decode("utf-8", errors="ignore"))

lib.orn_free()
