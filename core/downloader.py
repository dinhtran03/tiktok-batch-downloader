import os
import time
import json
import shutil
import subprocess
import tempfile
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Callable, Dict, Any, Union

from .models import VideoItem, DownloadStatus, DownloadOptions
from .utils import sanitize_filename, format_bytes, format_timestamp, extract_channel_username, is_valid_mp4, is_audio_file
from .tikwm import resolve_with_tikwm, resolve_video_info

# Kích thước chunk đệm tối ưu: 1 MB giúp giảm tối đa I/O syscall và tăng băng thông
OPTIMAL_CHUNK_SIZE = 1048576  # 1 MB (1024 * 1024 bytes)

class BatchDownloader:
    """
    Bộ quản lý tải video hàng loạt đa luồng siêu tốc không watermark.
    Tích hợp cơ chế dự phòng đa tầng (Multi-tier Failover):
    - Tầng 1: TikWM Direct Stream (Tối ưu thứ tự CDN, chống 403)
    - Tầng 2: SSSTik Proxy Stream
    - Tầng 3: Native yt-dlp In-Process Downloader (Giải mã JS challenge trực tiếp từ TikTok)
    """

    def __init__(self, options: DownloadOptions, browser_cookie: Optional[str] = None):
        self.options = options
        self.browser_cookie = browser_cookie
        self.cancel_event = threading.Event()
        self.is_paused = False
        self.pause_condition = threading.Condition()
        
        # Thiết lập HTTP Session với Connection Pooling & Keep-Alive tái sử dụng kết nối TLS
        self.session = requests.Session()
        retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(
            pool_connections=max(10, self.options.max_workers * 2),
            pool_maxsize=max(10, self.options.max_workers * 2),
            max_retries=retries
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # Thống kê tiến độ
        self.total_count = 0
        self.completed_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.in_progress_count = 0
        self._stats_lock = threading.Lock()
        
        # Danh sách tệp đã tải (lịch sử)
        self.archive_file = os.path.join(self.options.output_dir, ".download_archive.txt")
        self.downloaded_ids = self._load_archive()

        # File txt lưu danh sách tên video tải về (.mp4)
        self.video_list_file = os.path.join(self.options.output_dir, "downloaded_videos.txt")
        self._file_write_lock = threading.Lock()

        # Callbacks
        self.log_callback: Optional[Callable[[str], None]] = None
        self.on_item_status_callback: Optional[Callable[[VideoItem, int, int], None]] = None
        self.on_item_progress_callback: Optional[Callable[[VideoItem, float, str], None]] = None
        self.on_batch_progress_callback: Optional[Callable[[int, int], None]] = None
        self.on_batch_finished_callback: Optional[Callable[[Dict[str, int]], None]] = None

    def log(self, msg: str):
        if self.log_callback:
            self.log_callback(msg)

    def _load_archive(self) -> set:
        """Đọc danh sách ID các video đã tải trước đó vào bộ nhớ đệm (O(1) lookup)."""
        os.makedirs(self.options.output_dir, exist_ok=True)
        if not os.path.exists(self.archive_file):
            return set()
        try:
            with open(self.archive_file, "r", encoding="utf-8") as f:
                return set(line.strip() for line in f if line.strip())
        except Exception:
            return set()

    def _save_to_archive(self, video_id: str):
        """Lưu ID video vào bộ nhớ đệm và file lưu trữ."""
        with self._stats_lock:
            self.downloaded_ids.add(video_id)
        try:
            with open(self.archive_file, "a", encoding="utf-8") as f:
                f.write(f"{video_id}\n")
        except Exception:
            pass

    def _append_video_filename(self, filename: str):
        """
        Ghi tên file video (vd: dung.mat_ket_noi_7700794682691063060.mp4) vào file downloaded_videos.txt.
        Nếu file txt đã tồn tại thì cập nhật (append) thêm dữ liệu vào,
        đảm bảo không bị trùng lặp dòng và hoàn toàn an toàn đa luồng (Thread-safe).
        """
        targets = [self.video_list_file]
        # Nếu đang ở thư mục kênh con (@channel), cập nhật cả file downloaded_videos.txt ở thư mục gốc downloads/
        parent_dir = os.path.dirname(self.options.output_dir)
        if parent_dir and os.path.isdir(parent_dir) and parent_dir != self.options.output_dir:
            targets.append(os.path.join(parent_dir, "downloaded_videos.txt"))

        with self._file_write_lock:
            for txt_path in targets:
                try:
                    existing_lines = set()
                    if os.path.exists(txt_path):
                        with open(txt_path, "r", encoding="utf-8") as f:
                            existing_lines = set(line.strip() for line in f if line.strip())

                    if filename not in existing_lines:
                        with open(txt_path, "a", encoding="utf-8") as f:
                            f.write(f"{filename}\n")
                except Exception:
                    pass

    def _is_already_downloaded(self, video_id: str) -> bool:
        """
        Kiểm tra xem video đã tải và có tệp video MP4 hợp lệ trên đĩa chưa.
        Đặc biệt: Nếu tệp trên đĩa là âm thanh thuần túy (ID3) lưu nhầm dạng .mp4,
        hàm sẽ tự động trả về False để tải lại video MP4 chuẩn có đầy đủ hình ảnh.
        """
        if not self.options.skip_existing:
            return False

        # Kiểm tra tệp vật lý trong thư mục đích
        try:
            if os.path.isdir(self.options.output_dir):
                for fname in os.listdir(self.options.output_dir):
                    if video_id in fname and fname.endswith(".mp4"):
                        fpath = os.path.join(self.options.output_dir, fname)
                        if is_audio_file(fpath) or not is_valid_mp4(fpath):
                            # Tệp cũ bị lỗi chỉ có âm thanh, gỡ khỏi danh sách để tải lại video thật
                            with self._stats_lock:
                                self.downloaded_ids.discard(video_id)
                            return False
                        with self._stats_lock:
                            self.downloaded_ids.add(video_id)
                        return True
        except Exception:
            pass

        with self._stats_lock:
            if video_id in self.downloaded_ids:
                return True
        return False

    def _build_base_filename(self, item: VideoItem) -> str:
        """
        Định dạng tên tệp chuẩn: {username}_{id}
        Ví dụ: dung.mat_ket_noi_7700794682691063060
        """
        raw_user = item.user or extract_channel_username(item.url) or "tiktok_user"
        username_clean = sanitize_filename(raw_user, max_length=50)
        return f"{username_clean}_{item.id}"

    def _build_video_from_slides(self, item: VideoItem, temp_path: str) -> bool:
        """
        Tự động tạo video MP4 chất lượng cao từ các slide ảnh và nhạc nền bằng ffmpeg.
        Đảm bảo các bài đăng Album ảnh / Carousel trên TikTok đều có video hoàn chỉnh với âm thanh.
        """
        if not item.images:
            return False

        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            # Tìm trong thư mục trích xuất của PyInstaller hoặc thư mục chứa file .exe
            for cand_dir in [
                getattr(sys, "_MEIPASS", ""),
                os.path.dirname(sys.executable),
                os.getcwd(),
                os.path.join(os.getcwd(), "tools"),
            ]:
                if cand_dir:
                    f_cand = os.path.join(cand_dir, "ffmpeg.exe")
                    if os.path.exists(f_cand):
                        ffmpeg_bin = f_cand
                        break

        if not ffmpeg_bin:
            self.log(f"⚠️ Không tìm thấy ffmpeg trên hệ thống để ghép slide ảnh cho #{item.id}")
            return False

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://www.tiktok.com/",
        }

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                downloaded_images = []
                for idx, img_url in enumerate(item.images):
                    self._check_pause()
                    if self.cancel_event.is_set():
                        return False
                    img_path = os.path.join(tmpdir, f"slide_{idx:03d}.jpg")
                    try:
                        r = self.session.get(img_url, headers=headers, timeout=15)
                        if r.status_code == 200 and len(r.content) > 1024:
                            with open(img_path, "wb") as f:
                                f.write(r.content)
                            downloaded_images.append(img_path)
                    except Exception:
                        pass

                if not downloaded_images:
                    return False

                # Tải file nhạc nếu có
                music_file = None
                if item.music_url:
                    m_path = os.path.join(tmpdir, "bg_music.mp3")
                    try:
                        r = self.session.get(item.music_url, headers=headers, timeout=15)
                        if r.status_code == 200 and len(r.content) > 1024:
                            with open(m_path, "wb") as f:
                                f.write(r.content)
                            music_file = m_path
                    except Exception:
                        pass

                # Tạo file concat.txt cho ffmpeg (mỗi ảnh hiển thị 2.5 giây)
                concat_path = os.path.join(tmpdir, "concat.txt")
                with open(concat_path, "w", encoding="utf-8") as f:
                    for img in downloaded_images:
                        clean_p = img.replace("\\", "/")
                        f.write(f"file '{clean_p}'\nduration 2.5\n")
                    last_img = downloaded_images[-1].replace("\\", "/")
                    f.write(f"file '{last_img}'\n")

                cmd = [
                    ffmpeg_bin, "-y",
                    "-f", "concat", "-safe", "0", "-i", concat_path,
                ]

                total_duration = len(downloaded_images) * 2.5
                if music_file and os.path.exists(music_file) and os.path.getsize(music_file) > 1024:
                    cmd.extend(["-i", music_file, "-c:a", "aac", "-shortest"])
                else:
                    cmd.extend([
                        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                        "-c:a", "aac", "-t", str(total_duration)
                    ])

                cmd.extend([
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-preset", "fast",
                    "-r", "30",
                    temp_path
                ])

                res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if res.returncode == 0 and os.path.exists(temp_path) and is_valid_mp4(temp_path):
                    self.log(f"🎬 Đã dựng thành công video MP4 từ {len(downloaded_images)} slide ảnh cho #{item.id}!")
                    return True
                else:
                    self.log(f"⚠️ Ghép video slide gặp lỗi: {res.stderr[:200] if res.stderr else 'unknown'}")
        except Exception as e:
            self.log(f"⚠️ Ngoại lệ khi tạo video slide cho #{item.id}: {e}")

        return False

    def cancel(self):
        """Hủy toàn bộ tiến trình tải."""
        self.cancel_event.set()
        self.resume()
        self.log("⏹️ Đã yêu cầu dừng tải hàng loạt.")

    def pause(self):
        """Tạm dừng tiến trình tải."""
        self.is_paused = True
        self.log("⏸️ Đã tạm dừng tiến trình tải.")

    def resume(self):
        """Tiếp tục tiến trình tải."""
        self.is_paused = False
        with self.pause_condition:
            self.pause_condition.notify_all()
        self.log("▶️ Tiếp tục tiến trình tải.")

    def _check_pause(self):
        """Kiểm tra xem có đang tạm dừng không."""
        with self.pause_condition:
            while self.is_paused and not self.cancel_event.is_set():
                self.pause_condition.wait(0.5)

        # Sau khi thức dậy từ tạm dừng, kiểm tra nếu đã đạt giới hạn limit_videos thì dừng ngay
        if self.options.limit_videos is not None:
            with self._stats_lock:
                if self.completed_count >= self.options.limit_videos:
                    self.cancel_event.set()

    def download_single_video(self, item: VideoItem, index: int, total: int) -> bool:
        """
        Tải một video đơn lẻ với buffer 1MB, tái sử dụng session và cơ chế fallback đa tầng.
        Hoàn toàn loại bỏ tình trạng kẹt 'Không trích xuất được link không watermark'.
        """
        self._check_pause()
        if self.cancel_event.is_set():
            item.status = DownloadStatus.FAILED
            item.error_message = "Đã hủy"
            return False

        # Kiểm tra giới hạn số lượng video đã tải (nếu có cấu hình limit)
        if self.options.limit_videos is not None:
            with self._stats_lock:
                if self.completed_count >= self.options.limit_videos:
                    item.status = DownloadStatus.SKIPPED
                    return False

        # 1. Kiểm tra tức thời nếu đã tải rồi
        if self._is_already_downloaded(item.id):
            item.status = DownloadStatus.SKIPPED
            base_name = self._build_base_filename(item)
            self._append_video_filename(f"{base_name}.mp4")
            with self._stats_lock:
                self.skipped_count += 1
            self.log(f"⏭️ [{index}/{total}] Bỏ qua video #{item.id} (đã có sẵn)")
            if self.on_item_status_callback:
                self.on_item_status_callback(item, index, total)
            if self.on_batch_progress_callback:
                self.on_batch_progress_callback(self.completed_count + self.skipped_count, total)
            return True

        item.status = DownloadStatus.DOWNLOADING
        with self._stats_lock:
            self.in_progress_count += 1

        if self.on_item_status_callback:
            self.on_item_status_callback(item, index, total)

        # 2. Chuẩn bị đường dẫn tệp lưu theo chuẩn {username}_{id}.mp4
        base_name = self._build_base_filename(item)
        filename = f"{base_name}.mp4"
        dest_path = os.path.join(self.options.output_dir, filename)
        temp_path = dest_path + ".part"

        # 3. Trích xuất link tải không watermark (Tầng 1: TikWM, Tầng 2: SSSTik)
        if not item.download_url:
            resolved_info = resolve_video_info(item.url)
            if resolved_info:
                if resolved_info.download_url:
                    item.download_url = resolved_info.download_url
                if resolved_info.backup_urls:
                    item.backup_urls = resolved_info.backup_urls
                if not item.user and resolved_info.user:
                    item.user = resolved_info.user
                    base_name = self._build_base_filename(item)
                    filename = f"{base_name}.mp4"
                    dest_path = os.path.join(self.options.output_dir, filename)
                    temp_path = dest_path + ".part"
                if not item.title and resolved_info.title:
                    item.title = resolved_info.title
                if not item.cover_url and resolved_info.cover_url:
                    item.cover_url = resolved_info.cover_url
                if not item.music_url and resolved_info.music_url:
                    item.music_url = resolved_info.music_url
                if not item.create_time and resolved_info.create_time:
                    item.create_time = resolved_info.create_time
                if resolved_info.images:
                    item.images = resolved_info.images
                    item.is_photo = resolved_info.is_photo

        # Thu thập danh sách candidate URLs
        candidate_urls = []
        if item.download_url:
            candidate_urls.append(item.download_url)
        if hasattr(item, "backup_urls") and item.backup_urls:
            for u in item.backup_urls:
                if u and u not in candidate_urls:
                    candidate_urls.append(u)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://www.tiktok.com/",
        }

        download_success = False
        downloaded = 0

        # Thử tải trực tiếp từ các candidate URLs (TikWM / SSSTik)
        for cand_url in candidate_urls:
            self._check_pause()
            if self.cancel_event.is_set():
                break

            try:
                resp = self.session.get(cand_url, headers=headers, stream=True, timeout=20)
                if resp.status_code == 200:
                    total_size = int(resp.headers.get("content-length", 0))
                    item.total_bytes = total_size
                    downloaded = 0
                    start_time = time.time()
                    last_update_time = start_time

                    with open(temp_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=OPTIMAL_CHUNK_SIZE):
                            self._check_pause()
                            if self.cancel_event.is_set():
                                f.close()
                                if os.path.exists(temp_path):
                                    try:
                                        os.remove(temp_path)
                                    except Exception:
                                        pass
                                item.status = DownloadStatus.FAILED
                                with self._stats_lock:
                                    self.in_progress_count = max(0, self.in_progress_count - 1)
                                return False

                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                item.bytes_downloaded = downloaded

                                now = time.time()
                                if now - last_update_time >= 0.25 or (total_size > 0 and downloaded == total_size):
                                    speed = downloaded / max(now - start_time, 0.001)
                                    speed_str = f"{format_bytes(int(speed))}/s"
                                    percent = (downloaded / total_size * 100) if total_size > 0 else 0.0
                                    if self.on_item_progress_callback:
                                        self.on_item_progress_callback(item, percent, speed_str)
                                    last_update_time = now

                    if os.path.exists(temp_path) and os.path.getsize(temp_path) > 1024:
                        if is_valid_mp4(temp_path):
                            download_success = True
                            break
                        else:
                            self.log(f"⚠️ [{index}/{total}] Tệp tải về từ nguồn mạng cho #{item.id} không phải video MP4 hợp lệ, chuyển sang nguồn khác...")
                            try:
                                os.remove(temp_path)
                            except Exception:
                                pass
            except Exception:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                continue

        # 4. TẦNG 3: Nếu các link online đều lỗi/chặn IP, tự động kích hoạt yt-dlp nội bộ
        # QUAN TRỌNG: Chỉ tải định dạng có hình ảnh (vcodec!=none), tuyệt đối không tải nhầm file audio MP3 rồi đổi đuôi .mp4
        if not download_success and not self.cancel_event.is_set():
            self.log(f"🔄 [{index}/{total}] Đang kích hoạt bộ giải mã trực tiếp từ TikTok cho #{item.id}...")
            try:
                import yt_dlp
                start_time = time.time()
                last_update_time = start_time

                def _ytdl_hook(d):
                    nonlocal last_update_time
                    if self.cancel_event.is_set():
                        raise Exception("Đã hủy thao tác")
                    if d.get("status") == "downloading":
                        d_b = d.get("downloaded_bytes", 0)
                        t_b = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                        spd = d.get("speed") or 0
                        item.bytes_downloaded = d_b
                        if t_b > 0:
                            item.total_bytes = t_b
                        now = time.time()
                        if now - last_update_time >= 0.25:
                            spd_str = f"{format_bytes(int(spd))}/s" if spd else "--/s"
                            pct = (d_b / t_b * 100) if t_b > 0 else 0.0
                            if self.on_item_progress_callback:
                                self.on_item_progress_callback(item, pct, spd_str)
                            last_update_time = now

                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "outtmpl": temp_path,
                    "overwrites": True,
                    "noplaylist": True,
                    "format": "bestvideo[vcodec!=none]+bestaudio/best[vcodec!=none]",
                    "progress_hooks": [_ytdl_hook],
                }
                if self.browser_cookie:
                    ydl_opts["cookiesfrombrowser"] = (self.browser_cookie.lower(),)

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([item.url])

                if os.path.exists(temp_path) and os.path.getsize(temp_path) > 1024:
                    if is_valid_mp4(temp_path):
                        download_success = True
                        downloaded = os.path.getsize(temp_path)
                    else:
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
            except Exception as yt_err:
                self.log(f"⚠️ Bộ tải trực tiếp gặp lỗi với #{item.id}: {yt_err}")
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

        # 5. TẦNG 4: Nếu là bài đăng dạng Album ảnh / Slide ảnh (Photo Carousel post), tự động tải ảnh + nhạc và dựng video MP4 bằng ffmpeg
        if not download_success and not self.cancel_event.is_set():
            if item.images:
                self.log(f"📸 [{index}/{total}] Phát hiện bài đăng Album ảnh (#{item.id}), đang tổng hợp video MP4 có nhạc bằng ffmpeg...")
                if self._build_video_from_slides(item, temp_path):
                    download_success = True
                    downloaded = os.path.getsize(temp_path)

        # 6. Xử lý sau khi tải xong
        if not download_success:
            item.status = DownloadStatus.FAILED
            item.error_message = "Không trích xuất được luồng video không watermark từ máy chủ TikTok"
            with self._stats_lock:
                self.failed_count += 1
                self.in_progress_count = max(0, self.in_progress_count - 1)
            self.log(f"❌ [{index}/{total}] Thất bại video #{item.id}: {item.error_message}")
            if self.on_item_status_callback:
                self.on_item_status_callback(item, index, total)
            return False

        # Đổi tên từ .part sang file chính thức
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
            os.rename(temp_path, dest_path)
            item.file_path = dest_path
        except Exception as rename_err:
            item.status = DownloadStatus.FAILED
            item.error_message = f"Lỗi đổi tên tệp: {rename_err}"
            with self._stats_lock:
                self.failed_count += 1
                self.in_progress_count = max(0, self.in_progress_count - 1)
            return False

        # Tùy chọn nâng cao: Tự động lọc từ nhạy cảm 'tiktok' (Cắt đoạn nói & Che logo chữ bằng sticker)
        if self.options.enable_censorship and item.file_path and os.path.exists(item.file_path):
            try:
                from .censor import process_video_censorship
                self.log(f"🛡️ [{index}/{total}] Đang kích hoạt bộ lọc bản quyền / nhạy cảm cho video #{item.id}...")
                process_video_censorship(
                    video_path=item.file_path,
                    keywords_str=self.options.censor_keywords,
                    custom_sticker_path=self.options.custom_sticker_path,
                    log_callback=self.log
                )
            except Exception as censor_err:
                self.log(f"⚠️ Lỗi khi lọc video #{item.id}: {censor_err} (Giữ video gốc)")

        # 6. Tải thêm ảnh bìa nếu được chọn
        if self.options.download_cover and item.cover_url:
            try:
                cover_filename = f"{base_name}_cover.jpg"
                cover_path = os.path.join(self.options.output_dir, cover_filename)
                c_resp = self.session.get(item.cover_url, headers=headers, timeout=10)
                if c_resp.status_code == 200:
                    with open(cover_path, "wb") as cf:
                        cf.write(c_resp.content)
            except Exception:
                pass

        # 7. Tải thêm file nhạc nếu được chọn
        if self.options.download_audio and item.music_url:
            try:
                audio_filename = f"{base_name}_audio.mp3"
                audio_path = os.path.join(self.options.output_dir, audio_filename)
                a_resp = self.session.get(item.music_url, headers=headers, timeout=10)
                if a_resp.status_code == 200:
                    with open(audio_path, "wb") as af:
                        af.write(a_resp.content)
            except Exception:
                pass

        # 8. Lưu metadata JSON nếu được chọn
        if self.options.save_metadata:
            try:
                date_str = format_timestamp(item.create_time)
                meta_filename = f"{base_name}_meta.json"
                meta_path = os.path.join(self.options.output_dir, meta_filename)
                meta_data = {
                    "id": item.id,
                    "title": item.title,
                    "user": item.user,
                    "url": item.url,
                    "create_time": item.create_time,
                    "date": date_str,
                    "duration": item.duration,
                    "download_url": item.download_url,
                    "cover_url": item.cover_url,
                    "music_url": item.music_url,
                    "file_path": dest_path,
                }
                with open(meta_path, "w", encoding="utf-8") as jf:
                    json.dump(meta_data, jf, ensure_ascii=False, indent=2)
            except Exception:
                pass

        # Đánh dấu thành công
        item.status = DownloadStatus.COMPLETED
        self._save_to_archive(item.id)
        self._append_video_filename(filename)
        with self._stats_lock:
            self.completed_count += 1
            self.in_progress_count = max(0, self.in_progress_count - 1)

        self.log(f"✅ [{index}/{total}] Tải xong: {filename} ({format_bytes(downloaded)})")

        if self.on_item_status_callback:
            self.on_item_status_callback(item, index, total)
        if self.on_batch_progress_callback:
            self.on_batch_progress_callback(self.completed_count + self.skipped_count, total)
        return True

    def download_batch(self, videos: List[VideoItem]) -> Dict[str, int]:
        """Tải toàn bộ danh sách video với ThreadPool tốc độ cao."""
        self.cancel_event.clear()
        self.total_count = len(videos)
        self.completed_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.in_progress_count = 0

        self.log(f"🚀 Bắt đầu tải {self.total_count} video với {self.options.max_workers} luồng đồng thời...")
        os.makedirs(self.options.output_dir, exist_ok=True)

        with ThreadPoolExecutor(max_workers=self.options.max_workers) as executor:
            futures = []
            for idx, v in enumerate(videos, 1):
                if self.cancel_event.is_set():
                    break
                if self.options.limit_videos and self.completed_count >= self.options.limit_videos:
                    break
                f = executor.submit(self.download_single_video, v, idx, self.total_count)
                futures.append(f)
            
            for f in futures:
                try:
                    f.result()
                except Exception:
                    pass

        stats = {
            "total": self.total_count,
            "completed": self.completed_count,
            "skipped": self.skipped_count,
            "failed": self.failed_count,
        }

        # Giải phóng bộ nhớ đệm RAM sau khi hoàn tất lượt tải
        import gc
        gc.collect()

        self.log(f"🎉 Hoàn tất phiên tải! Thành công: {self.completed_count} | Bỏ qua: {self.skipped_count} | Lỗi: {self.failed_count}")
        if self.on_batch_finished_callback:
            self.on_batch_finished_callback(stats)

        return stats

    def download_from_stream_queue(
        self,
        item_queue: queue.Queue,
        get_total_callback: Callable[[], int],
        on_item_received_callback: Optional[Callable[[VideoItem, int], None]] = None
    ) -> Dict[str, int]:
        """
        Mô hình Producer-Consumer siêu tốc:
        Vừa quét vừa tải song song ngay lập tức!
        Worker không cần đợi quét xong toàn bộ kênh mới bắt đầu tải.
        Tự động dừng chuẩn xác khi đã đạt đủ số lượng limit_videos được cài đặt (chống chạy quá số lượng).
        """
        self.cancel_event.clear()
        self.completed_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.in_progress_count = 0

        os.makedirs(self.options.output_dir, exist_ok=True)
        worker_threads = []
        item_counter = 0
        allocated_count = 0
        counter_lock = threading.Lock()

        def _worker():
            nonlocal item_counter, allocated_count
            while not self.cancel_event.is_set():
                # 1. Kiểm tra trước khi lấy item: Đã đủ quota số lượng cần tải chưa
                if self.options.limit_videos is not None:
                    with counter_lock:
                        if allocated_count >= self.options.limit_videos or self.completed_count >= self.options.limit_videos:
                            break

                try:
                    item = item_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if item is None:  # Dấu hiệu kết thúc stream
                    item_queue.task_done()
                    break

                # 2. Đặt chỗ quota tải nguyên tử (Atomic Reservation) - Đảm bảo đa luồng không vượt limit
                with counter_lock:
                    if self.options.limit_videos is not None:
                        if allocated_count >= self.options.limit_videos or self.completed_count >= self.options.limit_videos:
                            item_queue.task_done()
                            break
                    allocated_count += 1
                    item_counter += 1
                    curr_idx = item_counter

                tot = max(get_total_callback(), curr_idx)
                if self.options.limit_videos:
                    tot = min(tot, self.options.limit_videos)

                self.download_single_video(item, curr_idx, tot)
                item_queue.task_done()

        # Khởi động pool worker threads
        num_workers = self.options.max_workers
        for _ in range(num_workers):
            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            worker_threads.append(t)

        # Chờ toàn bộ worker hoàn tất
        for t in worker_threads:
            t.join()

        stats = {
            "total": max(self.total_count, item_counter),
            "completed": self.completed_count,
            "skipped": self.skipped_count,
            "failed": self.failed_count,
        }

        # Giải phóng bộ nhớ đệm RAM sau khi hoàn tất lượt tải
        import gc
        gc.collect()

        self.log(f"🎉 Hoàn tất toàn bộ kênh! Thành công: {self.completed_count} | Bỏ qua: {self.skipped_count} | Lỗi: {self.failed_count}")
        if self.on_batch_finished_callback:
            self.on_batch_finished_callback(stats)

        return stats
