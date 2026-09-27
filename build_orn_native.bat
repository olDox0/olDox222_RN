@echo off
:: ========================================================================
:: ORN - Forja do Backend Nativo (orn.dll) para i5-1235U
:: ========================================================================
echo ============================================================
echo   ORN - Compilando orn.dll (Otimizado para 1235U)
echo ============================================================
echo.

:: 1. Verificar GCC
where gcc >nul 2>nul
if errorlevel 1 (
    echo [ERRO] gcc nao encontrado. Execute: set PATH=C:\winlibs\mingw64\bin;%%PATH%%
    pause
    exit /b 1
)

:: 2. Limpar build anterior
if exist native\orn.dll del native\orn.dll
echo [1/4] orn.dll antigo removido.

:: 3. Verificar dependencias
if not exist "thirdparty\llama.cpp\include\llama.h" (
    echo [ERRO] llama.h nao encontrado em thirdparty\llama.cpp\include
    pause
    exit /b 1
)
if not exist "venv\Lib\site-packages\llama_cpp\lib\libllama.dll.a" (
    echo [ERRO] libllama.dll.a nao encontrado. Execute build_llama_1235u.bat primeiro.
    pause
    exit /b 1
)
echo [2/4] Headers e bibliotecas OK.

:: 4. Compilar com flags MODERNAS
echo.
echo [3/4] Compilando com -march=native, -O3 e -fopenmp...
echo.

gcc -shared -O3 -march=native -fopenmp ^
    -DGGML_USE_CPU ^
    -I"native" ^
    -I"thirdparty\llama.cpp\include" ^
    -I"thirdparty\llama.cpp\ggml\include" ^
    -L"venv\Lib\site-packages\llama_cpp\lib" ^
    -o native\orn.dll ^
    native\orn_llama_wrapper.c ^
    native\orn_optimizer.c ^
    native\orn_varint.c ^
    -lllama -lggml -lggml-base -lggml-cpu -lstdc++ -lm -lgomp

if errorlevel 1 (
    echo.
    echo [ERRO] Compilacao falhou.
    pause
    exit /b 1
)

:: 5. Resultado
for %%A in (native\orn.dll) do set DLL_SIZE=%%~zA
echo.
echo ============================================================
echo   [OK] orn.dll forjado com sucesso!
echo   Tamanho: %DLL_SIZE% bytes
echo   Otimizacoes: march=native (AVX2/FMA), O3, OpenMP
echo ============================================================
echo.
pause
