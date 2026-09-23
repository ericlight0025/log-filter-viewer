@echo off
title Log Filter Viewer - Port 6666
cd /d "%~dp0"

echo ========================================================
echo   Starting Log Filter Viewer on http://localhost:6666
echo ========================================================
echo.

set "PY_CMD=python"
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    where py >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PY_CMD=py"
    ) else (
        echo [ERROR] Python not found. Please install Python and add to PATH.
        pause
        exit /b 1
    )
)

echo [1/2] Opening browser with port 6666 allowed...
start "" msedge.exe --explicitly-allowed-ports=6666 http://localhost:6666 2>nul || start "" chrome.exe --explicitly-allowed-ports=6666 http://localhost:6666 2>nul || start http://localhost:6666

echo [2/2] Starting Streamlit server...
echo Local URL: http://localhost:6666
echo Press Ctrl+C in this window to stop the server.
echo.

%PY_CMD% -m streamlit run streamlit_app\app.py --server.port 6666 --server.headless true

pause
