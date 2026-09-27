@echo off
:: ORN — Ativacao do ambiente
:: Uso: orn_activate.bat  (executar na raiz do projeto)
:: Adiciona venv\Scripts ao PATH e verifica status do servidor

call .\venv\Scripts\activate.bat
set PATH=.\venv\Scripts;%PATH%

echo [ORN] Ambiente ativo.
echo [ORN] Python: %VIRTUAL_ENV%

:: Verifica servidor
.\venv\Scripts\python.exe -c "from engine.tools.server_client import is_server_online; print('[ORN] Servidor:', 'ONLINE' if is_server_online() else 'offline')" 2>nul || echo [ORN] Servidor: (engine nao carregado ainda)

echo [ORN] Pronto. Use: orn think "sua pergunta"