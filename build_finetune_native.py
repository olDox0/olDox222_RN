# -*- coding: utf-8 -*-
# build_finetune_native.py
"""
🔨 METALCRAFT / VULCAN — COMPILADOR DO LLAMA-FINETUNE NATIVO
Compila o motor de treinamento em C/C++ usando a toolchain winlibs.
Flags otimizadas para CPU moderna (AVX2/FMA) e compatíveis com N2808.
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WINLIBS_BIN = Path(r"C:\winlibs\mingw64\bin")
THIRDPARTY_DIR = ROOT / "thirdparty"
LLAMA_SRC = THIRDPARTY_DIR / "llama.cpp"
BUILD_DIR = LLAMA_SRC / "build_finetune"

def check_toolchain():
    print("🔍 [1/4] Verificando toolchain de compilação...")
    gcc = WINLIBS_BIN / "gcc.exe"
    cmake = shutil.which("cmake")
    ninja = shutil.which("ninja")

    if not gcc.exists():
        print(f"❌ GCC winlibs não encontrado em: {WINLIBS_BIN}")
        sys.exit(1)
    if not cmake:
        print("❌ CMake não encontrado no PATH.")
        sys.exit(1)
    print(f"   ✔ GCC: {gcc}")
    print(f"   ✔ CMake: {cmake} | Ninja: {ninja or 'Não (usará MinGW Makefiles)'}")

def ensure_llama_source():
    print("\n📦 [2/4] Verificando código-fonte do llama.cpp...")
    THIRDPARTY_DIR.mkdir(parents=True, exist_ok=True)
    if not LLAMA_SRC.exists():
        print("   ⬇ Clonando llama.cpp (shallow clone)...")
        subprocess.run(
            ["git", "clone", "--depth", "1", "https://github.com/ggerganov/llama.cpp", str(LLAMA_SRC)],
            check=True
        )
    else:
        print("   ✔ Código-fonte do llama.cpp localizado.")

def build_finetune():
    print("\n🔨 [3/4] Configurando CMake e compilando 'llama-finetune'...")
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    # Injeta winlibs no topo do PATH para evitar linkers errados
    env = os.environ.copy()
    env["PATH"] = f"{WINLIBS_BIN};{env.get('PATH', '')}"

    # Flags calibradas: sem HTTP embutido (evita o bug CreateFile2 do Incidente I-007)
    cmake_cmd = [
        "cmake",
        "-S", str(LLAMA_SRC),
        "-B", str(BUILD_DIR),
        "-G", "MinGW Makefiles",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_C_COMPILER=gcc",
        "-DCMAKE_CXX_COMPILER=g++",
        "-DCMAKE_C_FLAGS=-O3 -march=native",
        "-DCMAKE_CXX_FLAGS=-O3 -march=native",
        "-DLLAMA_BUILD_EXAMPLES=ON",
        "-DLLAMA_SERVER_HTTP=OFF",
        "-DLLAMA_SERVER_SSL=OFF",
        "-DGGML_OPENMP=ON",
    ]

    print("   ⚙ Gerando Makefiles...")
    subprocess.run(cmake_cmd, cwd=str(LLAMA_SRC), env=env, check=True)

    print("   🔥 Compilando binário llama-finetune (usando múltiplos núcleos)...")
    build_cmd = [
        "cmake",
        "--build", str(BUILD_DIR),
        "--config", "Release",
        "--target", "llama-finetune",
        "-j", str(os.cpu_count() or 4)
    ]
    subprocess.run(build_cmd, cwd=str(LLAMA_SRC), env=env, check=True)

def verify_binary():
    print("\n🎯 [4/4] Verificando executável gerado...")
    candidates = [
        BUILD_DIR / "bin" / "llama-finetune.exe",
        BUILD_DIR / "bin" / "Release" / "llama-finetune.exe",
        BUILD_DIR / "llama-finetune.exe",
    ]
    exe_found = None
    for cand in candidates:
        if cand.exists():
            exe_found = cand
            break

    if exe_found:
        dest = ROOT / "native" / "llama-finetune.exe"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(exe_found, dest)
        print(f"   ✅ SUCESSO! Binário instalado em: {dest}")
        print(f"   Tamanho: {dest.stat().st_size / (1024*1024):.2f} MB")
    else:
        print("   ❌ Compilação finalizada, mas o executável llama-finetune.exe não foi localizado.")
        sys.exit(1)

if __name__ == "__main__":
    check_toolchain()
    ensure_llama_source()
    build_finetune()
    verify_binary()
