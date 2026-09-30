import os
os.add_dll_directory(r"C:\winlibs\mingw64\bin")
os.add_dll_directory(r"C:\Users\Victor Alexandre\Documents\ORN_proj\venv\Lib\site-packages\llama_cpp\lib")

import ctypes
lib = ctypes.CDLL(r"C:\Users\Victor Alexandre\Documents\ORN_proj\native\orn.dll")
print("orn_init:", lib.orn_init)

