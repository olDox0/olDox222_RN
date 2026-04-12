@echo off
setlocal enabledelayedexpansion

set CC=gcc
set LLAMA_PATH=..\llama.cpp
set LLAMA_LIB_PATH=..\venv\Lib\site-packages\llama_cpp\lib

echo Compilando...

%CC% -O3 -msse4.2 ^
    -I%LLAMA_PATH%\include ^
    -I%LLAMA_PATH%\ggml\include ^
    -I. ^
    -c orn_llama_wrapper.c -o orn_llama_wrapper.o

if errorlevel 1 (
    echo [ERRO] compilacao orn_llama_wrapper.c
    pause
    exit /b 1
)

%CC% -O3 -msse4.2 ^
    -I%LLAMA_PATH%\include ^
    -I%LLAMA_PATH%\ggml\include ^
    -I. ^
    -c orn_optimizer.c -o orn_optimizer.o

if errorlevel 1 (
    echo [ERRO] compilacao orn_optimizer.c
    pause
    exit /b 1
)

%CC% -shared -o orn.dll orn_llama_wrapper.o orn_optimizer.o ^
    -L%LLAMA_LIB_PATH% ^
    -lllama

if errorlevel 1 (
    echo [ERRO] link
    pause
    exit /b 1
)

if exist "%LLAMA_LIB_PATH%\libllama.dll" (
    copy /Y "%LLAMA_LIB_PATH%\libllama.dll" ".\libllama.dll" >nul
)

echo.
echo [OK] orn.dll gerado.
pause