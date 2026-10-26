@echo off
chcp 65001 >nul
title Đẩy mã nguồn lên GitHub - TikTok Batch Downloader

echo ========================================================
echo       TIKTOK BATCH DOWNLOADER - ĐẨY LÊN GITHUB
echo ========================================================
echo.

cd /d "%~dp0"

where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    if exist "C:\Program Files\Git\cmd\git.exe" (
        set "GIT_CMD=C:\Program Files\Git\cmd\git.exe"
    ) else (
        echo [LỖI] Không tìm thấy Git! Vui lòng cài đặt Git trước.
        pause
        exit /b 1
    )
) else (
    set "GIT_CMD=git"
)

echo [1/3] Kiểm tra trạng thái Git...
"%GIT_CMD%" status -s

echo.
echo [2/3] Cập nhật và lưu commit mới nhất...
"%GIT_CMD%" add .
"%GIT_CMD%" commit -m "feat: TikTok Batch Channel Downloader - Turbo Edition (No-watermark HD)" 2>nul

echo.
echo [3/3] Đang đẩy lên GitHub (nhánh main)...
"%GIT_CMD%" push -u origin main

if %ERRORLEVEL% equ 0 (
    echo.
    echo ========================================================
    echo [THÀNH CÔNG] ĐÃ ĐẨY TOÀN BỘ MÃ NGUỒN LÊN GITHUB!
    echo Link repo: https://github.com/dinhtran03/tiktok-batch-downloader
    echo ========================================================
) else (
    echo.
    echo ========================================================
    echo [CHÚ Ý] Nếu bạn chưa tạo repository trên GitHub:
    echo 1. Hãy truy cập: https://github.com/new
    echo 2. Điền tên: tiktok-batch-downloader (Không tick Add README)
    echo 3. Bấm "Create repository"
    echo 4. Sau đó chạy lại file này một lần nữa để đẩy code lên.
    echo ========================================================
)

echo.
pause
