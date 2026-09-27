@echo off
:: ========================================================================
:: ORN - Recompilação do llama-cpp-python para Intel i5-1235U
:: Hardware: 10 Cores, AVX2, AVX-VNNI, FMA, OpenMP
:: ========================================================================
echo ============================================================
echo   ORN - Recompilando llama-cpp-python (Modo 1235U)
echo ============================================================
echo.

:: 1. Verificar venv
where python | findstr /I "venv" >nul
if errorlevel 1 (
    echo [ERRO] Ative o venv primeiro: .\venv\Scripts\activate
    pause
    exit /b 1
)

:: 2. Limpar instalações anteriores
echo [1/3] Limpando instalacoes anteriores...
pip uninstall llama-cpp-python -y
pip cache purge

:: 3. Configurar flags para i5-1235U
echo [2/3] Configurando flags de otimizacao (AVX2, FMA, OpenMP)...
set PATH=C:\winlibs\mingw64\bin;%PATH%
set CMAKE_GENERATOR=MinGW Makefiles
set CC=gcc
set CXX=g++
set FORCE_CMAKE=1

:: NATIVE=ON ativa automaticamente AVX, AVX2, FMA e as instrucoes especificas do Alder Lake
:: OPENMP=ON permite usar os 10 nucleos do 1235U
set CMAKE_ARGS=-DGGML_NATIVE=ON -DGGML_OPENMP=ON -DGGML_BLAS=OFF -DGGML_LTO=ON

:: 4. Compilar
echo [3/3] Compilando (isso pode levar 2-5 minutos)...
pip install llama-cpp-python==0.3.16 --no-cache-dir --force-reinstall --no-binary llama-cpp-python

if errorlevel 1 (
    echo.
    echo [ERRO] Falha na compilacao.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   [OK] llama-cpp-python recompilado com sucesso!
echo   Otimizacoes: NATIVE (AVX2/FMA), OpenMP, LTO
echo ============================================================
pause
