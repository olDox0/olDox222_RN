# -*- coding: utf-8 -*-
import os, sys, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WINLIBS_BIN = Path(r"C:\winlibs\mingw64\bin")
THIRDPARTY_DIR = ROOT / "thirdparty"
LLAMA_SRC = THIRDPARTY_DIR / "llama.cpp"
BUILD_DIR = LLAMA_SRC / "build_finetune"

def check_toolchain():
    print("🔍 [1/4] Verificando toolchain de compilação (Metalcraft)...")
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
            ["git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp", str(LLAMA_SRC)],
            check=True
        )
    else: 
        print("   ✔ Código-fonte do llama.cpp localizado.")

def build_finetune():
    print("\n🔨 [3/4] Configurando CMake com perfil ALDER LAKE (AVX2 + FMA + OpenMP)...")
    
    # Limpar build anterior para evitar cache de flags conflitantes
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PATH"] = f"{WINLIBS_BIN};{env.get('PATH', '')}"
    env["CC"] = "gcc"
    env["CXX"] = "g++"

    # ⚠️ CORREÇÃO CRÍTICA:
    # -ffast-math REMOVIDO (quebra o suporte a NaN/Inf do ggml)
    # -fno-finite-math-only ADICIONADO (garante que logit_bias=-inf funcione)
    c_flags = "-O3 -march=native -fopenmp -fno-finite-math-only"
    
    cmake_cmd = [
        "cmake",
        "-S", str(LLAMA_SRC),
        "-B", str(BUILD_DIR),
        "-G", "MinGW Makefiles",
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_C_COMPILER={WINLIBS_BIN / 'gcc.exe'}",
        f"-DCMAKE_CXX_COMPILER={WINLIBS_BIN / 'g++.exe'}",
        f"-DCMAKE_C_FLAGS={c_flags}",
        f"-DCMAKE_CXX_FLAGS={c_flags}",
        "-DLLAMA_BUILD_EXAMPLES=ON",
        "-DLLAMA_SERVER_HTTP=OFF",
        "-DLLAMA_SERVER_SSL=OFF",
        "-DGGML_OPENMP=ON",          # CRUCIAL: Habilita o backend OpenMP do GGML
        "-DGGML_AVX2=ON",            # CRUCIAL: Força AVX2
        "-DGGML_FMA=ON",             # CRUCIAL: Força FMA (Fused Multiply-Add)
        "-DGGML_AVX_VNNI=ON",        # BÔNUS: Alder Lake suporta VNNI para int8
    ]
    
    print("   ⚙ Gerando Makefiles com flags otimizadas...")
    subprocess.run(cmake_cmd, cwd=str(LLAMA_SRC), env=env, check=True)
    
    print("   🔥 Compilando binário llama-finetune (usando múltiplos núcleos)...")
    build_cmd = [
        "cmake",
        "--build", str(BUILD_DIR),
        "--config", "Release",
        "--target", "llama-finetune",
        "-j", str(os.cpu_count() or 10) # Usar todos os cores disponíveis
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
        print(f"   ✅ SUCESSO! Binário Metalcraft instalado em: {dest}")
        print(f"   Tamanho: {dest.stat().st_size / (1024*1024):.2f} MB")
    else:
        print("   ❌ Compilação finalizada, mas o executável llama-finetune.exe não foi localizado.")
        sys.exit(1)

if __name__ == "__main__":
    check_toolchain()
    ensure_llama_source()
    build_finetune()
    verify_binary()
