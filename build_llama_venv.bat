@echo off
:: Verifica se está no venv
where python | findstr /I "venv" >nul
if errorlevel 1 (
    echo [ERRO] Ative o venv primeiro: .\venv\Scripts\activate
    exit /b 1
)

:: Toolchain winlibs
set PATH=C:\winlibs\mingw64\bin;%PATH%
set CMAKE_GENERATOR=MinGW Makefiles
set CC=gcc
set CXX=g++
set FORCE_CMAKE=1

:: Flags para Celeron N2808 (SSE4.2, SEM AVX)
set CMAKE_ARGS=-DGGML_OPENMP=OFF -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF -DGGML_SSE42=ON -DCMAKE_MAKE_PROGRAM=mingw32-make.exe -DCMAKE_C_FLAGS="-O2 -msse4.2 -mfpmath=sse" -DCMAKE_CXX_FLAGS="-O2 -msse4.2 -mfpmath=sse"

pip install cmake ninja
pip install llama-cpp-python==0.3.16 --no-cache-dir --force-reinstall --no-binary llama-cpp-python

echo.
echo === Teste de import ===
python -c "from llama_cpp import Llama; print('OK - DLL carregou!')"
