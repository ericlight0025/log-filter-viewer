@echo off
chcp 65001 >nul
title Log Filter Viewer (Port 6666)

echo ========================================================
echo   🚀 正在啟動 Log Filter Viewer (Port 6666)
echo ========================================================
echo.

cd /d "%~dp0"

:: 1. 偵測 Python 執行檔
set "PYTHON_EXE="
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python"
) else (
    where py >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_EXE=py"
    )
)

if "%PYTHON_EXE%"=="" (
    echo [錯誤] 系統中未找到 Python！請先安裝 Python 並將其加入系統 PATH。
    echo 下載位置: https://www.python.org/
    pause
    exit /b 1
)

:: 2. 檢查並安裝 streamlit 依賴
%PYTHON_EXE% -c "import streamlit" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [資訊] 首次執行，正在自動安裝必要套件 (streamlit)...
    %PYTHON_EXE% -m pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo [錯誤] 套件安裝失敗，請檢查網路連線。
        pause
        exit /b 1
    )
)

:: 3. 背景延遲 2 秒自動開啟瀏覽器 (解除 Chrome / Edge 對 Port 6666 的限制)
echo [資訊] 伺服器啟動中，稍後將自動開啟瀏覽器...
start "" /b cmd /c "timeout /t 2 /nobreak >nul && (start msedge --explicitly-allowed-ports=6666 http://localhost:6666 2>nul || start chrome --explicitly-allowed-ports=6666 http://localhost:6666 2>nul || start http://localhost:6666)"

:: 4. 啟動 Streamlit
echo [資訊] 本地網址: http://localhost:6666
echo [提示] 如需關閉服務，直接關閉此視窗或按下 Ctrl + C 即可。
echo.
%PYTHON_EXE% -m streamlit run app.py --server.port 6666 --server.headless true

pause
