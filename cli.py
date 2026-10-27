#!/usr/bin/env python3
"""
TikTok Batch Channel Downloader - CLI Interface (Turbo Edition)
"""
import argparse
import sys
import os
import queue
import threading
from typing import List

from core.models import VideoItem, DownloadOptions, DownloadStatus
from core.utils import extract_channel_username, extract_channel_list_from_text, extract_video_urls_from_text
from core.scanner import scan_channel_videos
from core.downloader import BatchDownloader

def main():
    parser = argparse.ArgumentParser(
        description="Ứng dụng tải video hàng loạt từ kênh TikTok siêu tốc không watermark"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-c", "--channel",
        type=str,
        help="Link kênh TikTok hoặc danh sách username phân cách bởi dấu phẩy (vd: @dung.mat_ket_noi, @openai)"
    )
    group.add_argument(
        "-cf", "--channels-file",
        type=str,
        help="Đường dẫn đến file .txt chứa danh sách link kênh hoặc username TikTok (mỗi kênh 1 dòng)"
    )
    group.add_argument(
        "-f", "--file",
        type=str,
        help="Đường dẫn đến file .txt chứa danh sách link video TikTok (mỗi link 1 dòng)"
    )
    group.add_argument(
        "-u", "--url",
        type=str,
        help="Link của 1 video TikTok đơn lẻ cần tải không watermark"
    )
    group.add_argument(
        "--repair",
        action="store_true",
        help="Quét và sửa lại các video trong thư mục output bị lỗi chỉ có tiếng (tải lại bản video chuẩn)"
    )

    parser.add_argument(
        "-o", "--output",
        type=str,
        default="./downloads",
        help="Thư mục lưu video tải về (mặc định: ./downloads)"
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=None,
        help="Số lượng video tối đa cần tải (mặc định: tải toàn bộ kênh)"
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=6,
        help="Số luồng tải song song (mặc định: 6 luồng, tối đa 16)"
    )
    parser.add_argument(
        "--turbo",
        action="store_true",
        help="Kích hoạt chế độ siêu tốc Turbo (tương đương 12 luồng đồng thời)"
    )
    parser.add_argument(
        "--browser",
        type=str,
        default=None,
        choices=["chrome", "edge", "firefox", "brave"],
        help="Nạp Cookie từ trình duyệt để chống chặn bot hoàn toàn (vd: --browser chrome hoặc --browser edge)"
    )
    parser.add_argument(
        "--audio",
        action="store_true",
        help="Tải thêm tệp âm thanh gốc (.mp3)"
    )
    parser.add_argument(
        "--cover",
        action="store_true",
        help="Tải thêm ảnh bìa thumbnail (.jpg)"
    )
    parser.add_argument(
        "--meta",
        action="store_true",
        help="Lưu file thông tin chi tiết (.json)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Tải lại ngay cả khi tệp đã tồn tại (không bỏ qua)"
    )
    parser.add_argument(
        "--censor",
        action="store_true",
        help="Kích hoạt tự động lọc từ nhạy cảm 'tiktok' (Cắt đoạn nói & Che logo chữ bằng sticker)"
    )
    parser.add_argument(
        "--censor-keywords",
        type=str,
        default="tiktok, tik tok, tóp tóp, toptop, douyin, tiktokshop, tiktok shop, tik tok shop, tích tốc, tích tốc xốp, tíchtốc, tíchtốcxốp, cháy, nổ",
        help="Danh sách từ khóa cần lọc, phân cách bởi dấu phẩy (mặc định: 'tiktok, tik tok, tóp tóp, toptop, douyin, tiktokshop, tiktok shop, tik tok shop, tích tốc, tích tốc xốp, tíchtốc, tíchtốcxốp, cháy, nổ')"
    )
    parser.add_argument(
        "--sticker",
        type=str,
        default=None,
        help="Đường dẫn file ảnh Logo / Sticker che chữ (mặc định: dùng sticker có sẵn trong app)"
    )

    args = parser.parse_args()

    # Xác định thư mục đích
    dest_dir = os.path.abspath(args.output)
    num_workers = 12 if args.turbo else max(1, min(16, args.workers))

    # Chế độ sửa chữa các video bị lỗi chỉ có tiếng
    if args.repair:
        from repair_audio_files import scan_corrupted_files, repair_single_file
        print("=" * 65)
        print(f"🔍 Đang quét các tệp video bị lỗi chỉ có tiếng trong: {dest_dir}")
        corrupted = scan_corrupted_files(dest_dir)
        total = len(corrupted)
        if total == 0:
            print("🎉 Tuyệt vời! Không tìm thấy tệp video nào bị lỗi chỉ có tiếng.")
            return
        print(f"⚠️ Phát hiện {total} tệp video bị lỗi. Đang tải lại video MP4 chuẩn...")
        repaired = 0
        for idx, (fpath, uname, vid_id) in enumerate(corrupted, 1):
            print(f"[{idx}/{total}] Đang sửa: {os.path.basename(fpath)} ...")
            if repair_single_file(fpath, uname, vid_id):
                repaired += 1
        print("=" * 65)
        print(f"🎉 Hoàn tất sửa chữa! Đã khắc phục thành công: {repaired}/{total} video.")
        print("=" * 65)
        return

    # 1. Chế độ tải theo Kênh hoặc Danh sách Kênh (Pipelined Streaming)
    channels = []
    if args.channels_file:
        if not os.path.isfile(args.channels_file):
            print(f"[ERROR] Tệp không tồn tại: {args.channels_file}")
            sys.exit(1)
        with open(args.channels_file, "r", encoding="utf-8") as f:
            channels = extract_channel_list_from_text(f.read())
    elif args.channel:
        channels = extract_channel_list_from_text(args.channel)

    if channels:
        total_channels = len(channels)
        print("=" * 65)
        print(f"🎬 BẮT ĐẦU TẢI DANH SÁCH {total_channels} KÊNH TIKTOK (CHẾ ĐỘ PIPELINE SIÊU TỐC)")
        print(f"📁 Thư mục gốc lưu trữ: {dest_dir}")
        print(f"⚡ Số luồng tải: {num_workers} luồng đồng thời | Buffer: 1 MB/chunk")
        print("=" * 65)

        grand_total = 0
        grand_completed = 0
        grand_skipped = 0
        grand_failed = 0

        for ch_idx, username in enumerate(channels, 1):
            print(f"\n{'='*55}")
            print(f"🎬 [{ch_idx}/{total_channels}] Đang quét & tải kênh @{username} ...")
            print(f"{'='*55}")

            channel_dir = os.path.join(dest_dir, f"@{username}")
            options = DownloadOptions(
                output_dir=channel_dir,
                download_video=True,
                download_audio=args.audio,
                download_cover=args.cover,
                save_metadata=args.meta,
                skip_existing=not args.force,
                max_workers=num_workers,
                limit_videos=args.limit,
                enable_censorship=args.censor,
                censor_keywords=args.censor_keywords,
                custom_sticker_path=args.sticker
            )

            downloader = BatchDownloader(options, browser_cookie=args.browser)
            downloader.log_callback = lambda msg: print(f"[*] {msg}")

            stream_queue = queue.Queue()
            channel_items = []
            channel_lock = threading.Lock()

            def on_video_found(v: VideoItem, count: int):
                with channel_lock:
                    channel_items.append(v)

            def _run_downloader():
                downloader.download_from_stream_queue(
                    item_queue=stream_queue,
                    get_total_callback=lambda: len(channel_items)
                )

            dl_thread = threading.Thread(target=_run_downloader, daemon=True)
            dl_thread.start()

            scan_channel_videos(
                channel_input=f"https://www.tiktok.com/@{username}",
                limit=args.limit,
                on_found_callback=on_video_found,
                log_callback=downloader.log,
                stream_queue=stream_queue,
                browser_cookie=args.browser
            )

            for _ in range(num_workers):
                stream_queue.put(None)

            dl_thread.join()

            grand_total += len(channel_items)
            grand_completed += downloader.completed_count
            grand_skipped += downloader.skipped_count
            grand_failed += downloader.failed_count

            print(f"✅ [{ch_idx}/{total_channels}] Hoàn tất kênh @{username}: Tải mới {downloader.completed_count} | Bỏ qua {downloader.skipped_count} | Lỗi {downloader.failed_count}")

        print("\n" + "=" * 65)
        print(f"📊 TỔNG KẾT TOÀN BỘ {total_channels} KÊNH:")
        print(f"   - Tổng video phát hiện: {grand_total}")
        print(f"   - Tải mới thành công : {grand_completed}")
        print(f"   - Đã có sẵn (bỏ qua)  : {grand_skipped}")
        print(f"   - Lỗi                 : {grand_failed}")
        print(f"📂 Thư mục gốc lưu trữ: {dest_dir}")
        print(f"📄 Danh sách tên video (.txt): {os.path.join(dest_dir, 'downloaded_videos.txt')}")
        print("=" * 65)
        sys.exit(0)

    # 2. Chế độ tải từ File danh sách link hoặc Link đơn lẻ
    videos_to_download: List[VideoItem] = []
    if args.file:
        if not os.path.isfile(args.file):
            print(f"[ERROR] Tệp không tồn tại: {args.file}")
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
        raw_urls = extract_video_urls_from_text(content)
        print(f"[*] Đã trích xuất {len(raw_urls)} link từ tệp: {args.file}")
        for idx, u in enumerate(raw_urls, 1):
            vid_id = u.split("/video/")[-1].split("?")[0] if "/video/" in u else str(idx)
            videos_to_download.append(VideoItem(id=vid_id, url=u))

    elif args.url:
        u = args.url.strip()
        vid_id = u.split("/video/")[-1].split("?")[0] if "/video/" in u else "video"
        videos_to_download.append(VideoItem(id=vid_id, url=u))

    options = DownloadOptions(
        output_dir=dest_dir,
        download_video=True,
        download_audio=args.audio,
        download_cover=args.cover,
        save_metadata=args.meta,
        skip_existing=not args.force,
        max_workers=num_workers,
        limit_videos=args.limit,
        enable_censorship=args.censor,
        censor_keywords=args.censor_keywords,
        custom_sticker_path=args.sticker
    )

    downloader = BatchDownloader(options, browser_cookie=args.browser)
    downloader.log_callback = lambda msg: print(f"[*] {msg}")

    stats = downloader.download_batch(videos_to_download)
    print("\n" + "=" * 65)
    print(f"📊 KẾT QUẢ: Tổng: {stats['total']} | Thành công: {stats['completed']} | Bỏ qua: {stats['skipped']} | Lỗi: {stats['failed']}")
    print(f"📂 Video được lưu tại: {dest_dir}")
    print(f"📄 Danh sách tên video (.txt): {os.path.join(dest_dir, 'downloaded_videos.txt')}")
    print("=" * 65)

if __name__ == "__main__":
    main()
