import os
from ctypes import cdll, c_char_p, c_int, create_string_buffer

os.add_dll_directory(os.path.dirname(__file__))

lib = cdll.LoadLibrary(os.path.join(os.path.dirname(__file__), "orn.dll"))

lib.orn_init.argtypes = [c_char_p, c_int, c_int]
lib.orn_init.restype = c_int

lib.orn_infer.argtypes = [c_char_p, c_int, c_char_p, c_int]
lib.orn_infer.restype = c_int

lib.orn_free.argtypes = []
lib.orn_free.restype = None

rc = lib.orn_init(
    br"..\models\sicdox\Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF\qwen2.5-coder-0.5b-instruct-q4_k_m.gguf",
    256,
    2,
)
print("orn_init =", rc)

buf = create_string_buffer(8192)
n = lib.orn_infer(
    b"Explique recursao em C em 3 linhas.",
    64,
    buf,
    len(buf),
)
print("orn_infer =", n)
print(buf.value.decode("utf-8", errors="ignore"))

lib.orn_free()