@echo off
chcp 65001 >nul
title TikTok Batch Downloader - Sửa lỗi video chỉ có tiếng

echo =======================================================
echo    TIKTOK BATCH DOWNLOADER - CÔNG CỤ SỬA LỖI VIDEO
echo    Tự động tải lại các video bị lỗi chỉ có tiếng
echo =======================================================
echo.

setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    goto :RUN_REPAIR
)

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python"
    goto :RUN_REPAIR
)

echo [LỖI] Không tìm thấy Python! Vui lòng chạy setup_env.bat trước.
pause
exit /b 1

:RUN_REPAIR
"%PYTHON_EXE%" -B repair_audio_files.py
echo.
pause
