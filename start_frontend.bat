@echo off
setlocal EnableExtensions

cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"
for %%I in ("%PROJECT_ROOT%\..") do set "PROJECT_PARENT=%%~fI"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "HOST=127.0.0.1"
if "%DOCUMENT_PARSER_PORT%"=="" set "DOCUMENT_PARSER_PORT=8011"
if "%FRONTEND_PORT%"=="" set "FRONTEND_PORT=5174"
set "BACKEND_URL=http://%HOST%:%DOCUMENT_PARSER_PORT%/"
set "HEALTH_URL=%BACKEND_URL%api/health"
set "FRONTEND_URL=http://%HOST%:%FRONTEND_PORT%/"
if "%VITE_DEV_API_ORIGIN%"=="" set "VITE_DEV_API_ORIGIN=http://%HOST%:%DOCUMENT_PARSER_PORT%"

rem Include both source roots so the backend works before an editable install.
set "PYTHONPATH=%PROJECT_ROOT%;%PROJECT_PARENT%;%PYTHONPATH%"

rem Load local runtime settings. Existing process variables take precedence;
rem support the repository's legacy MINERU_API_KEY name as well.
if exist "%PROJECT_ROOT%\.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%PROJECT_ROOT%\.env") do (
        if not "%%A"=="" if not defined %%A set "%%A=%%B"
    )
)
if defined DOCUMENT_PARSER_ALLOW_CLOUD set "DOCUMENT_PARSER_ALLOW_CLOUD=%DOCUMENT_PARSER_ALLOW_CLOUD:"=%"
if not defined MINERU_API_TOKEN if defined MINERU_API_KEY set "MINERU_API_TOKEN=%MINERU_API_KEY%"
if defined MINERU_API_TOKEN set "MINERU_API_TOKEN=%MINERU_API_TOKEN:"=%"

if not exist "%PYTHON%" (
    echo [ERROR] Virtual environment not found: %PYTHON%
    pause
    exit /b 1
)
if not exist "%PROJECT_ROOT%\frontend\package.json" (
    echo [ERROR] Frontend package manifest not found.
    pause
    exit /b 1
)
if not exist "%PROJECT_ROOT%\frontend\node_modules\.bin\vite.cmd" (
    echo [ERROR] Frontend dependencies are not installed.
    echo Run: cd frontend ^&^& npm install
    pause
    exit /b 1
)

"%PYTHON%" -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Uvicorn is not installed in .venv.
    echo Run: .venv\Scripts\python.exe -m pip install -e .[server]
    pause
    exit /b 1
)

rem Start the API only when it is not already healthy.
powershell -NoProfile -Command "$ErrorActionPreference = 'Stop'; $response = Invoke-WebRequest -UseBasicParsing -Uri '%HEALTH_URL%' -TimeoutSec 2; if ($response.StatusCode -eq 200 -and (($response.Content | ConvertFrom-Json).status -eq 'ok')) { exit 0 }; exit 1" >nul 2>&1
if errorlevel 1 (
    netstat -ano | findstr /R /C:":%DOCUMENT_PARSER_PORT% .*LISTENING" >nul
    if not errorlevel 1 (
        echo [ERROR] Backend port %DOCUMENT_PARSER_PORT% is already in use.
        pause
        exit /b 1
    )
    echo Starting backend API at %BACKEND_URL%
    start "Document Parser API" "%ComSpec%" /k ""%PYTHON%" -m uvicorn document_parser.backend.main:app --app-dir "%PROJECT_PARENT%" --host %HOST% --port %DOCUMENT_PARSER_PORT%"
    call :wait_for_url "%HEALTH_URL%" "backend API"
    if errorlevel 1 exit /b 1
)

netstat -ano | findstr /R /C:":%FRONTEND_PORT% .*LISTENING" >nul
if not errorlevel 1 (
    echo [ERROR] Frontend port %FRONTEND_PORT% is already in use.
    pause
    exit /b 1
)
echo Starting frontend dev server at %FRONTEND_URL%
start "Document Parser Frontend" /D "%PROJECT_ROOT%\frontend" "%ComSpec%" /k "npm run dev -- --host %HOST% --port %FRONTEND_PORT%"
call :wait_for_url "%FRONTEND_URL%" "frontend"
if errorlevel 1 exit /b 1
start "" "%FRONTEND_URL%"
echo Browser opened: %FRONTEND_URL%
echo Close the API and frontend windows to stop local development.
exit /b 0

:wait_for_url
set "WAIT_URL=%~1"
set "WAIT_LABEL=%~2"
set /a ATTEMPT=0
:wait_loop
set /a ATTEMPT+=1
powershell -NoProfile -Command "$ErrorActionPreference = 'Stop'; $response = Invoke-WebRequest -UseBasicParsing -Uri '%WAIT_URL%' -TimeoutSec 2; if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { exit 0 }; exit 1" >nul 2>&1
if not errorlevel 1 exit /b 0
if %ATTEMPT% GEQ 60 (
    echo [ERROR] The %WAIT_LABEL% did not become ready within 60 seconds.
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_loop
