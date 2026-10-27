# 🎵 TikTok Batch Channel Downloader (Phiên Bản Tăng Tốc Siêu Tốc - Turbo)

Ứng dụng chuyên nghiệp giúp tự động quét và tải toàn bộ video từ bất kỳ kênh TikTok nào về máy tính với chất lượng gốc cao nhất (**HD 1080p/720p**) và **hoàn toàn sạch watermark** (không có logo TikTok nhảy góc hay outro cuối video).

---

## ⚡ Các Cải Tiến Tăng Tốc Vượt Trội (Turbo Acceleration)

1. **Mô Hình Xử Lý Song Song Pipeline (Producer - Consumer):**
   - **Không cần chờ đợi:** Ứng dụng vừa quét vừa tải video song song cùng lúc.
   - Ngay khi quét thấy video 1, hệ thống lập tức tải video 1 ngay trong vài giây mà không cần phải đợi quét xong toàn bộ hàng trăm video của kênh.

2. **Tái Sử Dụng Kết Nối TLS/HTTP Keep-Alive (Connection Pooling):**
   - Tái sử dụng socket TCP và chứng chỉ bảo mật TLS với pool lên đến 50 kết nối.
   - Loại bỏ độ trễ bắt tay mạng (bỏ qua 200ms - 500ms delay mỗi tệp).

3. **Tối Ưu Bộ Đệm Ghi Đĩa (Optimal Buffer 1 MB/Chunk):**
   - Tăng kích thước bộ đệm từ 64 KB lên **1 MB (1048576 bytes)**, giảm tối đa số lần ngắt I/O hệ điều hành và khai thác tối đa băng thông mạng cáp quang.

4. **Tải Đa Luồng Song Song (Lên Đến 16 - 20 Luồng):**
   - Cung cấp các nút bấm tốc độ nhanh:
     - 🐢 **3 luồng**: Tiêu chuẩn (tiết kiệm tài nguyên).
     - ⚡ **6 luồng**: Nhanh (mặc định khuyên dùng).
     - 🚀 **12 luồng**: Siêu tốc Turbo.
     - 🔥 **16 luồng**: Tối đa công suất mạng.

5. **Bộ Lọc Quét Tinh Gọn (Stripped Scanning Overhead):**
   - Lược bỏ kiểm tra ảnh tĩnh và audio thừa trong lúc quét kênh, giúp thời gian phân trang nhanh hơn gấp 2 lần.

6. **Kiểm Tra Trùng Lặp Tức Thời O(1) (In-Memory Archive):**
   - Nhận diện các video đã tải trong 0 mili-giây từ RAM, bỏ qua ngay lập tức không tốn dung lượng hay thời gian quét đĩa.

---

## 🛡️ Tính Năng Tự Động Lọc Từ Khóa Nhạy Cảm & Bản Quyền ("tiktok", "tích tốc", "tích tốc xốp", "cháy", "nổ", "tiktokshop")

Ứng dụng tích hợp bộ đôi công nghệ AI tiên tiến:
1. **Trí tuệ nhân tạo Nhận diện Giọng nói (Whisper AI):**
   - Tự động nhận diện giọng nói trong video với độ chính xác theo từng từ (word-level timestamps).
   - Khi phát hiện người nói phát âm các từ khóa nhạy cảm: **`tiktok`**, **`tik tok`**, **`tóp tóp`**, **`tích tốc`**, **`tích tốc xốp`**, **`tiktokshop`**, **`tiktok shop`**, **`cháy`**, **`nổ`**, hệ thống sẽ **cắt bỏ hoàn toàn cả hình ảnh lẫn âm thanh** đoạn đó (video được cắt ngắn lại đồng bộ khung hình mượt mà).
2. **Thị giác Máy tính Nhận diện Văn bản (RapidOCR):**
   - Quét từng khung hình trên video để nhận diện vị trí và thời lượng xuất hiện các từ khóa hoặc chữ "tiktok", "tích tốc", "tích tốc xốp", "tiktokshop", "cháy", "nổ".
   - Tự động dán đè Sticker/Logo lên đúng tọa độ chữ xuất hiện để che hoàn toàn.
   - Cho phép chọn ảnh Logo/Sticker tùy chỉnh từ máy tính (`.png`, `.jpg`) hoặc tự động dùng sticker ngôi sao mặc định (`assets/default_sticker.png`).
3. **Hoàn Toàn Là Tùy Chọn (Optional):**
   - Mặc định tính năng này **TẮT** (Bỏ tick) để ứng dụng tải video gốc nguyên bản siêu tốc.
   - Khi bạn tick chọn ô **"✂️ Lọc nhạy cảm 'tiktok'"**, ứng dụng mới kích hoạt quy trình lọc cho các video tải về.
   - **Giao diện GUI:** Có thể bật/tắt nhanh ngay trên màn hình chính hoặc vào Tab **"⚙️ Tăng Tốc & Cài Đặt"** để chỉnh ảnh Logo và danh sách từ khóa.
   - **Dòng lệnh CLI:** Thêm cờ `--censor` (kèm `--sticker <ảnh.png>` và `--censor-keywords <từ_khóa>`).

---

## 📁 Quy Chuẩn Đặt Tên Tệp & Xuất Danh Sách Tên Video

1. **Định dạng tên video lưu trữ:**
```text
{tên_kênh}_{id_video}.mp4
Ví dụ: dung.mat_ket_noi_7700794682691063060.mp4
```
- Âm thanh MP3 (nếu chọn): `{tên_kênh}_{id_video}_audio.mp3`
- Ảnh bìa HD (nếu chọn): `{tên_kênh}_{id_video}_cover.jpg`
- Metadata JSON (nếu chọn): `{tên_kênh}_{id_video}_meta.json`

2. **Tự động xuất và cập nhật file `downloaded_videos.txt`:**
- Sau khi tải xong bất kỳ video nào, tên file `.mp4` sẽ được tự động lưu vào tệp `downloaded_videos.txt` (nằm ngay trong thư mục lưu của kênh và thư mục gốc tải về).
- **Cập nhật dữ liệu liên tục:** Nếu file `.txt` đã có từ trước, ứng dụng sẽ tự động cập nhật nối tiếp (append) tên các video mới vào, hoàn toàn **không bị trùng lặp dòng** và bảo toàn dữ liệu cũ.
- Trên giao diện phần mềm có nút **"📄 Xem file .txt"** ngay cạnh ô thư mục lưu để bạn mở và xem danh sách nhanh chóng bằng 1 cú click.

---

## 💻 Chuyển Ứng Dụng Sang Thiết Bị Khác (Rất Đơn Giản)

Khi chuyển thư mục ứng dụng này sang một máy tính Windows khác:

### 1. Trên thiết bị mới cần chuẩn bị:
- **Cài đặt Python 3.10 trở lên** (nếu máy mới chưa có):
  - Tải tại: [https://www.python.org/downloads/](https://www.python.org/downloads/)
  - **Lưu ý quan trọng:** Khi cài đặt trên Windows, ở màn hình đầu tiên nhớ **TICK chọn vào ô: `Add python.exe to PATH`**.

### 2. Các bước chuyển và chạy:
1. **Copy thư mục ứng dụng** sang thiết bị mới.
2. **Nhấp đúp vào file `run_gui.bat`:**
   - Ứng dụng sẽ **tự động kiểm tra**: Nếu phát hiện đây là máy mới hoặc chưa có thư viện, script sẽ **tự động tạo môi trường và tự cài đặt toàn bộ thư viện cần thiết (`requirements.txt`) trong 1 phút**, sau đó tự mở ứng dụng lên!
   - Bạn **không cần phải gõ bất kỳ câu lệnh nào bằng tay**.

---

## 🚀 Hướng Dẫn Khởi Chạy Nhanh (1 Click Trên Windows)

### Cách 1: Chạy File Cài Đặt Trực Tiếp (.EXE)
- Chạy trực tiếp file **`TikTokDownloaderPro.exe`** (không cần cài Python hay thư viện).

### Cách 2: Chạy Giao Diện Đồ Họa (GUI)
- Nhấp đúp chuột vào file: **`run_gui.bat`**
- Trong tab **"📺 Tải Danh Sách Kênh (Channels)"**, bạn có thể:
  - Dán danh sách nhiều kênh TikTok hoặc `@username` (mỗi kênh 1 dòng hoặc cách nhau bằng dấu phẩy).
  - Hoặc bấm nút **"📂 Nhập tệp .txt"** để chọn tệp danh sách các kênh cần tải.
  - Chọn số lượng video tải mỗi kênh (mặc định: Toàn bộ kênh).
  - Tùy chọn tick vào **"✂️ Lọc nhạy cảm 'tiktok'"** nếu muốn tự động cắt âm thanh và che logo chữ 'tiktok'.
- Nhấn **"🚀 BẮT ĐẦU QUÉT & TẢI TẤT CẢ KÊNH (SIÊU TỐC)"**. Ứng dụng sẽ tự động tải lần lượt từng kênh vào các thư mục riêng (`@kenh1`, `@kenh2`, ...).

### Cách 3: Chạy Dòng Lệnh (CLI)
- Mở terminal trong thư mục ứng dụng:
  ```powershell
  # Tải danh sách nhiều kênh trực tiếp từ dòng lệnh (cách nhau bằng dấu phẩy):
  .\.venv\Scripts\python.exe cli.py -c "@dung.mat_ket_noi, @openai, khaby.lame" --turbo

  # Tải kèm tính năng tự động lọc từ nhạy cảm 'tiktok':
  .\.venv\Scripts\python.exe cli.py -c "@openai" --turbo --censor

  # Tải danh sách kênh từ file văn bản (.txt):
  .\.venv\Scripts\python.exe cli.py -cf "danh_sach_kenh.txt" --turbo
  ```

---

## 🛠️ Khắc Phục Triệt Để Lỗi Video Chỉ Có Âm Thanh (Thiếu Hình Ảnh)

### 1. Nguyên nhân kỹ thuật:
- Trên TikTok có những bài đăng dạng **Slide ảnh / Album Carousel** (không có luồng video trực tiếp trên web).
- Khi tải đa luồng tốc độ cao (6-16 luồng), máy chủ TikWM giới hạn 1 req/s trả về mã bận. Bộ giải mã phụ (yt-dlp) tự động tải luồng âm thanh duy nhất (`acodec: mp3`, `vcodec: none`) và lưu nhầm thành tệp `.mp4`.
- Người dùng mở file lên xem thì chỉ nghe thấy tiếng mà không có hình.

### 2. Giải pháp đã tích hợp:
1. **Bộ Điều Tiết Tần Suất Thông Minh (Rate Limiter & Backoff):** Đồng bộ nhịp gọi API TikWM và SSSTik trên toàn bộ các luồng, đảm bảo 100% video đều lấy được link video MP4 gốc sạch watermark từ máy chủ.
2. **Kiểm Tra Header Video Nghiêm Ngặt (`is_valid_mp4`):** Trước khi lưu tệp `.mp4`, hệ thống kiểm tra cấu trúc ISO Media Container (`ftyp`). Nếu phát hiện tệp chỉ chứa âm thanh thuần túy (header `ID3`), hệ thống lập tức loại bỏ và chuyển sang nguồn dự phòng khác.
3. **Bộ Dựng Video Slide Ảnh Tự Động (`ffmpeg`):** Với các bài đăng dạng Album ảnh trên TikTok, hệ thống tự động tải toàn bộ ảnh HD và nhạc nền, sau đó dùng `ffmpeg` ghép thành một video MP4 chất lượng cao 1080p mượt mà với âm thanh gốc!
4. **Công Cụ Sửa Chữa Video Cũ 1-Click (`repair_audio_files.bat`):**
   - Nếu bạn đã có các video cũ tải về trước đây bị lỗi chỉ có tiếng:
   - Chỉ cần **nhấp đúp vào `repair_audio_files.bat`** hoặc bấm nút **"🔧 Quét & Sửa Lỗi Các Video Bị Thiếu Hình"** trong tab **Cài Đặt** của phần mềm.
   - Ứng dụng sẽ tự động quét toàn bộ thư mục `downloads` và tải lại các video chuẩn thay thế cho bạn!
