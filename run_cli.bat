@echo off
title TikTok Batch Downloader - Dong lenh (CLI)
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   TIKTOK BATCH CHANNEL DOWNLOADER (CLI)
echo ========================================================
echo.

REM 1. Tim trinh thong dich Python tren may
set "PYTHON_CMD="

REM Kiem tra trong .venv truoc neu co san va hop le
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=.venv\Scripts\python.exe -B"
        goto :cli_start
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
        goto :setup_venv_cli
    )
)

where py >nul 2>nul
if not errorlevel 1 (
    py -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "SYSTEM_PY=py"
        goto :setup_venv_cli
    )
)

echo ========================================================
echo [CANH BAO] May tinh cua ban chua cai dat Python hop le!
echo Vui long truy cap: https://www.python.org/downloads/
echo Tai va cai dat ban Python 3.10 hoac moi hon.
echo * LUU Y: Nho TICK vao o "Add python.exe to PATH" khi cai.
echo ========================================================
echo.
pause
exit /b 1

:setup_venv_cli
echo [THONG BAO] Phat hien thiet bi moi! Dang thiet lap moi truong tu dong...
echo [1/2] Dang khoi tao moi truong ao .venv...
%SYSTEM_PY% -m venv .venv
if errorlevel 1 (
    echo [LOI] Khong the tao moi truong ao bang Python!
    pause
    exit /b 1
)

echo [2/2] Dang cai dat cac thu vien can thiet tu requirements.txt...
".venv\Scripts\python.exe" -m pip install --no-cache-dir --upgrade pip >nul 2>nul
".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt
if errorlevel 1 (
    echo [LOI] Co van de xay ra khi cai dat thu vien!
    pause
    exit /b 1
)

echo [HOAN TAT] Cai dat moi truong thanh cong!
echo.
set "PYTHON_CMD=.venv\Scripts\python.exe -B"

:cli_start
if not "%~1"=="" (
    "%PYTHON_CMD%" cli.py %*
    goto end
)

echo Huong dan: Nhap link kenh TikTok hoac danh sach cac kenh cach nhau bang dau phay
echo Vi du: @dung.mat_ket_noi, @openai, khaby.lame
set /p CHANNEL_INPUT="Link kenh hoac @username: "

if "%CHANNEL_INPUT%"=="" (
    echo [LOI] Ban chua nhap link kenh!
    pause
    exit /b 1
)

echo.
set /p LIMIT_INPUT="So luong video muon tai moi kenh (nhan Enter de tai TOAN BO kenh): "

if "%LIMIT_INPUT%"=="" (
    "%PYTHON_CMD%" cli.py -c "%CHANNEL_INPUT%"
) else (
    "%PYTHON_CMD%" cli.py -c "%CHANNEL_INPUT%" -l %LIMIT_INPUT%
)

:end
echo.
pause
