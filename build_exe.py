import os
import sys
import shutil
import subprocess

def build():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    print("=" * 65)
    print("🚀 BẮT ĐẦU ĐÓNG GÓI ỨNG DỤNG TIKTOK DOWNLOADER THÀNH FILE .EXE")
    print("=" * 65)

    # 1. Dọn dẹp thư mục build & dist cũ
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            print(f"🧹 Đang xóa thư mục {folder} cũ...")
            try:
                shutil.rmtree(folder)
            except Exception as e:
                print(f"⚠️ Không thể xóa {folder}: {e}")

    # 2. Kiểm tra icon
    icon_arg = []
    if os.path.exists("app_icon.ico"):
        icon_arg = [
            "--icon=app_icon.ico",
            "--add-data=app_icon.ico;."
        ]

    # 3. Lệnh PyInstaller đóng gói thành 1 file .exe duy nhất không hiện cửa sổ đen
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=TikTokDownloaderPro",
        "--onefile",
        "--noconsole",
        "--clean",
        "--collect-all=customtkinter",
        "--collect-all=gallery_dl",
        "--collect-all=yt_dlp",
        "--collect-all=curl_cffi",
        "--hidden-import=PIL",
        "--hidden-import=darkdetect",
        "--hidden-import=tkinter",
        "--hidden-import=tkinter.filedialog",
        "--hidden-import=tkinter.messagebox",
    ] + icon_arg + ["main.py"]

    print("\n📦 Đang biên dịch mã nguồn và đóng gói toàn bộ thư viện...")
    print("Lệnh chạy:", " ".join(cmd))
    print("Quá trình này có thể mất từ 1 - 2 phút, vui lòng chờ...\n")

    res = subprocess.run(cmd)

    if res.returncode == 0:
        exe_path = os.path.join(script_dir, "dist", "TikTokDownloaderPro.exe")
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print("\n" + "=" * 65)
            print("🎉 ĐÓNG GÓI THÀNH CÔNG RỰC RỠ!")
            print(f"📁 Tệp thực thi độc lập: {exe_path}")
            print(f"⚖️ Dung lượng: {size_mb:.1f} MB")
            print("👉 Bạn chỉ cần copy duy nhất file TikTokDownloaderPro.exe sang bất kỳ máy tính nào là có thể chạy trực tiếp ngay, không cần cài đặt Python hay thư viện!")
            print("=" * 65)
            return True
    
    print("\n❌ Có lỗi xảy ra trong quá trình đóng gói PyInstaller!")
    return False

if __name__ == "__main__":
    success = build()
    sys.exit(0 if success else 1)
