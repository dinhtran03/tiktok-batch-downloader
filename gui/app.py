import os
import sys
import threading
import time
import queue
from typing import Optional, List

import customtkinter as ctk
from tkinter import filedialog, messagebox

# Import core modules
from core.models import VideoItem, DownloadOptions, DownloadStatus
from core.utils import extract_channel_username, extract_channel_list_from_text, extract_video_urls_from_text, format_bytes
from core.scanner import scan_channel_videos
from core.downloader import BatchDownloader

# Cài đặt giao diện CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class TikTokDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Cấu hình cửa sổ
        self.title("TikTok Downloader Pro - Tải Kênh Siêu Tốc Không Watermark")
        self.geometry("1020x760")
        self.minsize(880, 660)

        # Thiết lập biểu tượng ứng dụng (icon)
        for icon_path in [
            os.path.join(getattr(sys, "_MEIPASS", ""), "app_icon.ico"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app_icon.ico"),
            os.path.join(os.getcwd(), "app_icon.ico"),
        ]:
            if os.path.exists(icon_path):
                try:
                    self.iconbitmap(icon_path)
                    break
                except Exception:
                    pass

        # Trạng thái tải
        self.active_downloader: Optional[BatchDownloader] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()
        self.is_running = False
        self.current_session_id = 0

        # Thư mục lưu mặc định
        default_dl_dir = os.path.abspath(os.path.join(os.getcwd(), "downloads"))
        self.output_dir_var = ctk.StringVar(value=default_dl_dir)

        # Tùy chọn lọc từ khóa nhạy cảm / bản quyền ('tiktok')
        self.enable_censor_var = ctk.BooleanVar(value=False)
        self.censor_keywords_var = ctk.StringVar(value="tiktok, tik tok, tóp tóp, toptop, douyin, tiktokshop, tiktok shop, tik tok shop, cháy, nổ")
        self.custom_sticker_var = ctk.StringVar(value="")

        # Xây dựng giao diện
        self._build_ui()

    def _build_ui(self):
        # 1. Header Frame
        header_frame = ctk.CTkFrame(self, corner_radius=10)
        header_frame.pack(fill="x", padx=15, pady=(15, 8))

        title_label = ctk.CTkLabel(
            header_frame,
            text="⚡ TIKTOK BATCH CHANNEL DOWNLOADER (TURBO)",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(side="left", padx=15, pady=10)

        subtitle_label = ctk.CTkLabel(
            header_frame,
            text="Quét & Tải song song siêu tốc | 100% Sạch Watermark HD",
            font=ctk.CTkFont(size=12),
            text_color="#64B5F6"
        )
        subtitle_label.pack(side="left", padx=(0, 15), pady=10)

        theme_switch = ctk.CTkOptionMenu(
            header_frame,
            values=["Dark", "Light", "System"],
            width=90,
            command=self._change_theme
        )
        theme_switch.set("Dark")
        theme_switch.pack(side="right", padx=15, pady=10)

        # 2. Thư mục lưu Frame
        dest_frame = ctk.CTkFrame(self, corner_radius=10)
        dest_frame.pack(fill="x", padx=15, pady=5)

        dest_label = ctk.CTkLabel(dest_frame, text="📁 Thư mục lưu:", font=ctk.CTkFont(weight="bold"))
        dest_label.pack(side="left", padx=(15, 5), pady=10)

        self.dest_entry = ctk.CTkEntry(dest_frame, textvariable=self.output_dir_var, width=520)
        self.dest_entry.pack(side="left", fill="x", expand=True, padx=5, pady=10)

        browse_btn = ctk.CTkButton(
            dest_frame,
            text="Chọn thư mục...",
            width=110,
            command=self._browse_output_dir
        )
        browse_btn.pack(side="left", padx=5, pady=10)

        open_folder_btn = ctk.CTkButton(
            dest_frame,
            text="📂 Mở thư mục",
            width=105,
            fg_color="#2b7a4b",
            hover_color="#1e5835",
            command=self._open_output_dir
        )
        open_folder_btn.pack(side="left", padx=5, pady=10)

        open_txt_btn = ctk.CTkButton(
            dest_frame,
            text="📄 Xem file .txt",
            width=115,
            fg_color="#3a5a7a",
            hover_color="#283f55",
            command=self._open_video_list_txt
        )
        open_txt_btn.pack(side="left", padx=(5, 15), pady=10)

        # 3. Tabview điều hướng các chế độ
        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=5)

        self.tab_channel = self.tabview.add("📺 Tải Danh Sách Kênh (Channels)")
        self.tab_links = self.tabview.add("🔗 Tải Theo Danh Sách Link")
        self.tab_settings = self.tabview.add("⚙️ Tăng Tốc & Cài Đặt")

        self._build_channel_tab()
        self._build_links_tab()
        self._build_settings_tab()

        # 4. Khu vực Thống kê và Tiến độ (Dưới cùng)
        self._build_progress_area()

    def _build_channel_tab(self):
        """Xây dựng giao diện Tab Tải Danh Sách Kênh."""
        container = self.tab_channel

        # Tiêu đề hướng dẫn
        lbl = ctk.CTkLabel(
            container,
            text="Nhập danh sách link kênh TikTok hoặc @username (mỗi kênh một dòng hoặc phân tách bởi dấu phẩy):",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        lbl.pack(anchor="w", padx=15, pady=(8, 4))

        # Khung nhập danh sách kênh (Textbox đa dòng)
        self.channels_textbox = ctk.CTkTextbox(
            container,
            height=95,
            font=ctk.CTkFont(size=13),
            corner_radius=8
        )
        self.channels_textbox.pack(fill="x", padx=15, pady=(0, 6))

        # Mẫu kênh gợi ý
        sample_channels = "https://www.tiktok.com/@dung.mat_ket_noi\n@openai\nkhaby.lame"
        self.channels_textbox.insert("1.0", sample_channels)

        # Thanh công cụ: Dán, Mở tệp .txt, Xóa, Đếm số kênh
        tools_frame = ctk.CTkFrame(container, fg_color="transparent")
        tools_frame.pack(fill="x", padx=15, pady=(0, 6))

        paste_btn = ctk.CTkButton(
            tools_frame,
            text="📋 Dán từ Clipboard",
            width=135,
            height=32,
            fg_color="#2b5c8f",
            hover_color="#1d4268",
            command=self._paste_channel_input
        )
        paste_btn.pack(side="left", padx=(0, 8))

        import_btn = ctk.CTkButton(
            tools_frame,
            text="📂 Nhập tệp .txt",
            width=120,
            height=32,
            fg_color="#3a4b5c",
            hover_color="#283542",
            command=self._import_channels_file
        )
        import_btn.pack(side="left", padx=(0, 8))

        clear_btn = ctk.CTkButton(
            tools_frame,
            text="🧹 Xóa trắng",
            width=90,
            height=32,
            fg_color="#5c3a3a",
            hover_color="#422828",
            command=self._clear_channels_input
        )
        clear_btn.pack(side="left", padx=(0, 12))

        self.channels_count_lbl = ctk.CTkLabel(
            tools_frame,
            text="📌 Đã nhận diện: 3 kênh",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#4db8ff"
        )
        self.channels_count_lbl.pack(side="left")

        # Cập nhật số kênh khi gõ
        self.channels_textbox.bind("<KeyRelease>", lambda e: self._update_channels_count())

        # Hàng tùy chọn số lượng video
        opt_frame = ctk.CTkFrame(container, fg_color="transparent")
        opt_frame.pack(fill="x", padx=15, pady=4)

        limit_lbl = ctk.CTkLabel(opt_frame, text="Số lượng video tải mỗi kênh:", font=ctk.CTkFont(size=13))
        limit_lbl.pack(side="left", padx=(0, 10))

        self.limit_option = ctk.CTkOptionMenu(
            opt_frame,
            values=["Tất cả video (Toàn bộ kênh)", "10 video mới nhất", "25 video mới nhất", "50 video mới nhất", "100 video mới nhất", "Tùy chỉnh số lượng..."],
            command=self._on_limit_option_changed,
            width=230
        )
        self.limit_option.pack(side="left", padx=5)

        self.custom_limit_entry = ctk.CTkEntry(
            opt_frame,
            placeholder_text="Số lượng",
            width=90
        )
        self.custom_limit_entry.pack(side="left", padx=5)
        self.custom_limit_entry.configure(state="disabled")

        self.quick_censor_check = ctk.CTkCheckBox(
            opt_frame,
            text="✂️ Lọc nhạy cảm 'tiktok'",
            variable=self.enable_censor_var,
            text_color="#64B5F6"
        )
        self.quick_censor_check.pack(side="right", padx=(10, 5))

        # Hàng nút điều khiển
        action_frame = ctk.CTkFrame(container, fg_color="transparent")
        action_frame.pack(fill="x", padx=15, pady=8)

        self.start_channel_btn = ctk.CTkButton(
            action_frame,
            text="🚀 BẮT ĐẦU QUÉT & TẢI TẤT CẢ KÊNH (SIÊU TỐC)",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            fg_color="#1f6aa5",
            hover_color="#144870",
            command=self._start_channel_download
        )
        self.start_channel_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.pause_btn = ctk.CTkButton(
            action_frame,
            text="⏸️ Tạm Dừng",
            width=110,
            height=44,
            fg_color="#7a6015",
            hover_color="#5a460e",
            state="disabled",
            command=self._toggle_pause
        )
        self.pause_btn.pack(side="left", padx=(0, 10))

        self.stop_btn = ctk.CTkButton(
            action_frame,
            text="⏹️ Dừng / Hủy",
            width=110,
            height=44,
            fg_color="#8b1e1e",
            hover_color="#631414",
            state="disabled",
            command=self._stop_download
        )
        self.stop_btn.pack(side="left")

    def _build_links_tab(self):
        """Xây dựng giao diện Tab Tải Theo Danh Sách Link."""
        container = self.tab_links

        lbl = ctk.CTkLabel(
            container,
            text="Dán danh sách các link video TikTok cần tải (mỗi link 1 dòng):",
            font=ctk.CTkFont(weight="bold")
        )
        lbl.pack(anchor="w", padx=15, pady=(10, 5))

        self.links_textbox = ctk.CTkTextbox(container, height=140, font=ctk.CTkFont(size=12))
        self.links_textbox.pack(fill="both", expand=True, padx=15, pady=5)

        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", padx=15, pady=10)

        import_file_btn = ctk.CTkButton(
            btn_row,
            text="📂 Nhập file .txt danh sách link",
            command=self._import_links_file
        )
        import_file_btn.pack(side="left", padx=(0, 10))

        clear_links_btn = ctk.CTkButton(
            btn_row,
            text="🗑️ Xóa trắng",
            fg_color="gray",
            hover_color="#444",
            width=100,
            command=lambda: self.links_textbox.delete("1.0", "end")
        )
        clear_links_btn.pack(side="left", padx=(0, 10))

        self.quick_censor_links_check = ctk.CTkCheckBox(
            btn_row,
            text="✂️ Lọc nhạy cảm 'tiktok'",
            variable=self.enable_censor_var,
            text_color="#64B5F6"
        )
        self.quick_censor_links_check.pack(side="left", padx=(0, 10))

        self.start_links_btn = ctk.CTkButton(
            btn_row,
            text="🚀 Tải Danh Sách Link Này",
            font=ctk.CTkFont(weight="bold"),
            fg_color="#1f6aa5",
            hover_color="#144870",
            command=self._start_links_download
        )
        self.start_links_btn.pack(side="right")

    def _build_settings_tab(self):
        """Xây dựng giao diện Tab Tăng Tốc & Cài Đặt."""
        container = self.tab_settings

        # Khung cấu hình tăng tốc luồng
        speed_group = ctk.CTkFrame(container)
        speed_group.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(speed_group, text="⚡ Cấu Hình Tăng Tốc Tải Đa Luồng:", font=ctk.CTkFont(weight="bold", size=14)).pack(anchor="w", padx=15, pady=(10, 5))

        presets_row = ctk.CTkFrame(speed_group, fg_color="transparent")
        presets_row.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(presets_row, text="Chế độ tăng tốc:").pack(side="left", padx=(0, 10))

        def _set_threads(num: int):
            self.workers_slider.set(num)
            self.workers_lbl.configure(text=f"{num} luồng đồng thời")

        ctk.CTkButton(presets_row, text="🐢 3 luồng (Tiêu chuẩn)", width=120, command=lambda: _set_threads(3)).pack(side="left", padx=4)
        ctk.CTkButton(presets_row, text="⚡ 6 luồng (Nhanh)", width=120, fg_color="#1f6aa5", command=lambda: _set_threads(6)).pack(side="left", padx=4)
        ctk.CTkButton(presets_row, text="🚀 12 luồng (Siêu tốc)", width=120, fg_color="#8f5c15", hover_color="#6e460e", command=lambda: _set_threads(12)).pack(side="left", padx=4)
        ctk.CTkButton(presets_row, text="🔥 16 luồng (Turbo)", width=120, fg_color="#8f1515", hover_color="#6b0e0e", command=lambda: _set_threads(16)).pack(side="left", padx=4)

        slider_row = ctk.CTkFrame(speed_group, fg_color="transparent")
        slider_row.pack(fill="x", padx=15, pady=(10, 15))

        ctk.CTkLabel(slider_row, text="Điều chỉnh số luồng thủ công:").pack(side="left", padx=(0, 10))
        self.workers_slider = ctk.CTkSlider(slider_row, from_=1, to=16, number_of_steps=15, width=240)
        self.workers_slider.set(6)
        self.workers_slider.pack(side="left", padx=10)

        self.workers_lbl = ctk.CTkLabel(slider_row, text="6 luồng đồng thời", font=ctk.CTkFont(weight="bold"))
        self.workers_lbl.pack(side="left", padx=5)
        self.workers_slider.configure(command=lambda val: self.workers_lbl.configure(text=f"{int(val)} luồng đồng thời"))

        # Tùy chọn Cookie chống chặn bot
        cookie_frame = ctk.CTkFrame(container)
        cookie_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(cookie_frame, text="🛡️ Cookie Chống Chặn Bot TikTok:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=15, pady=10)

        self.cookie_option = ctk.CTkOptionMenu(
            cookie_frame,
            values=["Tự động (Không cần cookie)", "Google Chrome", "Microsoft Edge", "Mozilla Firefox", "Brave"],
            width=230
        )
        self.cookie_option.set("Tự động (Không cần cookie)")
        self.cookie_option.pack(side="left", padx=10, pady=10)

        ctk.CTkLabel(
            cookie_frame,
            text="(Khuyên dùng nếu TikTok yêu cầu xác minh bảo mật hoặc không tải được kênh)",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        ).pack(side="left", padx=5)

        # Cài đặt tùy chọn tải
        opts_group = ctk.CTkFrame(container)
        opts_group.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(opts_group, text="📁 Tùy Chọn Tệp Tải Về:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=15, pady=(10, 5))

        self.opt_skip_existing = ctk.CTkCheckBox(opts_group, text="Bỏ qua video đã tải trước đó (chống tải trùng, kiểm tra bộ nhớ tức thời O(1))")
        self.opt_skip_existing.select()
        self.opt_skip_existing.pack(anchor="w", padx=25, pady=5)

        self.opt_download_audio = ctk.CTkCheckBox(opts_group, text="Tải thêm tệp âm thanh gốc (.mp3)")
        self.opt_download_audio.pack(anchor="w", padx=25, pady=5)

        self.opt_download_cover = ctk.CTkCheckBox(opts_group, text="Tải thêm ảnh bìa Thumbnail (.jpg)")
        self.opt_download_cover.pack(anchor="w", padx=25, pady=5)

        self.opt_save_metadata = ctk.CTkCheckBox(opts_group, text="Lưu thông tin chi tiết video dạng JSON (tiêu đề, lượt xem, thời gian, nhạc)")
        self.opt_save_metadata.pack(anchor="w", padx=25, pady=(5, 15))

        # Nhóm cấu hình Lọc nhạy cảm & Bản quyền ("tiktok")
        censor_group = ctk.CTkFrame(container)
        censor_group.pack(fill="x", padx=15, pady=5)

        censor_hdr = ctk.CTkLabel(
            censor_group,
            text="🛡️ Tùy Chọn Lọc Từ Nhạy Cảm & Bản Quyền ('tiktok'):",
            font=ctk.CTkFont(weight="bold", size=14)
        )
        censor_hdr.pack(anchor="w", padx=15, pady=(10, 4))

        censor_sub = ctk.CTkLabel(
            censor_group,
            text="Tự động cắt bỏ đoạn nói từ 'tiktok' (video ngắn lại) và dán đè Sticker/Logo lên vị trí chữ 'tiktok' trên khung hình.",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        censor_sub.pack(anchor="w", padx=25, pady=(0, 6))

        self.censor_check = ctk.CTkCheckBox(
            censor_group,
            text="Kích hoạt tự động lọc từ nhạy cảm 'tiktok' (Bỏ tick nếu muốn tải video gốc nguyên bản)",
            variable=self.enable_censor_var,
            font=ctk.CTkFont(weight="bold")
        )
        self.censor_check.pack(anchor="w", padx=25, pady=5)

        # Hàng chọn Sticker / Logo
        sticker_row = ctk.CTkFrame(censor_group, fg_color="transparent")
        sticker_row.pack(fill="x", padx=25, pady=4)

        ctk.CTkLabel(sticker_row, text="Ảnh Sticker / Logo che chữ:").pack(side="left", padx=(0, 10))
        self.sticker_entry = ctk.CTkEntry(
            sticker_row,
            textvariable=self.custom_sticker_var,
            placeholder_text="Để trống sẽ dùng sticker ngôi sao mặc định (assets/default_sticker.png)",
            width=360
        )
        self.sticker_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            sticker_row,
            text="Chọn ảnh...",
            width=95,
            command=self._browse_custom_sticker
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            sticker_row,
            text="Mặc định",
            width=80,
            fg_color="gray",
            hover_color="#555",
            command=self._reset_default_sticker
        ).pack(side="left")

        # Hàng từ khóa lọc
        kw_row = ctk.CTkFrame(censor_group, fg_color="transparent")
        kw_row.pack(fill="x", padx=25, pady=(4, 12))

        ctk.CTkLabel(kw_row, text="Từ khóa cần lọc:").pack(side="left", padx=(0, 10))
        self.keywords_entry = ctk.CTkEntry(
            kw_row,
            textvariable=self.censor_keywords_var,
            width=420
        )
        self.keywords_entry.pack(side="left", fill="x", expand=True)

        # Nhóm công cụ sửa chữa & bảo trì
        repair_group = ctk.CTkFrame(container)
        repair_group.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(repair_group, text="🛠️ Công Cụ Sửa Chữa & Bảo Trì Tệp:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=15, pady=(10, 5))

        repair_desc = ctk.CTkLabel(
            repair_group,
            text="Tự động phát hiện và tải lại các video bị tải nhầm thành âm thanh (chỉ có tiếng, không có hình).",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        repair_desc.pack(anchor="w", padx=25, pady=(0, 8))

        self.repair_btn = ctk.CTkButton(
            repair_group,
            text="🔧 Quét & Sửa Lỗi Các Video Bị Thiếu Hình (Chỉ Có Tiếng)",
            fg_color="#2b5c8f",
            hover_color="#1d4268",
            height=36,
            command=self._start_repair_audio_files
        )
        self.repair_btn.pack(anchor="w", padx=25, pady=(0, 15))

    def _browse_custom_sticker(self):
        f = filedialog.askopenfilename(
            title="Chọn ảnh Logo / Sticker che chữ 'tiktok'",
            filetypes=[
                ("Image files", "*.png;*.jpg;*.jpeg;*.webp"),
                ("PNG (Nền trong suốt)", "*.png"),
                ("Tất cả tệp", "*.*")
            ]
        )
        if f:
            self.custom_sticker_var.set(os.path.abspath(f))

    def _reset_default_sticker(self):
        self.custom_sticker_var.set("")

    def _start_repair_audio_files(self):
        """Khởi chạy tiến trình sửa các tệp video chỉ có tiếng trong thư mục tải về."""
        output_dir = self.output_dir_var.get()
        if not os.path.exists(output_dir):
            self._log(f"⚠️ Thư mục tải về không tồn tại: {output_dir}")
            return

        self.repair_btn.configure(state="disabled", text="⏳ Đang sửa chữa video...")

        def _worker():
            try:
                from repair_audio_files import scan_corrupted_files, repair_single_file
                self._log("=" * 50)
                self._log(f"🔍 Đang quét các video bị lỗi thiếu hình trong {output_dir} ...")
                corrupted = scan_corrupted_files(output_dir)
                total = len(corrupted)
                if total == 0:
                    self._log("🎉 Không có video nào bị lỗi chỉ có tiếng trong thư mục này!")
                else:
                    self._log(f"⚠️ Tìm thấy {total} video bị lỗi. Đang bắt đầu tải lại video chuẩn...")
                    repaired = 0
                    for idx, (fpath, uname, vid_id) in enumerate(corrupted, 1):
                        self._log(f"🔄 [{idx}/{total}] Đang sửa: {os.path.basename(fpath)} ...")
                        if repair_single_file(fpath, uname, vid_id):
                            repaired += 1
                            self._log(f"✅ [{idx}/{total}] Đã sửa xong: {os.path.basename(fpath)}")
                        else:
                            self._log(f"❌ [{idx}/{total}] Chưa sửa được: {os.path.basename(fpath)}")
                    self._log(f"🎉 Hoàn tất sửa chữa! Đã khắc phục thành công {repaired}/{total} video.")
                self._log("=" * 50)
            except Exception as e:
                self._log(f"❌ Lỗi trong quá trình sửa chữa: {e}")
            finally:
                self.after(0, lambda: self.repair_btn.configure(state="normal", text="🔧 Quét & Sửa Lỗi Các Video Bị Thiếu Hình (Chỉ Có Tiếng)"))

        threading.Thread(target=_worker, daemon=True).start()

    def _build_progress_area(self):
        """Xây dựng khung hiển thị thống kê, thanh tiến độ và nhật ký."""
        bottom_frame = ctk.CTkFrame(self, corner_radius=10)
        bottom_frame.pack(fill="both", expand=True, padx=15, pady=(5, 15))

        # Hàng Thẻ Thống Kê (Badges)
        stats_row = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        stats_row.pack(fill="x", padx=15, pady=(10, 5))

        self.stat_total_lbl = self._create_stat_card(stats_row, "📊 Đã phát hiện", "0", "#2b5c8f")
        self.stat_in_progress_lbl = self._create_stat_card(stats_row, "⏳ Đang tải", "0", "#8f682b")
        self.stat_done_lbl = self._create_stat_card(stats_row, "✅ Hoàn thành", "0", "#2b8f4b")
        self.stat_skipped_lbl = self._create_stat_card(stats_row, "⏭️ Đã có sẵn", "0", "#636363")
        self.stat_failed_lbl = self._create_stat_card(stats_row, "❌ Lỗi", "0", "#8f2b2b")

        # Thanh tiến độ tổng
        prog_header = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        prog_header.pack(fill="x", padx=15, pady=(5, 2))

        self.status_detail_lbl = ctk.CTkLabel(
            prog_header,
            text="Sẵn sàng",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.status_detail_lbl.pack(side="left")

        self.percent_lbl = ctk.CTkLabel(prog_header, text="0%", font=ctk.CTkFont(size=12, weight="bold"))
        self.percent_lbl.pack(side="right")

        self.batch_progressbar = ctk.CTkProgressBar(bottom_frame, height=14)
        self.batch_progressbar.set(0.0)
        self.batch_progressbar.pack(fill="x", padx=15, pady=(0, 5))

        # Khung nhật ký hoạt động (Logs)
        log_header = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=15, pady=(5, 0))

        ctk.CTkLabel(log_header, text="📝 Nhật ký hoạt động:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")

        clear_log_btn = ctk.CTkButton(
            log_header,
            text="Xóa log",
            width=65,
            height=20,
            font=ctk.CTkFont(size=10),
            command=self._clear_logs
        )
        clear_log_btn.pack(side="right")

        self.log_textbox = ctk.CTkTextbox(
            bottom_frame,
            height=130,
            font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.log_textbox.pack(fill="both", expand=True, padx=15, pady=(2, 10))

    def _create_stat_card(self, parent, title: str, init_val: str, color: str):
        card = ctk.CTkFrame(parent, fg_color=color, corner_radius=6)
        card.pack(side="left", fill="x", expand=True, padx=4)

        t = ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=11), text_color="#ddd")
        t.pack(pady=(4, 0))

        val = ctk.CTkLabel(card, text=init_val, font=ctk.CTkFont(size=16, weight="bold"), text_color="white")
        val.pack(pady=(0, 4))
        return val

    # ==========================
    # LOG & UI HELPERS
    # ==========================
    def log(self, text: str):
        """Ghi dòng nhật ký ra giao diện an toàn đa luồng, tự động cắt tỉa để RAM luôn siêu nhẹ."""
        def _append():
            timestamp = time.strftime("%H:%M:%S")
            self.log_textbox.insert("end", f"[{timestamp}] {text}\n")
            # Tự động cắt tỉa nếu nhật ký quá 350 dòng để giải phóng RAM tối đa
            try:
                line_count = int(self.log_textbox.index("end-1c").split(".")[0])
                if line_count > 350:
                    self.log_textbox.delete("1.0", "101.0")
            except Exception:
                pass
            self.log_textbox.see("end")
        self.after(0, _append)

    def _clear_logs(self):
        self.log_textbox.delete("1.0", "end")
        import gc
        gc.collect()

    def _update_stats(self, total: int, done: int, skipped: int, failed: int, in_progress: int = 0):
        def _apply():
            self.stat_total_lbl.configure(text=str(total))
            self.stat_done_lbl.configure(text=str(done))
            self.stat_skipped_lbl.configure(text=str(skipped))
            self.stat_failed_lbl.configure(text=str(failed))
            self.stat_in_progress_lbl.configure(text=str(in_progress))

            finished = done + skipped + failed
            if total > 0:
                percent = min(1.0, finished / total)
                self.batch_progressbar.set(percent)
                self.percent_lbl.configure(text=f"{int(percent * 100)}%")
            else:
                self.batch_progressbar.set(0.0)
                self.percent_lbl.configure(text="0%")
        self.after(0, _apply)

    def _set_ui_state(self, running: bool):
        self.is_running = running
        def _apply():
            if running:
                self.start_channel_btn.configure(state="disabled")
                self.start_links_btn.configure(state="disabled")
                self.pause_btn.configure(state="normal", text="⏸️ Tạm Dừng")
                self.stop_btn.configure(state="normal")
            else:
                self.start_channel_btn.configure(state="normal")
                self.start_links_btn.configure(state="normal")
                self.pause_btn.configure(state="disabled", text="⏸️ Tạm Dừng")
                self.stop_btn.configure(state="disabled")
                import gc
                gc.collect()
        self.after(0, _apply)

    # ==========================
    # EVENT HANDLERS
    # ==========================
    def _change_theme(self, mode: str):
        ctk.set_appearance_mode(mode)

    def _browse_output_dir(self):
        folder = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if folder:
            self.output_dir_var.set(folder)

    def _open_output_dir(self):
        p = self.output_dir_var.get()
        if os.path.isdir(p):
            os.startfile(p)
        else:
            os.makedirs(p, exist_ok=True)
            os.startfile(p)

    def _open_video_list_txt(self):
        p = self.output_dir_var.get()
        txt_path = os.path.join(p, "downloaded_videos.txt")
        if os.path.isfile(txt_path):
            os.startfile(txt_path)
            return
        if os.path.isdir(p):
            for sub in os.listdir(p):
                sub_txt = os.path.join(p, sub, "downloaded_videos.txt")
                if os.path.isfile(sub_txt):
                    os.startfile(sub_txt)
                    return
        messagebox.showinfo(
            "Chưa có dữ liệu",
            f"Chưa có video nào tải xong để tạo tệp downloaded_videos.txt tại:\n{p}"
        )

    def _update_channels_count(self):
        text = self.channels_textbox.get("1.0", "end").strip()
        ch_list = extract_channel_list_from_text(text)
        if ch_list:
            self.channels_count_lbl.configure(
                text=f"📌 Đã nhận diện: {len(ch_list)} kênh",
                text_color="#4db8ff"
            )
        else:
            self.channels_count_lbl.configure(
                text="📌 Chưa có kênh nào hợp lệ",
                text_color="gray"
            )

    def _paste_channel_input(self):
        try:
            cb = self.clipboard_get().strip()
            curr = self.channels_textbox.get("1.0", "end").strip()
            if not curr:
                self.channels_textbox.insert("1.0", cb)
            else:
                self.channels_textbox.insert("end", "\n" + cb)
            self._update_channels_count()
        except Exception:
            pass

    def _import_channels_file(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.channels_textbox.delete("1.0", "end")
                self.channels_textbox.insert("1.0", content)
                self._update_channels_count()
                self.log(f"📂 Đã nạp danh sách kênh từ tệp: {path}")
            except Exception as e:
                messagebox.showerror("Lỗi đọc file", f"Không thể đọc file: {e}")

    def _clear_channels_input(self):
        self.channels_textbox.delete("1.0", "end")
        self._update_channels_count()

    def _on_limit_option_changed(self, choice: str):
        if "Tùy chỉnh" in choice:
            self.custom_limit_entry.configure(state="normal")
            self.custom_limit_entry.focus()
        else:
            self.custom_limit_entry.configure(state="disabled")

    def _get_current_limit(self) -> Optional[int]:
        """Lấy giá trị giới hạn số lượng video hiện tại từ giao diện."""
        limit_choice = self.limit_option.get()
        if "10 video" in limit_choice:
            return 10
        elif "25 video" in limit_choice:
            return 25
        elif "50 video" in limit_choice:
            return 50
        elif "100 video" in limit_choice:
            return 100
        elif "Tùy chỉnh" in limit_choice:
            try:
                val = int(self.custom_limit_entry.get().strip())
                return val if val > 0 else None
            except ValueError:
                return None
        return None

    def _import_links_file(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.links_textbox.delete("1.0", "end")
                self.links_textbox.insert("1.0", content)
                self.log(f"📂 Đã nạp danh sách link từ file: {path}")
            except Exception as e:
                messagebox.showerror("Lỗi đọc file", f"Không thể đọc file: {e}")

    def _toggle_pause(self):
        if not self.active_downloader:
            return
        if self.active_downloader.is_paused:
            # Luôn kiểm tra và cập nhật cấu hình số lượng giới hạn mới nhất từ giao diện khi tiếp tục!
            cur_limit = self._get_current_limit()
            self.active_downloader.options.limit_videos = cur_limit
            if cur_limit is not None:
                self.log(f"⚙️ Giới hạn áp dụng khi tiếp tục: {cur_limit} video mỗi kênh.")
                if self.active_downloader.completed_count >= cur_limit:
                    self.log(f"✅ Kênh này đã tải xong {self.active_downloader.completed_count}/{cur_limit} video. Kết thúc kênh này.")
                    self.active_downloader.cancel()
                    self._set_ui_state(False)
                    return

            self.active_downloader.resume()
            self.pause_btn.configure(text="⏸️ Tạm Dừng")
            self.status_detail_lbl.configure(text="▶️ Đang tiếp tục tiến trình tải...")
            self.start_channel_btn.configure(state="disabled")
            self.start_links_btn.configure(state="disabled")
            self.log("▶️ Đã tiếp tục tiến trình tải.")
        else:
            self.active_downloader.pause()
            self.pause_btn.configure(text="▶️ Tiếp Tục")
            # KHI TẠM DỪNG: Mở lại nút Quét và tải kênh ngay lập tức!
            self.start_channel_btn.configure(state="normal")
            self.start_links_btn.configure(state="normal")
            self.status_detail_lbl.configure(text="⏸️ Đã tạm dừng. Bấm 'Tiếp Tục' hoặc đổi số lượng rồi bấm 'Quét và tải kênh'.")
            self.log("⏸️ Đã tạm dừng tiến trình. Nút 'Quét và tải kênh' đã được mở lại.")

    def _stop_download(self):
        self.cancel_event.set()
        if self.active_downloader:
            self.active_downloader.cancel()
        
        # KHI BẤM HỦY: Mở lại nút Quét và tải kênh ngay lập tức!
        self._set_ui_state(False)
        self.status_detail_lbl.configure(text="⏹️ Đã dừng/hủy phiên tải. Sẵn sàng quét và tải mới.")
        self.log("⏹️ Đã hủy tiến trình tải. Nút 'Quét và tải kênh' đã sẵn sàng.")

    # ==========================
    # PIPELINED CONCURRENT WORKERS
    # ==========================
    def _start_channel_download(self):
        """Khởi động quét và tải theo danh sách kênh (Pipelined Streaming) siêu tốc."""
        raw_text = self.channels_textbox.get("1.0", "end").strip()
        if not raw_text:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập ít nhất 1 link kênh hoặc @username TikTok!")
            return

        channels = extract_channel_list_from_text(raw_text)
        if not channels:
            messagebox.showerror("Sai định dạng", "Không nhận diện được link kênh hoặc username TikTok hợp lệ nào!")
            return

        # Xác định số lượng video cần tải mỗi kênh
        limit_val = self._get_current_limit()
        if "Tùy chỉnh" in self.limit_option.get() and limit_val is None:
            messagebox.showwarning("Số lượng không hợp lệ", "Vui lòng nhập một số nguyên dương vào ô tùy chỉnh!")
            return

        # Dọn dẹp phiên tải cũ nếu đang chạy hoặc tạm dừng
        if self.is_running or (self.active_downloader and self.active_downloader.is_paused):
            self.log("🛑 Đang dừng phiên tải trước đó để nạp cấu hình mới...")
            self.cancel_event.set()
            if self.active_downloader:
                self.active_downloader.cancel()
            if self.worker_thread and self.worker_thread.is_alive():
                self.worker_thread.join(timeout=1.5)

        self.current_session_id += 1
        current_session = self.current_session_id
        session_cancel_event = threading.Event()
        self.cancel_event = session_cancel_event

        self._set_ui_state(True)
        self._update_stats(0, 0, 0, 0, 0)
        total_channels = len(channels)
        limit_desc = f"{limit_val} video mỗi kênh" if limit_val else "Toàn bộ video"
        self.status_detail_lbl.configure(text=f"Bắt đầu tải {total_channels} kênh TikTok ({limit_desc})...")
        self.log(f"📋 Bắt đầu phiên tải {total_channels} kênh: {', '.join('@' + c for c in channels[:5])}{'...' if len(channels) > 5 else ''} (Giới hạn: {limit_desc})")

        def _orchestrator():
            grand_total_found = 0
            grand_completed = 0
            grand_skipped = 0
            grand_failed = 0

            try:
                num_workers = int(self.workers_slider.get())
                self.log(f"⚡ Đã kích hoạt {num_workers} luồng tải song song (Pipeline Mode)")

                # Xác định cookie trình duyệt nếu được chọn
                chosen_cookie = self.cookie_option.get()
                b_name = None
                if "Chrome" in chosen_cookie:
                    b_name = "chrome"
                elif "Edge" in chosen_cookie:
                    b_name = "edge"
                elif "Firefox" in chosen_cookie:
                    b_name = "firefox"
                elif "Brave" in chosen_cookie:
                    b_name = "brave"

                base_dir = self.output_dir_var.get()

                # Vòng lặp tải từng kênh trong danh sách
                for ch_idx, username in enumerate(channels, 1):
                    if session_cancel_event.is_set() or self.current_session_id != current_session:
                        self.log(f"⏹️ Đã dừng danh sách kênh tại kênh thứ {ch_idx}/{total_channels}.")
                        break

                    self.log(f"\n{'='*55}")
                    self.log(f"🎬 [Kênh {ch_idx}/{total_channels}] Bắt đầu quét & tải kênh @{username} ...")
                    self.log(f"{'='*55}")

                    channel_dir = os.path.join(base_dir, f"@{username}")
                    os.makedirs(channel_dir, exist_ok=True)

                    # Luôn kiểm tra lại limit_val mới nhất từ giao diện nếu người dùng đã đổi
                    cur_limit = self._get_current_limit()

                    options = DownloadOptions(
                        output_dir=channel_dir,
                        download_video=True,
                        download_audio=bool(self.opt_download_audio.get()),
                        download_cover=bool(self.opt_download_cover.get()),
                        save_metadata=bool(self.opt_save_metadata.get()),
                        skip_existing=bool(self.opt_skip_existing.get()),
                        max_workers=num_workers,
                        limit_videos=cur_limit,
                        enable_censorship=bool(self.enable_censor_var.get()),
                        censor_keywords=self.censor_keywords_var.get().strip() or "tiktok, tik tok, tóp tóp, toptop, douyin, tiktokshop, tiktok shop, tik tok shop, cháy, nổ",
                        custom_sticker_path=self.custom_sticker_var.get().strip() or None
                    )

                    self.active_downloader = BatchDownloader(options, browser_cookie=b_name)
                    self.active_downloader.log_callback = self.log

                    stream_queue = queue.Queue()
                    channel_items = []
                    channel_lock = threading.Lock()

                    def on_item_status(item, idx, tot):
                        done = grand_completed + self.active_downloader.completed_count
                        skipped = grand_skipped + self.active_downloader.skipped_count
                        failed = grand_failed + self.active_downloader.failed_count
                        in_prog = self.active_downloader.in_progress_count
                        current_tot = max(grand_total_found + tot, grand_total_found + len(channel_items))
                        self._update_stats(current_tot, done, skipped, failed, in_prog)
                        self.status_detail_lbl.configure(
                            text=f"[Kênh {ch_idx}/{total_channels} - @{username}] [{idx}/{tot}] {item.status.value}: #{item.id}"
                        )

                    def on_item_progress(item, percent, speed_str):
                        self.status_detail_lbl.configure(
                            text=f"[@{username}] Đang tải #{item.id} ({percent:.1f}% - {speed_str})"
                        )

                    self.active_downloader.on_item_status_callback = on_item_status
                    self.active_downloader.on_item_progress_callback = on_item_progress

                    def on_video_found(v: VideoItem, count: int):
                        with channel_lock:
                            channel_items.append(v)
                        done = grand_completed + self.active_downloader.completed_count
                        skipped = grand_skipped + self.active_downloader.skipped_count
                        failed = grand_failed + self.active_downloader.failed_count
                        in_prog = self.active_downloader.in_progress_count
                        current_tot = grand_total_found + count
                        self._update_stats(current_tot, done, skipped, failed, in_prog)

                    # 1. Khởi động luồng Downloader Consumer cho kênh này
                    def _run_downloader():
                        self.active_downloader.download_from_stream_queue(
                            item_queue=stream_queue,
                            get_total_callback=lambda: len(channel_items)
                        )

                    dl_thread = threading.Thread(target=_run_downloader, daemon=True)
                    dl_thread.start()

                    # 2. Chạy Scanner quét kênh và đẩy liên tục vào stream_queue
                    scan_channel_videos(
                        channel_input=f"https://www.tiktok.com/@{username}",
                        limit=cur_limit,
                        on_found_callback=on_video_found,
                        log_callback=self.log,
                        cancel_event=session_cancel_event,
                        stream_queue=stream_queue,
                        browser_cookie=b_name,
                        pause_check=self.active_downloader._check_pause
                    )

                    # Gửi tín hiệu hoàn tất quét vào hàng đợi (sentinel None cho mỗi worker)
                    for _ in range(num_workers):
                        stream_queue.put(None)

                    # Chờ downloader hoàn thành tất cả video trong hàng đợi của kênh này
                    dl_thread.join()

                    ch_done = self.active_downloader.completed_count
                    ch_skip = self.active_downloader.skipped_count
                    ch_fail = self.active_downloader.failed_count
                    ch_tot = len(channel_items)

                    grand_total_found += ch_tot
                    grand_completed += ch_done
                    grand_skipped += ch_skip
                    grand_failed += ch_fail

                    self.log(f"✅ [Kênh {ch_idx}/{total_channels}] Xong @{username}: Tải mới {ch_done} | Bỏ qua {ch_skip} | Lỗi {ch_fail}")

                # Tổng kết toàn bộ các kênh
                self._update_stats(grand_total_found, grand_completed, grand_skipped, grand_failed, 0)
                self.status_detail_lbl.configure(
                    text=f"Hoàn tất {total_channels} kênh: {grand_completed} tải mới, {grand_skipped} bỏ qua, {grand_failed} lỗi."
                )
                self.log(f"\n🎉 HOÀN TẤT TOÀN BỘ {total_channels} KÊNH! Tổng tải: {grand_completed} | Bỏ qua: {grand_skipped} | Lỗi: {grand_failed}")

            except Exception as e:
                self.log(f"❌ Có lỗi trong quá trình xử lý: {e}")
            finally:
                if self.current_session_id == current_session:
                    self._set_ui_state(False)

        self.worker_thread = threading.Thread(target=_orchestrator, daemon=True)
        self.worker_thread.start()

    def _start_links_download(self):
        """Khởi động tải hàng loạt từ danh sách link đã nhập."""
        raw_text = self.links_textbox.get("1.0", "end").strip()
        if not raw_text:
            messagebox.showwarning("Thiếu link", "Vui lòng dán danh sách link video TikTok vào ô văn bản!")
            return

        urls = extract_video_urls_from_text(raw_text)
        if not urls:
            messagebox.showerror("Không tìm thấy link", "Không nhận diện được link TikTok hợp lệ nào!")
            return

        dest_dir = self.output_dir_var.get()
        os.makedirs(dest_dir, exist_ok=True)

        # Dọn dẹp phiên tải cũ nếu đang chạy hoặc tạm dừng
        if self.is_running or (self.active_downloader and self.active_downloader.is_paused):
            self.cancel_event.set()
            if self.active_downloader:
                self.active_downloader.cancel()
            if self.worker_thread and self.worker_thread.is_alive():
                self.worker_thread.join(timeout=1.5)

        self.current_session_id += 1
        current_session = self.current_session_id
        session_cancel_event = threading.Event()
        self.cancel_event = session_cancel_event

        self._set_ui_state(True)
        self._update_stats(len(urls), 0, 0, 0, 0)
        self.status_detail_lbl.configure(text=f"Bắt đầu tải {len(urls)} link ...")

        def _worker():
            try:
                num_workers = int(self.workers_slider.get())
                videos: List[VideoItem] = []
                for idx, u in enumerate(urls, 1):
                    if session_cancel_event.is_set() or self.current_session_id != current_session:
                        break
                    vid_id = u.split("/video/")[-1].split("?")[0] if "/video/" in u else str(idx)
                    videos.append(VideoItem(id=vid_id, url=u))

                options = DownloadOptions(
                    output_dir=dest_dir,
                    download_video=True,
                    download_audio=bool(self.opt_download_audio.get()),
                    download_cover=bool(self.opt_download_cover.get()),
                    save_metadata=bool(self.opt_save_metadata.get()),
                    skip_existing=bool(self.opt_skip_existing.get()),
                    max_workers=num_workers,
                    enable_censorship=bool(self.enable_censor_var.get()),
                    censor_keywords=self.censor_keywords_var.get().strip() or "tiktok, tik tok, tóp tóp, toptop, douyin, tiktokshop, tiktok shop, tik tok shop, cháy, nổ",
                    custom_sticker_path=self.custom_sticker_var.get().strip() or None
                )

                chosen_cookie = self.cookie_option.get()
                b_name = None
                if "Chrome" in chosen_cookie:
                    b_name = "chrome"
                elif "Edge" in chosen_cookie:
                    b_name = "edge"
                elif "Firefox" in chosen_cookie:
                    b_name = "firefox"
                elif "Brave" in chosen_cookie:
                    b_name = "brave"

                self.active_downloader = BatchDownloader(options, browser_cookie=b_name)
                self.active_downloader.log_callback = self.log

                total = len(videos)

                def on_item_status(item, idx, tot):
                    done = self.active_downloader.completed_count
                    skipped = self.active_downloader.skipped_count
                    failed = self.active_downloader.failed_count
                    in_prog = self.active_downloader.in_progress_count
                    self._update_stats(tot, done, skipped, failed, in_prog)
                    self.status_detail_lbl.configure(text=f"[{idx}/{tot}] {item.status.value}: #{item.id}")

                self.active_downloader.on_item_status_callback = on_item_status
                stats = self.active_downloader.download_batch(videos)
                self.status_detail_lbl.configure(
                    text=f"Hoàn tất: {stats['completed']} tải mới, {stats['skipped']} bỏ qua, {stats['failed']} lỗi."
                )

            except Exception as e:
                self.log(f"❌ Lỗi: {e}")
            finally:
                if self.current_session_id == current_session:
                    self._set_ui_state(False)

        self.worker_thread = threading.Thread(target=_worker, daemon=True)
        self.worker_thread.start()

def main():
    app = TikTokDownloaderApp()
    app.mainloop()

if __name__ == "__main__":
    main()
