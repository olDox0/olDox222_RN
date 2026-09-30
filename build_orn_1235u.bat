@echo off
:: ========================================================================
:: ORN - Forja do Backend Nativo (orn.dll) para i5-1235U
:: Headers casados com a libllama.dll do venv (elimina WinError 127)
:: ========================================================================
echo ============================================================
echo   ORN - Compilando orn.dll (Otimizado para 1235U)
echo ============================================================
echo.

:: 1. PATH do winlibs
set PATH=C:\winlibs\mingw64\bin;%PATH%
where gcc >nul 2>nul
if errorlevel 1 (
    echo [ERRO] gcc nao encontrado.
    pause
    exit /b 1
)
echo [OK] GCC encontrado.

:: 2. Limpar build anterior
if exist native\orn.dll del native\orn.dll
echo [1/4] orn.dll antigo removido.

:: 3. Caminhos (headers do PIP = mesma versao da libllama.dll)
set "PROJECT_DIR=%~dp0"
set "LLAMA_INC=%PROJECT_DIR%venv\Lib\site-packages\llama_cpp\include"
set "LLAMA_LIB=%PROJECT_DIR%venv\Lib\site-packages\llama_cpp\lib"

if not exist "%LLAMA_INC%\llama.h" (
    echo [ERRO] llama.h nao encontrado em %LLAMA_INC%
    pause
    exit /b 1
)
if not exist "%LLAMA_LIB%\libllama.dll.a" (
    echo [ERRO] libllama.dll.a nao encontrado.
    pause
    exit /b 1
)
echo [2/4] Headers e bibliotecas OK (versao casada com o venv).

:: 4. Compilar (SEM .def - exports via __declspec(dllexport))
echo.
echo [3/4] Compilando com -march=native -O3 -fopenmp...
echo.

gcc -shared -O3 -march=native -fopenmp ^
    -DGGML_USE_CPU ^
    -I"%PROJECT_DIR%native" ^
    -I"%LLAMA_INC%" ^
    -o native\orn.dll ^
    native\orn_llama_wrapper.c ^
    native\orn_optimizer.c ^
    native\orn_varint.c ^
    "%LLAMA_LIB%\libllama.dll.a" ^
    "%LLAMA_LIB%\libggml.dll.a" ^
    "%LLAMA_LIB%\libggml-base.dll.a" ^
    "%LLAMA_LIB%\libggml-cpu.dll.a" ^
    -lstdc++ -lm -lgomp

if errorlevel 1 (
    echo.
    echo [ERRO] Compilacao falhou.
    pause
    exit /b 1
)

:: 5. Verificar exports (deve listar orn_init, orn_infer, etc.)
echo.
echo [4/4] Verificando tabela de exportacao:
objdump -p native\orn.dll | findstr "orn_"
if errorlevel 1 (
    echo [AVISO] Nenhum export encontrado! Verifique ORN_API no .c/.h
    pause
    exit /b 1
)

for %%A in (native\orn.dll) do set DLL_SIZE=%%~zA
echo.
echo ============================================================
echo   [OK] orn.dll forjado com sucesso! (%DLL_SIZE% bytes)
echo ============================================================
echo.
pause
