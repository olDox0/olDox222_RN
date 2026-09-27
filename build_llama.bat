@echo off
:: === ORN — Build Vulcan 2.0 (winlibs + N2808) ===

:: 1. Toolchain winlibs (SEM ESPAÇOS no path)
set PATH=C:\winlibs\mingw64\bin;%PATH%

:: 2. Forçar MinGW (não MSVC)
set CMAKE_GENERATOR=MinGW Makefiles
set CC=gcc
set CXX=g++
set FORCE_CMAKE=1

:: 3. Flags para Celeron N2808 (SSE4.2, SEM AVX, SEM OpenMP)
set CMAKE_ARGS=-DGGML_OPENMP=OFF -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF -DGGML_SSE42=ON -DCMAKE_MAKE_PROGRAM=mingw32-make.exe -DCMAKE_C_FLAGS="-O2 -msse4.2 -mfpmath=sse" -DCMAKE_CXX_FLAGS="-O2 -msse4.2 -mfpmath=sse"

:: 4. Instalar cmake/ninja no venv (evita timeout do Temp)
pip install cmake ninja

:: 5. Compilar do zero
pip install llama-cpp-python==0.3.16 --no-cache-dir --force-reinstall --no-binary llama-cpp-python

echo.
echo === Teste de import ===
python -c "from llama_cpp import Llama; print('OK — DLL carregou!')"
