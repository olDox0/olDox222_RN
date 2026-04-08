import os
from ctypes import cdll, c_uint64, c_size_t, c_void_p, POINTER, c_uint8

_lib = None

def _load():
    global _lib
    if _lib is not None:
        return _lib

    dll_path = os.path.join(
        os.path.dirname(__file__),
        "../../native/orn_varint.dll"
    )
    dll_path = os.path.abspath(dll_path)

    if not os.path.exists(dll_path):
        return None

    lib = cdll.LoadLibrary(dll_path)

    lib.orn_encode_varint_u64.argtypes = [
        c_uint64,
        POINTER(c_uint8)
    ]
    lib.orn_encode_varint_u64.restype = c_size_t

    _lib = lib
    return _lib


def encode_varint(buf: bytearray, n: int):
    lib = _load()

    if lib is None:
        # fallback Python
        while n >= 0x80:
            buf.append((n & 0x7F) | 0x80)
            n >>= 7
        buf.append(n)
        return

    # buffer temporário stack-like (10 bytes máximo para u64)
    tmp = (c_uint8 * 10)()
    # A função C continua recebendo (n, tmp) corretamente
    size = lib.orn_encode_varint_u64(n, tmp)

    buf.extend(tmp[:size])