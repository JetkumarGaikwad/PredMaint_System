@echo off
echo ==============================================
echo Starting PredMaint System Servers
echo ==============================================

:: 1. Start Backend Server in a new window
echo Starting Backend Server...
start "PredMaint Backend" cmd /k "cd /d %~dp0backend & if not exist venv (echo Creating virtual environment... && python -m venv venv) & call venv\Scripts\activate.bat & if not exist venv\Scripts\uvicorn.exe (echo Installing dependencies... && pip install -r requirements.txt) & echo Starting FastAPI... && uvicorn main:app --port 8000"



:: 2. Start Frontend Server in a new window
echo Starting Frontend Server...
start "PredMaint Frontend" cmd /k "cd /d %~dp0frontend && echo Starting Vite Dev Server... && npm run dev"


echo Both servers have been launched in separate windows.
echo Please leave them running while performing verification.
pause
