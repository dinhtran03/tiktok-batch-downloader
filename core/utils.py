import re
import os
from datetime import datetime, timezone
from typing import List, Optional

def sanitize_filename(name: str, max_length: int = 80) -> str:
    """Loại bỏ ký tự không hợp lệ trong tên tệp trên Windows và cắt gọn."""
    if not name:
        return "tiktok_video"
    # Loại bỏ ký tự cấm: < > : " / \ | ? * và các ký tự điều khiển
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    # Rút gọn khoảng trắng
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip()
    return cleaned or "tiktok_video"

def extract_channel_username(url_or_name: str) -> Optional[str]:
    """
    Trích xuất username từ link kênh TikTok hoặc chuỗi nhập.
    Ví dụ:
      - https://www.tiktok.com/@openai?lang=en -> openai
      - https://tiktok.com/@khaby.lame -> khaby.lame
      - @user_name -> user_name
      - user_name -> user_name
    """
    if not url_or_name:
        return None
    s = url_or_name.strip()
    
    # Bỏ query params và hash
    s = s.split('?')[0].split('#')[0].rstrip('/')
    
    # Match tiktok.com/@username
    m = re.search(r'tiktok\.com/@([\w_.-]+)', s, re.IGNORECASE)
    if m:
        return m.group(1)
        
    # Match @username
    if s.startswith('@'):
        clean = s[1:].strip()
        if re.match(r'^[\w_.-]+$', clean):
            return clean
            
    # Match direct username (không chứa khoảng trắng hay http)
    if not s.startswith('http') and re.match(r'^[\w_.-]+$', s):
        return s
        
    return None

def extract_channel_list_from_text(text: str) -> List[str]:
    """
    Trích xuất danh sách username các kênh từ văn bản (mỗi dòng hoặc phân tách bởi dấu phẩy).
    Hỗ trợ đầy đủ các định dạng:
      - https://www.tiktok.com/@username
      - https://tiktok.com/@username?lang=en
      - @username
      - username
    Loại bỏ khoảng trắng, dòng trống, ghi chú (#...) và trùng lặp nhưng giữ nguyên thứ tự.
    """
    if not text:
        return []
        
    channels: List[str] = []
    seen = set()
    
    raw_lines = re.split(r'[\r\n,]+', text)
    for line in raw_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        uname = extract_channel_username(line)
        if uname and uname.lower() not in seen:
            seen.add(uname.lower())
            channels.append(uname)
            
    return channels

def extract_video_urls_from_text(text: str) -> List[str]:
    """Tìm tất cả các link video TikTok trong văn bản."""
    pattern = re.compile(
        r'https?://(?:(?:www|m|v[tm])\.)?tiktok\.com/(?:@[\w_.-]+/video/\d+|[\w_.-]+/video/\d+|v/\d+|\S+)',
        re.IGNORECASE
    )
    found = pattern.findall(text)
    # Loại bỏ ký tự thừa ở cuối URL nếu có
    clean_urls = []
    for u in found:
        u = u.strip().rstrip('.,;:)"\'')
        if u and u not in clean_urls:
            clean_urls.append(u)
    return clean_urls

def format_bytes(num_bytes: int) -> str:
    """Đổi kích thước bytes sang chuỗi hiển thị B, KB, MB, GB."""
    if num_bytes <= 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"

def format_timestamp(timestamp: Optional[int]) -> str:
    """Đổi timestamp thành YYYY-MM-DD."""
    if not timestamp:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def is_valid_mp4(file_path: str) -> bool:
    """
    Kiểm tra xem tệp có phải là video MP4/MOV hợp lệ có luồng video hay không.
    - Tệp phải tồn tại và có kích thước > 2048 bytes.
    - Trong 64 bytes đầu tiên phải chứa chuỗi 'ftyp' (ISO Base Media File Format).
    - Không được là tệp âm thanh thuần túy (ID3, v.v.).
    """
    if not file_path or not os.path.exists(file_path):
        return False
    try:
        sz = os.path.getsize(file_path)
        if sz < 2048:
            return False
        with open(file_path, "rb") as f:
            header = f.read(64)
            if header.startswith(b"ID3"):
                return False
            return b"ftyp" in header
    except Exception:
        return False

def is_audio_file(file_path: str) -> bool:
    """
    Kiểm tra xem tệp có phải là tệp âm thanh thuần túy (MP3, AAC, v.v.) hay không.
    """
    if not file_path or not os.path.exists(file_path):
        return False
    try:
        if os.path.getsize(file_path) < 16:
            return False
        with open(file_path, "rb") as f:
            hdr = f.read(16)
            if hdr.startswith(b"ID3"):
                return True
            if len(hdr) >= 2 and hdr[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xf1", b"\xff\xf9"):
                return True
    except Exception:
        pass
    return False

