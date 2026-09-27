# find_kv_function.py
# Busca em TODOS os headers do llama.cpp por funções de manipulação de KV-cache
import re
from pathlib import Path

# 1. Encontrar todos os headers do llama.cpp
LLAMA_ROOT = Path("thirdparty/llama.cpp")
if not LLAMA_ROOT.exists():
    print(f"[ERRO] {LLAMA_ROOT} nao encontrado.")
    exit(1)

all_headers = list(LLAMA_ROOT.rglob("*.h"))
print(f"[INFO] Encontrados {len(all_headers)} headers em {LLAMA_ROOT}")

# 2. Buscar TODAS as funções que contêm "kv" no nome
kv_functions = []
for header in all_headers:
    try:
        content = header.read_text(encoding="utf-8", errors="ignore")
        # Regex flexível: busca qualquer função com "kv" no nome
        # Aceita: LLAMA_API void func(...), void func(...), int func(...), etc.
        matches = re.findall(
            r"(?:LLAMA_API\s+)?(?:void|int|bool|size_t|uint32_t)\s+([a-zA-Z_]*kv[a-zA-Z_]*)\s*\(",
            content,
            re.MULTILINE | re.IGNORECASE
        )
        for func_name in matches:
            kv_functions.append((header, func_name))
    except Exception as e:
        pass

# 3. Filtrar apenas funções que manipulam/removem sequências
print(f"\n[INFO] Funções com 'kv' no nome encontradas: {len(kv_functions)}")
rm_functions = [(h, f) for h, f in kv_functions if "rm" in f.lower() or "remove" in f.lower()]

if not rm_functions:
    print("\n[ERRO] Nenhuma função de remoção de KV-cache encontrada.")
    print("\n[INFO] Todas as funções 'kv' encontradas:")
    for header, func in sorted(set(kv_functions), key=lambda x: x[1]):
        print(f"  {func:40s} em {header.relative_to(LLAMA_ROOT)}")
    exit(1)

# 4. Exibir funções candidatas
print(f"\n[OK] Funções de remoção encontradas: {len(rm_functions)}")
for header, func in sorted(set(rm_functions), key=lambda x: x[1]):
    print(f"  {func:40s} em {header.relative_to(LLAMA_ROOT)}")

# 5. Escolher a melhor candidata (heurística: preferir "seq_rm" ou "cache_rm")
best_candidate = None
for header, func in rm_functions:
    if "seq_rm" in func:
        best_candidate = (header, func)
        break
    if "cache_rm" in func and best_candidate is None:
        best_candidate = (header, func)
if best_candidate is None:
    best_candidate = rm_functions[0]

header_path, func_name = best_candidate
print(f"\n[OK] Função selecionada: {func_name}")
print(f"     Arquivo: {header_path.relative_to(LLAMA_ROOT)}")

# 6. Aplicar o patch no wrapper
wrapper = Path("native/orn_llama_wrapper.c")
if not wrapper.exists():
    print(f"[ERRO] {wrapper} nao encontrado.")
    exit(1)

src = wrapper.read_text(encoding="utf-8")
old_func = "llama_kv_self_seq_rm"
if old_func in src:
    src = src.replace(old_func, func_name)
    wrapper.write_text(src, encoding="utf-8")
    print(f"\n[OK] {wrapper} atualizado: '{old_func}' -> '{func_name}'")
else:
    print(f"\n[--] {wrapper} ja esta correto ou nao contem '{old_func}'")

# 7. Adicionar include do header correto se necessário
header_rel = header_path.relative_to(LLAMA_ROOT)
include_line = f'#include "{header_rel.as_posix()}"'
if include_line not in src:
    # Adicionar após #include "llama.h"
    src = src.replace('#include "llama.h"', f'#include "llama.h"\n{include_line}')
    wrapper.write_text(src, encoding="utf-8")
    print(f"[OK] Include adicionado: {include_line}")

print("\n[Agora execute: build_orn_native.bat]")
