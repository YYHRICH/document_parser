@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found: .venv\Scripts\python.exe
    echo Please create the virtual environment first.
    pause
    exit /b 1
)

set "HOST=127.0.0.1"
set "PORT=8010"
set "URL=http://%HOST%:%PORT%/"

echo Starting Document Parser frontend at %URL%
start "Document Parser API" "%ComSpec%" /k ""%~dp0.venv\Scripts\python.exe" -m uvicorn document_parser.trigger.http.main:app --app-dir "%~dp0.." --host %HOST% --port %PORT%"

timeout /t 3 /nobreak >nul
start "" "%URL%"

echo Browser opened. Close the "Document Parser API" window to stop the server.
endlocal
