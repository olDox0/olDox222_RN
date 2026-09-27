@echo off
:: ========================================================================
:: ORN - Setup Automatico (One-Click)
:: Cria o venv, ativa e executa a instalacao completa.
:: ========================================================================

echo ============================================================
echo   ORN - Configuracao Automatica do Ambiente
echo   Hardware Alvo: Celeron N2808 (SSE4.2, No-AVX)
echo ============================================================
echo.

:: 1. Criar venv se nao existir
if not exist "venv\Scripts\python.exe" (
    echo [1/4] Criando ambiente virtual (venv)...
    python -m venv venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar o venv. Verifique o Python 3.10+.
        pause
        exit /b 1
    )
)

:: 2. Ativar venv
echo [2/4] Ativando ambiente virtual...
call venv\Scripts\activate.bat

:: 3. Rodar instalacao automatica
echo [3/4] Executando instalacao automatica (pode levar alguns minutos)...
echo.
python install.py --auto

if errorlevel 1 (
    echo.
    echo [ERRO] A instalacao falhou. Verifique os logs acima.
    pause
    exit /b 1
)

:: 4. Verificacao final
echo.
echo [4/4] Verificando instalacao...
python install.py --check

echo.
echo ============================================================
echo   SETUP CONCLUIDO COM SUCESSO!
echo   Para usar o ORN, basta executar:
echo     .\venv\Scripts\activate
echo     orn think "Ola, como voce esta?"
echo ============================================================
pause
