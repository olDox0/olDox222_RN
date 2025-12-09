import os
import sys

def find_root(start):
    curr = os.path.abspath(start)
    print(f"Procurando raiz a partir de: {curr}")
    while True:
        if os.path.exists(os.path.join(curr, 'pyproject.toml')):
            return curr
        if os.path.exists(os.path.join(curr, '.git')):
            return curr
        parent = os.path.dirname(curr)
        if parent == curr: return None
        curr = parent

root = find_root('.')
print(f"Raiz encontrada: {root}")

if root:
    venv = os.path.join(root, 'venv')
    print(f"Venv path esperado: {venv}")
    print(f"Existe? {os.path.exists(venv)}")
    
    if os.name == 'nt':
        exe = os.path.join(venv, 'Scripts', 'python.exe')
    else:
        exe = os.path.join(venv, 'bin', 'python')
        
    print(f"Python executable esperado: {exe}")
    print(f"Existe? {os.path.exists(exe)}")