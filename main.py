#!/usr/bin/env python3
"""
TikTok Batch Channel Downloader - Main Entrypoint
- Chạy không tham số: Khởi động giao diện đồ họa Desktop (GUI)
- Chạy với tham số: Khởi động giao diện dòng lệnh (CLI)
"""
import sys
import os

# Đảm bảo đường dẫn thư mục hiện tại nằm trong sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

def main():
    # Nếu có cờ tham số dòng lệnh (ngoài tên script), chạy CLI
    if len(sys.argv) > 1 and not (len(sys.argv) == 2 and sys.argv[1].lower() in ["--gui", "-g"]):
        from cli import main as cli_main
        cli_main()
    else:
        # Mặc định khởi động giao diện đồ họa GUI
        from gui.app import main as gui_main
        gui_main()

if __name__ == "__main__":
    main()
