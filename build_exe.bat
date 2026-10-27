@echo off
chcp 65001 >nul
title Đóng gói TikTok Downloader Pro thành file .EXE

echo ========================================================
echo   TIKTOK BATCH CHANNEL DOWNLOADER - BUILD .EXE STANDALONE
echo ========================================================
echo.

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    goto :RUN_BUILD
)

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python"
    goto :RUN_BUILD
)

echo [LỖI] Không tìm thấy Python! Vui lòng chạy setup_env.bat trước.
pause
exit /b 1

:RUN_BUILD
"%PYTHON_EXE%" build_exe.py
echo.
pause
