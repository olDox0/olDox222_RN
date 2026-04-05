@echo off
setlocal

set CC=gcc
set LLAMA_PATH=..\llama.cpp
set LLAMA_LIB_PATH=..\venv\Lib\site-packages\llama_cpp\lib

echo Compilando...

%CC% -O3 -msse4.2 ^
    -I%LLAMA_PATH%\include ^
    -I%LLAMA_PATH%\ggml\include ^
    -I. ^
    -c orn_llama_wrapper.c -o orn.o

if errorlevel 1 (
    echo [ERRO] compilacao
    pause
    exit /b 1
)

%CC% -shared -o orn.dll orn.o ^
    -L%LLAMA_LIB_PATH% ^
    -l:libllama.dll

if errorlevel 1 (
    echo [ERRO] link
    pause
    exit /b 1
)

echo.
echo [OK] orn.dll gerado.
pause