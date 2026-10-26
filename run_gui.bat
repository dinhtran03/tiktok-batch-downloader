@echo off
title TikTok Batch Downloader - Khoi dong ung dung
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   TIKTOK BATCH CHANNEL DOWNLOADER (TURBO NO-WATERMARK)
echo   Khoi dong ung dung giao dien Desktop...
echo ========================================================
echo.

REM 1. Tim trinh thong dich Python tren may
set "PYTHON_CMD="

REM Kiem tra trong .venv truoc neu co san va hop le
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=.venv\Scripts\python.exe"
        goto :launch
    ) else (
        echo [THONG BAO] Moi truong .venv cu khong phu hop voi thiet bi nay.
        echo Dang xoa va thiet lap lai moi truong moi...
        rmdir /s /q .venv >nul 2>nul
    )
)

REM Kiem tra python toan he thong
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "SYSTEM_PY=python"
        goto :setup_venv
    )
)

REM Kiem tra py launcher neu co
where py >nul 2>nul
if not errorlevel 1 (
    py -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "SYSTEM_PY=py"
        goto :setup_venv
    )
)

REM Neu khong tim thay Python hop le nao
echo ========================================================
echo [CANH BAO] May tinh cua ban chua cai dat Python hop le!
echo.
echo Vui long truy cap: https://www.python.org/downloads/
echo Tai va cai dat ban Python 3.10 hoac moi hon.
echo * LUU Y QUAN TRONG: Khi cai dat, nho TICK vao o:
echo   [x] Add python.exe to PATH
echo ========================================================
echo.
pause
exit /b 1

:setup_venv
echo [THONG BAO] Phat hien thiet bi moi! Dang thiet lap moi truong tu dong...
echo [1/2] Dang khoi tao moi truong ao .venv...
%SYSTEM_PY% -m venv .venv
if errorlevel 1 (
    echo [LOI] Khong the tao moi truong ao bang Python!
    echo Vui long kiem tra lai quyen truy cap thu muc hoac bo cai Python.
    pause
    exit /b 1
)

echo [2/2] Dang cai dat cac thu vien can thiet tu requirements.txt...
echo Qua trinh nay mat khoang 1-2 phut trong lan dau tien, vui long cho...
".venv\Scripts\python.exe" -m pip install --no-cache-dir --upgrade pip >nul 2>nul
".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt
if errorlevel 1 (
    echo [LOI] Co van de xay ra khi cai dat thu vien!
    pause
    exit /b 1
)

echo.
echo [HOAN TAT] Cai dat moi truong thanh cong!
echo.
set "PYTHON_CMD=.venv\Scripts\python.exe"

:launch
echo Dang mo giao dien TikTok Downloader Pro...
"%PYTHON_CMD%" -B main.py

if errorlevel 1 (
    echo.
    echo ========================================================
    echo [LOI] Co van de xay ra khi khoi chay ung dung!
    echo Xem thong bao loi chi tiet o tren de xu ly.
    echo ========================================================
    echo.
    pause
)
