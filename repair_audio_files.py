import os
import re
import sys
import time
import shutil
import logging
from typing import List, Tuple

from core.models import VideoItem, DownloadStatus
from core.utils import is_valid_mp4, is_audio_file, format_bytes
from core.tikwm import resolve_video_info

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RepairTool")

def scan_corrupted_files(downloads_dir: str = "downloads") -> List[Tuple[str, str, str]]:
    """
    Quét toàn bộ thư mục downloads để tìm các tệp .mp4 bị lỗi chỉ có tiếng (file MP3 bị lưu nhầm đuôi .mp4).
    Trả về danh sách: [(file_path, username, video_id), ...]
    """
    corrupted = []
    if not os.path.exists(downloads_dir):
        return []

    for root, dirs, files in os.walk(downloads_dir):
        for f in files:
            if f.endswith(".mp4"):
                fpath = os.path.join(root, f)
                # Kiểm tra xem có phải file audio thuần túy (ID3) hoặc không có header ftyp
                if is_audio_file(fpath) or not is_valid_mp4(fpath):
                    m_id = re.search(r'(\d{15,22})', f)
                    if m_id:
                        vid_id = m_id.group(1)
                        # Tìm username từ tên tệp hoặc tên thư mục
                        uname = ""
                        m_u = re.search(r'^([a-zA-Z0-9_.-]+)_\d+', f)
                        if m_u:
                            uname = m_u.group(1)
                        else:
                            folder_name = os.path.basename(root)
                            if folder_name.startswith("@"):
                                uname = folder_name[1:]
                        corrupted.append((fpath, uname, vid_id))
    return corrupted

def repair_single_file(fpath: str, uname: str, vid_id: str) -> bool:
    """
    Tải lại video MP4 chuẩn có đầy đủ hình ảnh và âm thanh từ TikTok để thay thế file bị lỗi.
    """
    tiktok_url = f"https://www.tiktok.com/@{uname or 'user'}/video/{vid_id}"
    logger.info(f"🔄 Đang trích xuất video gốc cho ID {vid_id} ...")
    
    info = resolve_video_info(tiktok_url)
    if not info or not info.download_url:
        logger.warning(f"❌ Không lấy được link tải video cho {vid_id}")
        return False

    temp_path = fpath + ".repair_part"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.tiktok.com/",
    }

    import requests
    try:
        resp = requests.get(info.download_url, headers=headers, stream=True, timeout=25)
        if resp.status_code == 200:
            with open(temp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1048576):
                    if chunk:
                        f.write(chunk)

            if os.path.exists(temp_path) and is_valid_mp4(temp_path):
                new_size = os.path.getsize(temp_path)
                # Thay thế file cũ
                if os.path.exists(fpath):
                    os.remove(fpath)
                os.rename(temp_path, fpath)
                logger.info(f"✅ Sửa thành công: {os.path.basename(fpath)} ({format_bytes(new_size)}) - Video chuẩn!")
                return True
            else:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                logger.warning(f"⚠️ Tệp tải về cho {vid_id} vẫn không có luồng video.")
                return False
        else:
            logger.warning(f"⚠️ Máy chủ trả về HTTP {resp.status_code} cho {vid_id}")
            return False
    except Exception as e:
        logger.error(f"❌ Lỗi tải video sửa chữa cho {vid_id}: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False

def main():
    downloads_dir = "downloads"
    if len(sys.argv) > 1:
        downloads_dir = sys.argv[1]

    print("=" * 60)
    print("🛠️ CÔNG CỤ SỬA CHỮA VIDEO TIKTOK (FIX LỖI CHỈ CÓ TIẾNG)")
    print("=" * 60)
    print(f"🔍 Đang quét thư mục: {os.path.abspath(downloads_dir)} ...")

    corrupted_list = scan_corrupted_files(downloads_dir)
    total = len(corrupted_list)

    if total == 0:
        print("🎉 Tuyệt vời! Không tìm thấy tệp video nào bị lỗi chỉ có tiếng.")
        return

    print(f"⚠️ Phát hiện {total} tệp video bị lỗi chỉ có tiếng (file MP3 bị lưu nhầm .mp4).")
    print(f"🚀 Bắt đầu quá trình tải lại video MP4 chuẩn có đầy đủ hình ảnh...\n")

    success_count = 0
    fail_count = 0

    for idx, (fpath, uname, vid_id) in enumerate(corrupted_list, 1):
        fname = os.path.basename(fpath)
        print(f"[{idx}/{total}] Đang xử lý: {fname} ...")
        ok = repair_single_file(fpath, uname, vid_id)
        if ok:
            success_count += 1
        else:
            fail_count += 1
        print("-" * 50)

    print("\n" + "=" * 60)
    print(f"🎉 Hoàn tất sửa chữa! Đã sửa thành công: {success_count}/{total} video. Thất bại: {fail_count}")
    print("=" * 60)

if __name__ == "__main__":
    main()
