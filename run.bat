@echo off
REM Atalho para rodar o bot no Windows.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Ambiente virtual nao encontrado. Crie com:
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo Iniciando a agenda no Telegram... (Ctrl+C para parar)
".venv\Scripts\python.exe" -m app.main
pause
