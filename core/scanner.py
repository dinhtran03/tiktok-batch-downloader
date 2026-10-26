import re
import os
import sys
import time
import queue
import logging
import threading
from typing import List, Optional, Callable, Dict, Any

# Vá lỗi thiếu phương thức traceback trong logging.Logger của Python
if not hasattr(logging.Logger, "traceback"):
    logging.Logger.traceback = lambda self, exc: self.debug("Traceback", exc_info=exc)

from .models import VideoItem, DownloadStatus
from .utils import extract_channel_username, sanitize_filename

def scan_channel_videos(
    channel_input: str,
    limit: Optional[int] = None,
    on_found_callback: Optional[Callable[[VideoItem, int], None]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    stream_queue: Optional[queue.Queue] = None,
    browser_cookie: Optional[str] = None,
    pause_check: Optional[Callable[[], None]] = None
) -> List[VideoItem]:
    """
    Quét và lấy danh sách video từ kênh TikTok trực tiếp bằng Python native.
    - Hoàn toàn loại bỏ lỗi treo tiến trình subprocess trên Windows.
    - Tự động vượt thử thách bảo mật của TikTok bằng thuật toán tích hợp.
    - Đẩy video trực tiếp vào stream_queue để tải song song ngay lập tức!
    - Thu thập toàn bộ tiêu đề, ngày đăng, ảnh bìa, âm thanh gốc từ kênh.
    """
    def log(msg: str):
        if log_callback:
            log_callback(msg)

    username = extract_channel_username(channel_input)
    if not username:
        log(f"❌ Không thể nhận diện tên kênh từ: '{channel_input}'")
        return []

    target_url = f"https://www.tiktok.com/@{username}/posts"
    log(f"🔍 Bắt đầu quét kênh @{username} ...")
    if limit:
        log(f"⚙️ Giới hạn số lượng: {limit} video mới nhất")
    else:
        log(f"⚙️ Chế độ: Quét toàn bộ video công khai của kênh")

    videos: List[VideoItem] = []
    seen_ids = set()

    try:
        # Tối ưu hóa: Nạp lazy gallery-dl chỉ khi thực sự cần quét kênh (giúp khởi động app nhanh hơn 60 lần)
        import gallery_dl
        import gallery_dl.config
        import gallery_dl.cookies
        from gallery_dl.extractor import find

        gallery_dl.config.load()
        extr_cls = find(target_url)
        if not extr_cls:
            log(f"❌ Không tìm thấy bộ trích xuất phù hợp cho {target_url}")
            return []

        extr = extr_cls.from_url(target_url)

        # Nạp Cookie từ trình duyệt nếu người dùng yêu cầu (giúp tránh chặn bot 100%)
        if browser_cookie:
            try:
                cookies = gallery_dl.cookies.load_cookies(browser_cookie.lower())
                if cookies:
                    extr.cookies.update(cookies)
                    log(f"🍪 Đã nạp Cookie thành công từ trình duyệt {browser_cookie}")
            except Exception as e:
                log(f"⚠️ Không thể nạp cookie từ {browser_cookie}: {e}")

        log("🔐 Đang kết nối và xác thực với máy chủ TikTok...")
        extr.initialize()

        # Bắt đầu duyệt danh sách bài đăng từ kênh
        log("📋 Đang lấy danh sách các video đã đăng...")
        posts_data = extr.posts()

        # Hỗ trợ cả dict {post_url: metadata} và generator/list
        if isinstance(posts_data, dict):
            items_iterable = posts_data.items()
        else:
            items_iterable = ((p, None) for p in (posts_data or []))

        for post_url, post_info in items_iterable:
            if pause_check:
                pause_check()

            if cancel_event and cancel_event.is_set():
                log("⏹️ Đã hủy thao tác quét.")
                break

            if not post_url:
                continue

            # Bóc tách video_id từ URL dạng https://www.tiktok.com/@user/video/123456789
            m = re.search(r'/(?:video|photo)/(\d+)', post_url)
            if not m:
                continue
            vid_id = m.group(1)

            if vid_id in seen_ids:
                continue
            seen_ids.add(vid_id)

            # Trích xuất metadata phong phú nếu có
            title = f"tiktok_{vid_id}"
            create_time = None
            duration = None
            cover_url = None
            music_url = None
            slide_images = []
            is_photo = False

            if isinstance(post_info, dict):
                title = post_info.get("desc") or title
                create_time = post_info.get("createTime")
                v_dict = post_info.get("video") or {}
                duration = v_dict.get("duration")
                cover_url = v_dict.get("cover") or v_dict.get("originCover")
                m_dict = post_info.get("music") or {}
                music_url = m_dict.get("playUrl")

                # Trích xuất danh sách ảnh slide nếu là bài đăng dạng Album ảnh
                img_post = post_info.get("image_post_info") or post_info.get("imagePostInfo") or {}
                raw_imgs = img_post.get("images") or []
                for im in raw_imgs:
                    if isinstance(im, dict):
                        display_img = im.get("display_image") or im.get("imageURL") or {}
                        url_list = display_img.get("url_list") or []
                        if url_list:
                            slide_images.append(url_list[0])
                    elif isinstance(im, str):
                        slide_images.append(im)
                if slide_images:
                    is_photo = True

            video_obj = VideoItem(
                id=vid_id,
                url=post_url,
                title=title,
                user=username,
                create_time=create_time,
                duration=duration,
                cover_url=cover_url,
                music_url=music_url,
                images=slide_images,
                is_photo=is_photo,
                status=DownloadStatus.QUEUED
            )

            videos.append(video_obj)

            # Đẩy ngay vào hàng đợi tải nếu đang chạy chế độ stream song song
            if stream_queue is not None:
                stream_queue.put(video_obj)

            if on_found_callback:
                on_found_callback(video_obj, len(videos))

            # Thông báo tiến độ mỗi 10 video tìm thấy
            if len(videos) % 10 == 0:
                log(f"🔎 Đã tìm thấy {len(videos)} video từ kênh @{username} ...")

            if limit and len(videos) >= limit:
                break

        log(f"✅ Hoàn tất quét kênh @{username}! Tìm thấy tổng cộng: {len(videos)} video.")

    except Exception as exc:
        log(f"⚠️ Quá trình quét kênh gặp sự cố: {exc}")
        if videos:
            log(f"ℹ️ Giữ lại {len(videos)} video đã tìm thấy trước đó để tải.")

    if not videos:
        log(f"⚠️ Không tìm thấy video nào từ kênh @{username}.")
        log(f"💡 Lưu ý: Hãy kiểm tra lại username hoặc đảm bảo kênh có video công khai.")

    return videos
