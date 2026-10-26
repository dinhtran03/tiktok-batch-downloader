from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any

class DownloadStatus(Enum):
    QUEUED = "Chờ tải"
    DOWNLOADING = "Đang tải"
    COMPLETED = "Hoàn thành"
    SKIPPED = "Đã có sẵn (Bỏ qua)"
    FAILED = "Thất bại"

@dataclass
class VideoItem:
    id: str
    url: str
    title: str = ""
    user: str = ""
    create_time: Optional[int] = None
    duration: Optional[int] = None
    download_url: Optional[str] = None
    backup_urls: List[str] = field(default_factory=list)
    cover_url: Optional[str] = None
    music_url: Optional[str] = None
    images: List[str] = field(default_factory=list)
    is_photo: bool = False
    extension: str = "mp4"
    file_path: Optional[str] = None
    status: DownloadStatus = DownloadStatus.QUEUED
    error_message: Optional[str] = None
    bytes_downloaded: int = 0
    total_bytes: int = 0
    
    @property
    def progress_percent(self) -> float:
        if self.total_bytes > 0:
            return (self.bytes_downloaded / self.total_bytes) * 100
        return 0.0

@dataclass
class ChannelInfo:
    username: str
    sec_uid: Optional[str] = None
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    total_videos: int = 0
    url: str = ""

@dataclass
class DownloadOptions:
    output_dir: str
    download_video: bool = True
    download_audio: bool = False
    download_cover: bool = False
    save_metadata: bool = False
    skip_existing: bool = True
    max_workers: int = 3
    limit_videos: Optional[int] = None  # None = all videos
    naming_template: str = "{user}_{id}"
