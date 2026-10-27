import os
import sys
import re
import shutil
import tempfile
import threading
import subprocess
from typing import List, Tuple, Dict, Any, Optional, Callable, Union

from .utils import is_valid_mp4

# Khóa đa luồng cho các mô hình AI (Whisper & RapidOCR)
_WHISPER_MODEL = None
_WHISPER_LOCK = threading.Lock()
_OCR_ENGINE = None
_OCR_LOCK = threading.Lock()

def get_default_sticker_path() -> str:
    """Trả về đường dẫn tới ảnh sticker/logo mặc định."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(getattr(sys, "_MEIPASS", ""), "assets", "default_sticker.png"),
        os.path.join(base_dir, "assets", "default_sticker.png"),
        os.path.join(os.getcwd(), "assets", "default_sticker.png"),
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return os.path.abspath(p)
    return ""

def get_whisper_model(model_size: str = "tiny"):
    """Tải và lưu trữ mô hình Faster-Whisper trong bộ nhớ đệm (Singleton)."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        with _WHISPER_LOCK:
            if _WHISPER_MODEL is None:
                from faster_whisper import WhisperModel
                _WHISPER_MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _WHISPER_MODEL

def get_ocr_engine():
    """Tải và lưu trữ bộ máy RapidOCR trong bộ nhớ đệm (Singleton)."""
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        with _OCR_LOCK:
            if _OCR_ENGINE is None:
                from rapidocr_onnxruntime import RapidOCR
                _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE

def normalize_text(text: str) -> str:
    """Chuẩn hóa chuỗi văn bản: chuyển chữ thường, loại bỏ ký tự đặc biệt."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def parse_keyword_phrases(raw_keywords: Union[str, List[str]]) -> List[List[str]]:
    """
    Chuyển đổi chuỗi từ khóa (hoặc danh sách) thành các cụm tokens chuẩn hóa.
    Ví dụ: "tiktok, tik tok, tóp tóp, toptop" -> [["tiktok"], ["tik", "tok"], ["tóp", "tóp"], ["toptop"]]
    """
    if isinstance(raw_keywords, str):
        items = [k.strip() for k in raw_keywords.split(",") if k.strip()]
    else:
        items = list(raw_keywords)

    phrases = []
    for item in items:
        norm = normalize_text(item)
        if norm:
            tokens = norm.split()
            if tokens and tokens not in phrases:
                phrases.append(tokens)
    return phrases

def get_video_duration(video_path: str) -> float:
    """Lấy thời lượng video (giây) thông qua OpenCV hoặc ffprobe."""
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS)
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()
            if fps > 0 and frames > 0:
                return float(frames / fps)
    except Exception:
        pass

    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return float(res.stdout.strip())
    except Exception:
        pass

    return 0.0

def load_audio_for_whisper(file_path: str, sr: int = 16000):
    """
    Trích xuất và nạp dữ liệu âm thanh trực tiếp bằng ffmpeg (16kHz mono float32),
    tương thích 100% với Whisper mà không phụ thuộc vào thư viện PyAV decoding.
    """
    try:
        cmd = [
            "ffmpeg", "-nostdin", "-threads", "0",
            "-i", file_path,
            "-f", "s16le", "-ac", "1", "-acodec", "pcm_s16le", "-ar", str(sr),
            "-"
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode == 0 and res.stdout:
            import numpy as np
            audio = np.frombuffer(res.stdout, np.int16).flatten().astype(np.float32) / 32768.0
            return audio
    except Exception:
        pass
    return None

def detect_spoken_segments(
    video_path: str,
    keyword_phrases: List[List[str]],
    log_callback: Optional[Callable[[str], None]] = None
) -> List[Tuple[float, float]]:
    """
    Sử dụng faster-whisper để phát hiện các phân đoạn âm thanh chứa từ khóa.
    Trả về danh sách các khoảng thời gian cần cắt: [(start_sec, end_sec), ...]
    """
    if not keyword_phrases or not os.path.exists(video_path):
        return []

    if log_callback:
        log_callback("🎙️ Đang phân tích nhận diện giọng nói (Whisper AI) để tìm từ khóa nhạy cảm...")

    try:
        audio_arr = load_audio_for_whisper(video_path, 16000)
        if audio_arr is None or len(audio_arr) == 0:
            return []
        model = get_whisper_model("tiny")
        segments, info = model.transcribe(audio_arr, word_timestamps=True)
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ Nhận diện giọng nói gặp lỗi: {e}")
        return []

    total_duration = info.duration or get_video_duration(video_path)
    all_words: List[Tuple[float, float, str]] = []

    for seg in segments:
        if not seg.words:
            continue
        for w in seg.words:
            w_text = normalize_text(w.word)
            if w_text:
                all_words.append((w.start, w.end, w_text))

    if not all_words:
        return []

    # Tìm các vị trí khớp từ khóa
    cut_intervals: List[Tuple[float, float]] = []

    for phrase in keyword_phrases:
        p_len = len(phrase)
        if p_len == 1:
            target_kw = phrase[0]
            for idx, (st, en, w_text) in enumerate(all_words):
                if target_kw == w_text or target_kw in w_text:
                    cut_intervals.append((st, en))
        else:
            for idx in range(len(all_words) - p_len + 1):
                match = True
                for p_idx in range(p_len):
                    if all_words[idx + p_idx][2] != phrase[p_idx]:
                        match = False
                        break
                if match:
                    st = all_words[idx][0]
                    en = all_words[idx + p_len - 1][1]
                    cut_intervals.append((st, en))

    if not cut_intervals:
        return []

    # Thêm đệm thời gian (padding) để không bị ngắt cụt âm
    PAD_BEFORE = 0.15  # giây
    PAD_AFTER = 0.20   # giây
    padded: List[Tuple[float, float]] = []
    for st, en in cut_intervals:
        s = max(0.0, st - PAD_BEFORE)
        e = min(total_duration, en + PAD_AFTER) if total_duration > 0 else en + PAD_AFTER
        padded.append((s, e))

    # Gộp các khoảng trùng lặp hoặc sát nhau (< 0.35s)
    padded.sort(key=lambda x: x[0])
    merged: List[Tuple[float, float]] = []
    for s, e in padded:
        if not merged:
            merged.append((s, e))
        else:
            prev_s, prev_e = merged[-1]
            if s <= prev_e + 0.35:
                merged[-1] = (prev_s, max(prev_e, e))
            else:
                merged.append((s, e))

    if log_callback and merged:
        log_callback(f"✂️ Phát hiện {len(merged)} phân đoạn giọng nói chứa từ khóa: {[(round(s, 2), round(e, 2)) for s, e in merged]}")

    return merged

def cut_video_intervals(
    input_video: str,
    output_video: str,
    cut_intervals: List[Tuple[float, float]],
    log_callback: Optional[Callable[[str], None]] = None
) -> bool:
    """
    Cắt bỏ hoàn toàn cả hình ảnh và âm thanh các khoảng thời gian cut_intervals
    bằng bộ lọc FFmpeg trim/atrim concat đồng bộ khung hình.
    """
    if not cut_intervals:
        shutil.copy2(input_video, output_video)
        return True

    duration = get_video_duration(input_video)
    if duration <= 0:
        if log_callback:
            log_callback("⚠️ Không xác định được thời lượng video để cắt phân đoạn.")
        return False

    # Tính toán các khoảng giữ lại (keep intervals)
    keep_intervals: List[Tuple[float, float]] = []
    current_pos = 0.0

    for s, e in sorted(cut_intervals, key=lambda x: x[0]):
        if s > current_pos + 0.08:
            keep_intervals.append((current_pos, s))
        current_pos = max(current_pos, e)

    if current_pos < duration - 0.08:
        keep_intervals.append((current_pos, duration))

    if not keep_intervals:
        if log_callback:
            log_callback("⚠️ Toàn bộ video đều bị đánh dấu cắt, giữ nguyên video gốc.")
        return False

    if log_callback:
        log_callback(f"🎬 Đang ghép {len(keep_intervals)} phân đoạn sạch (bỏ đoạn nói từ khóa)...")

    # Xây dựng FFmpeg filter_complex
    filter_parts = []
    concat_inputs = []

    for i, (st, en) in enumerate(keep_intervals):
        filter_parts.append(f"[0:v]trim=start={st:.3f}:end={en:.3f},setpts=PTS-STARTPTS[v{i}]")
        filter_parts.append(f"[0:a]atrim=start={st:.3f}:end={en:.3f},asetpts=PTS-STARTPTS[a{i}]")
        concat_inputs.append(f"[v{i}][a{i}]")

    inputs_str = "".join(concat_inputs)
    filter_parts.append(f"{inputs_str}concat=n={len(keep_intervals)}:v=1:a=1[outv][outa]")
    filter_str = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-filter_complex", filter_str,
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_video
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode == 0 and is_valid_mp4(output_video):
            return True
        else:
            if log_callback:
                log_callback(f"⚠️ FFmpeg cắt video thất bại: {res.stderr[:200]}")
            return False
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ Lỗi cắt video: {e}")
        return False

def detect_visual_text(
    video_path: str,
    raw_keywords: Union[str, List[str]],
    sample_interval: float = 0.4,
    log_callback: Optional[Callable[[str], None]] = None
) -> List[Dict[str, Any]]:
    """
    Quét video bằng RapidOCR để tìm các khung hình có chữ từ khóa nhạy cảm.
    Gộp lại thành các khối hiển thị: [{"start": t1, "end": t2, "x": x, "y": y, "w": w, "h": h}]
    """
    if not os.path.exists(video_path):
        return []

    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / fps if total_frames > 0 else 0.0

    if duration <= 0:
        cap.release()
        return []

    if log_callback:
        log_callback(f"🔍 Đang quét thị giác (RapidOCR) tìm chữ trên video ({duration:.1f}s)...")

    # Chuẩn hóa từ khóa tìm kiếm
    if isinstance(raw_keywords, str):
        kw_list = [k.strip().lower() for k in raw_keywords.split(",") if k.strip()]
    else:
        kw_list = [k.lower().strip() for k in raw_keywords if k]

    try:
        ocr = get_ocr_engine()
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ Khởi tạo RapidOCR gặp lỗi: {e}")
        cap.release()
        return []

    detections = []
    step_frames = max(1, int(fps * sample_interval))

    current_frame = 0
    while current_frame < total_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        timestamp = current_frame / fps

        # Tối ưu: Nếu video quá lớn (4K/2K), thu nhỏ để OCR chạy nhanh gấp 4 lần rồi scale tọa độ lại
        orig_h, orig_w = frame.shape[:2]
        scale_ratio = 1.0
        if orig_w > 1280:
            scale_ratio = 1280.0 / orig_w
            new_w = 1280
            new_h = int(orig_h * scale_ratio)
            frame_to_ocr = cv2.resize(frame, (new_w, new_h))
        else:
            frame_to_ocr = frame

        try:
            ocr_res, _ = ocr(frame_to_ocr)
        except Exception:
            ocr_res = None

        if ocr_res:
            for item in ocr_res:
                box = item[0]
                text = str(item[1]).lower()

                # Kiểm tra xem có chứa từ khóa không
                matched = any(kw in text for kw in kw_list)
                if not matched:
                    # Kiểm tra bỏ dấu hoặc khoảng trắng (vd "tik tok" vs "tiktok")
                    clean_item_text = re.sub(r'[\s\W]', '', text)
                    matched = any(re.sub(r'[\s\W]', '', kw) in clean_item_text for kw in kw_list)

                if matched:
                    # Chuyển đổi tọa độ nếu có resize
                    inv_scale = 1.0 / scale_ratio
                    xs = [pt[0] * inv_scale for pt in box]
                    ys = [pt[1] * inv_scale for pt in box]

                    x_min, x_max = min(xs), max(xs)
                    y_min, y_max = min(ys), max(ys)

                    bw = x_max - x_min
                    bh = y_max - y_min

                    # Mở rộng lề 20% để sticker che phủ trọn vẹn và đẹp mắt
                    pad_x = bw * 0.2 + 8
                    pad_y = bh * 0.2 + 8

                    final_x = max(0, int(x_min - pad_x))
                    final_y = max(0, int(y_min - pad_y))
                    final_w = min(video_w - final_x, int(bw + 2 * pad_x))
                    final_h = min(video_h - final_y, int(bh + 2 * pad_y))

                    detections.append({
                        "t": timestamp,
                        "x": final_x,
                        "y": final_y,
                        "w": max(24, final_w),
                        "h": max(24, final_h)
                    })

        current_frame += step_frames

    cap.release()

    if not detections:
        return []

    # Gom các phát hiện liên tiếp thành các khối thời gian [start, end]
    detections.sort(key=lambda d: d["t"])
    merged_blocks: List[Dict[str, Any]] = []

    for d in detections:
        t, x, y, w, h = d["t"], d["x"], d["y"], d["w"], d["h"]
        if not merged_blocks:
            merged_blocks.append({
                "start": max(0.0, t - 0.2),
                "end": min(duration, t + sample_interval + 0.2),
                "x": x, "y": y, "w": w, "h": h
            })
        else:
            last = merged_blocks[-1]
            # Nếu thời gian gần nhau (< 1.2s) và khoảng cách vị trí gần nhau
            dist_x = abs(last["x"] - x)
            dist_y = abs(last["y"] - y)
            if t <= last["end"] + 1.0 and dist_x < 120 and dist_y < 120:
                last["end"] = min(duration, t + sample_interval + 0.2)
                # Mở rộng hộp bao
                nx = min(last["x"], x)
                ny = min(last["y"], y)
                nw = max(last["x"] + last["w"], x + w) - nx
                nh = max(last["y"] + last["h"], y + h) - ny
                last["x"], last["y"], last["w"], last["h"] = nx, ny, nw, nh
            else:
                merged_blocks.append({
                    "start": max(0.0, t - 0.2),
                    "end": min(duration, t + sample_interval + 0.2),
                    "x": x, "y": y, "w": w, "h": h
                })

    if log_callback:
        log_callback(f"🏷️ Phát hiện {len(merged_blocks)} cảnh chứa chữ từ khóa cần che sticker.")

    return merged_blocks

def overlay_stickers(
    input_video: str,
    output_video: str,
    visual_blocks: List[Dict[str, Any]],
    custom_sticker_path: Optional[str] = None,
    log_callback: Optional[Callable[[str], None]] = None
) -> bool:
    """
    Chèn hình ảnh Sticker/Logo tùy chỉnh đè lên các tọa độ chữ trong các khoảng thời gian visual_blocks.
    """
    if not visual_blocks:
        shutil.copy2(input_video, output_video)
        return True

    # Xác định file sticker
    sticker_path = ""
    if custom_sticker_path and os.path.exists(custom_sticker_path):
        sticker_path = custom_sticker_path
    else:
        sticker_path = get_default_sticker_path()

    if not sticker_path or not os.path.exists(sticker_path):
        if log_callback:
            log_callback("⚠️ Không tìm thấy file sticker để chèn che logo.")
        return False

    if log_callback:
        log_callback(f"🎨 Đang chèn sticker ({os.path.basename(sticker_path)}) lên {len(visual_blocks)} vị trí chữ...")

    # Xây dựng filter_complex cho overlay
    filter_chains = []
    curr_v = "0:v"

    for i, blk in enumerate(visual_blocks):
        st, en = blk["start"], blk["end"]
        x, y, w, h = blk["x"], blk["y"], blk["w"], blk["h"]
        # Đảm bảo w, h chẵn
        w = w if w % 2 == 0 else w + 1
        h = h if h % 2 == 0 else h + 1

        filter_chains.append(f"[1:v]scale={w}:{h}[stk{i}]")
        next_v = f"ov_{i}"
        filter_chains.append(f"[{curr_v}][stk{i}]overlay={x}:{y}:enable='between(t,{st:.3f},{en:.3f})'[{next_v}]")
        curr_v = next_v

    filter_str = ";".join(filter_chains)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-i", sticker_path,
        "-filter_complex", filter_str,
        "-map", f"[{curr_v}]",
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_video
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if res.returncode == 0 and is_valid_mp4(output_video):
            return True
        else:
            if log_callback:
                log_callback(f"⚠️ FFmpeg chèn sticker thất bại: {res.stderr[:200]}")
            return False
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ Lỗi chèn sticker: {e}")
        return False

def process_video_censorship(
    video_path: str,
    keywords_str: str = "tiktok, tik tok, tóp tóp, toptop, douyin, tiktokshop, tiktok shop, tik tok shop, tích tốc, tích tốc xốp, tíchtốc, tíchtốcxốp, cháy, nổ",
    custom_sticker_path: Optional[str] = None,
    log_callback: Optional[Callable[[str], None]] = None
) -> bool:
    """
    Quy trình xử lý kiểm duyệt video hoàn chỉnh:
    1. Phát hiện và cắt bỏ các phân đoạn nói từ khóa (cắt cả hình ảnh và âm thanh).
    2. Quét OCR nhận diện chữ trên khung hình video đã cắt.
    3. Dán đè sticker lên vị trí chữ.
    4. Cập nhật đè lên file video gốc một cách an toàn.
    """
    if not video_path or not os.path.exists(video_path):
        return False

    temp_dir = tempfile.mkdtemp(prefix="tt_censor_")
    try:
        current_source = video_path
        modifications_made = False

        # Bước 1: Phát hiện giọng nói
        phrases = parse_keyword_phrases(keywords_str)
        spoken_cuts = detect_spoken_segments(current_source, phrases, log_callback)

        # Bước 2: Cắt bỏ phân đoạn nói
        if spoken_cuts:
            cut_temp = os.path.join(temp_dir, "audio_cut.mp4")
            if cut_video_intervals(current_source, cut_temp, spoken_cuts, log_callback):
                current_source = cut_temp
                modifications_made = True
            else:
                if log_callback:
                    log_callback("⚠️ Bỏ qua bước cắt âm thanh do lỗi xử lý, tiếp tục quét chữ...")

        # Bước 3: Quét thị giác tìm chữ
        visual_blocks = detect_visual_text(current_source, keywords_str, sample_interval=0.4, log_callback=log_callback)

        # Bước 4: Chèn Sticker che chữ
        if visual_blocks:
            overlay_temp = os.path.join(temp_dir, "overlay_sticker.mp4")
            if overlay_stickers(current_source, overlay_temp, visual_blocks, custom_sticker_path, log_callback):
                current_source = overlay_temp
                modifications_made = True
            else:
                if log_callback:
                    log_callback("⚠️ Bỏ qua bước dán sticker do lỗi xử lý...")

        # Nếu có chỉnh sửa, lưu đè lên file video chính
        if modifications_made and os.path.exists(current_source):
            if is_valid_mp4(current_source):
                backup_path = video_path + ".orig.bak"
                try:
                    os.rename(video_path, backup_path)
                    shutil.copy2(current_source, video_path)
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    if log_callback:
                        log_callback(f"✨ Hoàn tất xử lý lọc video: Cắt {len(spoken_cuts)} đoạn nói, che {len(visual_blocks)} vị trí chữ!")
                    return True
                except Exception as ex:
                    if os.path.exists(backup_path) and not os.path.exists(video_path):
                        os.rename(backup_path, video_path)
                    if log_callback:
                        log_callback(f"⚠️ Không thể lưu đè file video: {ex}")
                    return False
        else:
            if log_callback:
                log_callback("ℹ️ Video không chứa từ khóa nhạy cảm trong giọng nói hoặc chữ trên màn hình.")
            return True

    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ Quá trình lọc video gặp sự cố: {e}")
        return False
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
