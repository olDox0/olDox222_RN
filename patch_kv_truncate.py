# patch_kv_truncate.py
# Detecta automaticamente o nome correto da função de KV-cache truncation
# no llama.h instalado e aplica o patch no orn_llama_wrapper.c

import re
from pathlib import Path

# 1. Encontrar o llama.h
LLAMA_H_CANDIDATES = [
    Path("thirdparty/llama.cpp/include/llama.h"),
    Path("venv/Lib/site-packages/llama_cpp/include/llama.h"),
]

llama_h = None
for p in LLAMA_H_CANDIDATES:
    if p.exists():
        llama_h = p
        break

if llama_h is None:
    print("[ERRO] llama.h nao encontrado.")
    exit(1)

print(f"[OK] Usando: {llama_h}")

# 2. Procurar TODAS as funcoes de KV-cache no header
content = llama_h.read_text(encoding="utf-8", errors="ignore")
kv_funcs = re.findall(r"^\s*(LLAMA_API\s+)?(?:void|int|bool|size_t)\s+(llama_kv\w+)\s*\(", content, re.MULTILINE)

print(f"\n[INFO] Funcoes de KV-cache encontradas no llama.h:")
kv_names = sorted(set(name for _, name in kv_funcs))
for i, name in enumerate(kv_names, 1):
    print(f"  {i:2d}. {name}")

# 3. Escolher a funcao certa (heuristica: procurar por "seq_rm" ou "rm")
candidate = None
for name in kv_names:
    if "seq_rm" in name and "self" in name:
        candidate = name
        break
if candidate is None:
    for name in kv_names:
        if "seq_rm" in name:
            candidate = name
            break
if candidate is None:
    for name in kv_names:
        if "rm" in name and "seq" in name:
            candidate = name
            break

if candidate is None:
    print("\n[ERRO] Nenhuma funcao de remocao de sequencia encontrada.")
    print("       Escolha manualmente na lista acima e edite orn_llama_wrapper.c.")
    exit(1)

print(f"\n[OK] Funcao selecionada: {candidate}")

# 4. Aplicar o patch no wrapper
wrapper = Path("native/orn_llama_wrapper.c")
if not wrapper.exists():
    print(f"[ERRO] {wrapper} nao encontrado.")
    exit(1)

src = wrapper.read_text(encoding="utf-8")

# Substituir qualquer chamada antiga de kv_truncate
patterns_to_replace = [
    "llama_kv_self_seq_rm",
    "llama_kv_cache_seq_rm",
    "llama_kv_self_cache_seq_rm",
]

replaced = False
for old in patterns_to_replace:
    if old in src and old != candidate:
        src = src.replace(old, candidate)
        replaced = True
        print(f"[FIX] Substituido '{old}' por '{candidate}'")

# Se a funcao orn_kv_truncate nao existe ainda, adicionar
if "void orn_kv_truncate" not in src:
    impl = f"""
void orn_kv_truncate(int keep_tokens)
{{
    if (!g_ctx || keep_tokens < 0) return;
    {candidate}(g_ctx, 0, keep_tokens, -1);
}}

"""
    # Inserir antes de orn_infer
    if "int orn_infer(" in src:
        src = src.replace("int orn_infer(", impl + "int orn_infer(", 1)
        replaced = True
        print(f"[FIX] Funcao orn_kv_truncate adicionada com {candidate}")

if replaced:
    wrapper.write_text(src, encoding="utf-8")
    print(f"\n[OK] {wrapper} atualizado.")
else:
    print(f"\n[--] {wrapper} ja esta correto.")

print("\n[Agora execute: build_orn_native.bat]")
