# engine/native/html_helper.py
import os
import ctypes
from ctypes import cdll, c_char_p, c_size_t

_lib = None

def _load():
    global _lib
    if _lib is not None:
        return _lib

    dll_path = os.path.join(os.path.dirname(__file__), "orn_html.dll")
    dll_path = os.path.abspath(dll_path)

    if not os.path.exists(dll_path):
        return None

    lib = cdll.LoadLibrary(dll_path)
    lib.orn_strip_html.argtypes = [c_char_p, c_size_t, c_char_p]
    lib.orn_strip_html.restype = c_size_t

    _lib = lib
    return _lib

def strip_html_fast(html_bytes: bytes) -> str:
    """Extrai texto do HTML usando a DLL otimizada em C."""
    lib = _load()
    if lib is None or not html_bytes:
        return "" # Fallback handled by caller if needed

    in_len = len(html_bytes)
    # O buffer de saída nunca será maior que o buffer de entrada
    out_buf = ctypes.create_string_buffer(in_len)
    
    out_size = lib.orn_strip_html(html_bytes, in_len, out_buf)
    
    # Retorna decodificando do utf-8
    return out_buf[:out_size].decode("utf-8", errors="replace")