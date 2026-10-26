import requests
import re
import time
import logging
import threading
from typing import Optional, List, Dict, Any
from .models import VideoItem, DownloadStatus

logger = logging.getLogger(__name__)

TIKWM_API_URL = "https://www.tikwm.com/api/"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://www.tikwm.com/",
}

# Khóa đồng bộ và bộ điều tiết tần suất gọi API (Rate Limiter)
# TikWM giới hạn nghiêm ngặt 1 yêu cầu / giây trên mỗi IP.
# Bộ điều tiết đảm bảo giữa 2 lần gọi liên tiếp luôn cách nhau tối thiểu 1.15 giây trên mọi luồng.
_tikwm_lock = threading.Lock()
_last_tikwm_time = 0.0

_ssstik_lock = threading.Lock()
_last_ssstik_time = 0.0

# Bộ nhớ đệm kết quả trích xuất để tránh gọi lại nhiều lần cho cùng một URL (giới hạn dung lượng RAM)
_cache_lock = threading.Lock()
_resolution_cache: Dict[str, VideoItem] = {}
MAX_CACHE_ENTRIES = 500

def _add_to_cache(url: str, item: VideoItem):
    """Lưu vào cache kết quả phân tích, tự động dọn dẹp để RAM luôn siêu nhẹ."""
    with _cache_lock:
        if len(_resolution_cache) >= MAX_CACHE_ENTRIES:
            for k in list(_resolution_cache.keys())[:100]:
                _resolution_cache.pop(k, None)
        _resolution_cache[url] = item

def _rate_limit_tikwm(min_interval: float = 1.15):
    """Đảm bảo khoảng cách giữa các lần gọi TikWM tối thiểu 1.15 giây (chống lỗi code: -1)."""
    global _last_tikwm_time
    with _tikwm_lock:
        now = time.time()
        elapsed = now - _last_tikwm_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_tikwm_time = time.time()

def _rate_limit_ssstik(min_interval: float = 0.8):
    """Điều tiết tần suất gọi SSSTik chống nghẽn mạng và chặn bot."""
    global _last_ssstik_time
    with _ssstik_lock:
        now = time.time()
        elapsed = now - _last_ssstik_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_ssstik_time = time.time()

def resolve_with_tikwm(tiktok_url: str, timeout: int = 15, max_retries: int = 3) -> Optional[VideoItem]:
    """
    Sử dụng TikWM API để lấy link tải video gốc không watermark.
    - Tích hợp Rate Limiting 1 req/sec chống lỗi: 'code: -1, Free Api Limit: 1 request/second.'
    - Tự động thử lại (Retry with backoff) nếu máy chủ bận.
    - Hỗ trợ đầy đủ bài đăng dạng Slide ảnh (Carousel/Photo post) trích xuất danh sách ảnh và nhạc nền.
    - Ưu tiên link 'play' trước 'hdplay' (tránh lỗi HTTP 403 Forbidden của TikTok CDN).
    """
    for attempt in range(max_retries):
        _rate_limit_tikwm()
        try:
            params = {"url": tiktok_url, "hd": 1}
            resp = requests.get(TIKWM_API_URL, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
            if resp.status_code != 200:
                time.sleep(1.0)
                continue
                
            data_json = resp.json()
            code = data_json.get("code")

            # Nếu bị dính giới hạn tần suất API (code: -1), chờ 1.5s rồi thử lại
            if code == -1:
                logger.warning(f"TikWM rate limit hit for {tiktok_url}. Đang chờ 1.5s để thử lại (lần {attempt + 1}/{max_retries})...")
                time.sleep(1.5)
                continue

            if code != 0 or not data_json.get("data"):
                return None
                
            d = data_json["data"]
            vid_id = str(d.get("id") or "")
            title = d.get("title") or ""
            author = d.get("author", {})
            user = author.get("unique_id") or author.get("nickname") or ""
            
            # Thu thập danh sách các link video ứng viên
            candidate_urls = []
            
            # 1. 'play': Luôn mở public và không bị khóa theo IP
            play_url = d.get("play")
            if play_url:
                if play_url.startswith("/"):
                    play_url = "https://www.tikwm.com" + play_url
                candidate_urls.append(play_url)
                
            # 2. 'hdplay': HD bitrate (dùng làm dự phòng)
            hdplay_url = d.get("hdplay")
            if hdplay_url:
                if hdplay_url.startswith("/"):
                    hdplay_url = "https://www.tikwm.com" + hdplay_url
                if hdplay_url not in candidate_urls:
                    candidate_urls.append(hdplay_url)
                    
            # Link nhạc nền
            music_url = d.get("music")
            if music_url and music_url.startswith("/"):
                music_url = "https://www.tikwm.com" + music_url
                
            # Link ảnh bìa
            cover_url = d.get("cover")
            if cover_url and cover_url.startswith("/"):
                cover_url = "https://www.tikwm.com" + cover_url

            # Danh sách ảnh slide (nếu là bài đăng dạng Album ảnh / Photo Carousel)
            raw_images = d.get("images") or []
            slide_images = []
            for img in raw_images:
                if img:
                    if img.startswith("/"):
                        img = "https://www.tikwm.com" + img
                    slide_images.append(img)

            primary_url = candidate_urls[0] if candidate_urls else None
            backup_urls = candidate_urls[1:] if len(candidate_urls) > 1 else []

            return VideoItem(
                id=vid_id,
                url=tiktok_url,
                title=title,
                user=user,
                create_time=d.get("create_time"),
                duration=d.get("duration"),
                download_url=primary_url,
                backup_urls=backup_urls,
                cover_url=cover_url,
                music_url=music_url,
                images=slide_images,
                is_photo=bool(slide_images),
                status=DownloadStatus.QUEUED,
            )
        except Exception as exc:
            logger.debug(f"TikWM resolve error on attempt {attempt + 1} for {tiktok_url}: {exc}")
            time.sleep(1.0)

    return None

def resolve_with_ssstik(tiktok_url: str, timeout: int = 15, max_retries: int = 2) -> Optional[VideoItem]:
    """
    Cơ chế dự phòng 1: Trích xuất link không watermark qua máy chủ SSSTik.
    Được đồng bộ nhịp gọi để tránh bị chặn 429 hoặc Cloudflare.
    """
    for attempt in range(max_retries):
        _rate_limit_ssstik()
        try:
            s = requests.Session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            }
            r_page = s.get("https://ssstik.io/en", headers=headers, timeout=timeout)
            if r_page.status_code != 200:
                time.sleep(1.0)
                continue
                
            tt_match = re.search(r's_tt\s*=\s*["\']([^"\']+)["\']', r_page.text) or re.search(r'"tt":\s*"([^"]+)"', r_page.text)
            tt_val = tt_match.group(1) if tt_match else "0"
            
            post_data = {"id": tiktok_url, "locale": "en", "tt": tt_val}
            r_dl = s.post("https://ssstik.io/abc?url=dl", data=post_data, headers=headers, timeout=timeout)
            if r_dl.status_code != 200:
                time.sleep(1.0)
                continue
                
            links = re.findall(r'href="([^"]+)"[^>]*class="[^"]*without_watermark[^"]*"', r_dl.text)
            if not links:
                links = re.findall(r'href="(https://tikcdn\.io/[^"]+)"', r_dl.text)
                
            if not links:
                # Kiểm tra xem có phải bài đăng ảnh không
                slide_imgs = re.findall(r'data-splide-lazy="([^"]+)"', r_dl.text) or re.findall(r'href="([^"]+)"[^>]*download="image', r_dl.text)
                if not slide_imgs:
                    return None
                m_id = re.search(r'/(?:video|photo)/(\d+)', tiktok_url)
                vid_id = m_id.group(1) if m_id else ""
                return VideoItem(
                    id=vid_id,
                    url=tiktok_url,
                    images=slide_imgs,
                    is_photo=True,
                    status=DownloadStatus.QUEUED
                )
                
            title_m = re.search(r'<p class="maintext">([^<]+)</p>', r_dl.text)
            title = title_m.group(1).strip() if title_m else ""

            m_id = re.search(r'/(?:video|photo)/(\d+)', tiktok_url)
            vid_id = m_id.group(1) if m_id else ""

            return VideoItem(
                id=vid_id,
                url=tiktok_url,
                title=title,
                download_url=links[0],
                backup_urls=links[1:] if len(links) > 1 else [],
                status=DownloadStatus.QUEUED
            )
        except Exception as exc:
            logger.debug(f"SSSTik resolve error on attempt {attempt + 1} for {tiktok_url}: {exc}")
            time.sleep(1.0)

    return None

def resolve_video_info(tiktok_url: str) -> Optional[VideoItem]:
    """
    Hệ thống trích xuất đa tầng siêu tốc có bộ nhớ đệm:
    - Tầng 1: TikWM (Tối ưu hóa thứ tự link, chống lỗi 403, có rate limiter & auto-retry)
    - Tầng 2: SSSTik (Dự phòng link proxy sạch watermark)
    """
    with _cache_lock:
        if tiktok_url in _resolution_cache:
            cached = _resolution_cache[tiktok_url]
            # Trả về một bản sao VideoItem để không bị ảnh hưởng trạng thái tải
            return VideoItem(
                id=cached.id,
                url=cached.url,
                title=cached.title,
                user=cached.user,
                create_time=cached.create_time,
                duration=cached.duration,
                download_url=cached.download_url,
                backup_urls=list(cached.backup_urls),
                cover_url=cached.cover_url,
                music_url=cached.music_url,
                images=list(cached.images),
                is_photo=cached.is_photo,
                status=DownloadStatus.QUEUED
            )

    # 1. Thử qua TikWM trước (tỷ lệ thành công 99.9% khi có rate limiting)
    res = resolve_with_tikwm(tiktok_url)
    if res and (res.download_url or res.images):
        _add_to_cache(tiktok_url, res)
        return res
        
    # 2. Thử qua SSSTik nếu TikWM không có kết quả
    res = resolve_with_ssstik(tiktok_url)
    if res and (res.download_url or res.images):
        _add_to_cache(tiktok_url, res)
        return res
        
    return None
