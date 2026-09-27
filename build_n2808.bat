@echo off
:: === ORN — Build Vulcan 3.0 (N2808 Bulletproof) ===

echo [1/6] Verificando venv...
where python | findstr /I "venv" >nul
if errorlevel 1 (
    echo [ERRO] Ative o venv primeiro: .\venv\Scripts\activate
    pause
    exit /b 1
)

echo [2/6] Limpando instalacoes anteriores e cache...
pip uninstall llama-cpp-python -y
pip cache purge

echo [3/6] Configurando toolchain winlibs e flags N2808 (SEM AVX)...
set PATH=C:\winlibs\mingw64\bin;%PATH%
set CMAKE_GENERATOR=MinGW Makefiles
set CC=gcc
set CXX=g++
set FORCE_CMAKE=1

:: Flags CRITICAS para Celeron N2808 (Silvermont) - Desativa TODAS as extensoes avancadas
set CMAKE_ARGS=-DGGML_NATIVE=OFF -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_AVX512=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF -DGGML_BMI2=OFF -DGGML_LTO=OFF -DGGML_OPENMP=OFF -DGGML_BLAS=OFF -DCMAKE_C_FLAGS="-O2 -msse4.2 -mfpmath=sse" -DCMAKE_CXX_FLAGS="-O2 -msse4.2 -mfpmath=sse"

echo [4/6] Garantindo cmake e ninja...
pip install cmake ninja

echo [5/6] Compilando llama-cpp-python (modo verbose para verificar flags)...
:: O -v no final mostra se o CMake realmente recebeu as flags -DGGML_AVX=OFF
pip install llama-cpp-python==0.3.16 --no-cache-dir --force-reinstall --no-binary llama-cpp-python -v

echo.
echo [6/6] Teste de FOGO: Carregar modelo e gerar 5 tokens...
python -c "from llama_cpp import Llama; print('1. Import OK'); m = Llama(model_path='models/sicdox/qwen2.5-coder-0.5b-instruct-q2_k.gguf', n_ctx=512, n_threads=2, verbose=False); print('2. Load OK'); res = m('Ola', max_tokens=5, echo=False); print('3. Inferencia OK:', res['choices'][0]['text'])"

echo.
echo Se o teste acima funcionou sem 'access violation', o build foi um SUCESSO!
pause
