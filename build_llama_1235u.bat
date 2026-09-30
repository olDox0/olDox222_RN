@echo off
:: ========================================================================
:: ORN - Forja do Backend Nativo (orn.dll) para i5-1235U
:: Hardware: Intel Core i5-1235U (AVX2, FMA, OpenMP, 10 Cores)
:: ========================================================================
echo ============================================================
echo   ORN - Compilando orn.dll (Otimizado para 1235U)
echo ============================================================
echo.

:: 1. FORCAR PATH do winlibs internamente
set PATH=C:\winlibs\mingw64\bin;%PATH%

:: 2. Verificar GCC
where gcc >nul 2>nul
if errorlevel 1 (
    echo [ERRO] gcc nao encontrado no PATH.
    pause
    exit /b 1
)
echo [OK] GCC encontrado:
gcc --version | findstr "gcc.exe"

:: 3. Limpar build anterior
if exist native\orn.dll del native\orn.dll
echo [1/4] orn.dll antigo removido.

:: 4. Definir caminhos absolutos
set "PROJECT_DIR=%~dp0"
set "LLAMA_LIB_DIR=%PROJECT_DIR%venv\Lib\site-packages\llama_cpp\lib"

if not exist "%LLAMA_LIB_DIR%\libllama.dll.a" (
    echo [ERRO] libllama.dll.a nao encontrado.
    pause
    exit /b 1
)
echo [2/4] Headers e bibliotecas OK.

:: 5. Compilar com flags MODERNAS (SEM .def)
echo.
echo [3/4] Compilando com -march=native, -O3 e -fopenmp...
echo.

set "LIB_LLAMA=%LLAMA_LIB_DIR%\libllama.dll.a"
set "LIB_GGML=%LLAMA_LIB_DIR%\libggml.dll.a"
set "LIB_GGML_BASE=%LLAMA_LIB_DIR%\libggml-base.dll.a"
set "LIB_GGML_CPU=%LLAMA_LIB_DIR%\libggml-cpu.dll.a"

gcc -shared -O3 -march=native -fopenmp ^
    -DGGML_USE_CPU ^
    -I"%PROJECT_DIR%native" ^
    -I"%PROJECT_DIR%thirdparty\llama.cpp\include" ^
    -I"%PROJECT_DIR%thirdparty\llama.cpp\ggml\include" ^
    -o native\orn.dll ^
    native\orn_llama_wrapper.c ^
    native\orn_optimizer.c ^
    native\orn_varint.c ^
    "%LIB_LLAMA%" "%LIB_GGML%" "%LIB_GGML_BASE%" "%LIB_GGML_CPU%" -lstdc++ -lm -lgomp

if errorlevel 1 (
    echo.
    echo [ERRO] Compilacao falhou.
    pause
    exit /b 1
)

:: 6. Resultado
for %%A in (native\orn.dll) do set DLL_SIZE=%%~zA
echo.
echo ============================================================
echo   [OK] orn.dll forjado com sucesso!
echo   Tamanho: %DLL_SIZE% bytes
echo   Otimizacoes: march=native (AVX2/FMA), O3, OpenMP
echo ============================================================
echo.
pause
