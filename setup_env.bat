@echo off
title TikTok Batch Downloader - Cai Dat Moi Truong
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   TIKTOK BATCH CHANNEL DOWNLOADER - CAI DAT MOI TRUONG
echo ========================================================
echo.

set "SYSTEM_PY="

where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "SYSTEM_PY=python"
        goto :do_install
    )
)

where py >nul 2>nul
if not errorlevel 1 (
    py -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "SYSTEM_PY=py"
        goto :do_install
    )
)

echo [CANH BAO] May tinh cua ban chua cai dat Python hop le!
echo Vui long vao https://www.python.org/downloads/ va cai dat Python 3.10 tro len.
echo * LUU Y: Nho TICK vao o "Add python.exe to PATH" khi cai.
echo.
pause
exit /b 1

:do_install
echo [1/3] Dang khoi tao moi truong ao .venv...
if exist ".venv" (
    echo Dang lam moi thu muc .venv cu...
    rmdir /s /q .venv >nul 2>nul
)

%SYSTEM_PY% -m venv .venv
if errorlevel 1 (
    echo [LOI] Khong the tao moi truong ao!
    pause
    exit /b 1
)

echo [2/3] Dang nang cap pip...
".venv\Scripts\python.exe" -m pip install --no-cache-dir --upgrade pip >nul 2>nul

echo [3/3] Dang cai dat cac thu vien can thiet tu requirements.txt...
".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt
if errorlevel 1 (
    echo [LOI] Co loi khi cai dat thu vien!
    pause
    exit /b 1
)

echo.
echo ========================================================
echo [HOAN TAT] DA CAI DAT XONG MOI TRUONG TREN THIET BI NAY!
echo Ban co the chay "run_gui.bat" de mo giao dien bat ky luc nao.
echo ========================================================
echo.
pause
