@echo off
title Log Filter Viewer - Port 6666
cd /d "%~dp0"

echo ========================================================
echo   Starting Log Filter Viewer on http://localhost:6666
echo ========================================================
echo.

set "PY_CMD=python"
python -c "import sys" >nul 2>nul
if errorlevel 1 (
    py -c "import sys" >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python not found. Please install Python and add to PATH.
        pause
        exit /b 1
    ) else (
        set "PY_CMD=py"
    )
)

echo Checking dependencies and starting Streamlit server...
echo Local URL: http://localhost:6666
echo Press Ctrl+C in this window to stop the server.
echo.

%PY_CMD% "%~dp0launch.py" %*
set "EXIT_CODE=%ERRORLEVEL%"

if "%~1"=="" pause
exit /b %EXIT_CODE%
