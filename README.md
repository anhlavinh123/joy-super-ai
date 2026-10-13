# HƯỚNG DẪN TRIỂN KHAI JOY SUPER AI LÊN CLOUD MIỄN PHÍ 24/7
(Không Cần Mở Máy Tính - Không Tốn Chi Phí - Độc Lập 100%)

---

## 🎯 Mục Tiêu
Đưa máy chủ riêng của Joy lên dịch vụ Cloud miễn phí vĩnh viễn (như **Render.com** hoặc **Hugging Face Spaces**) để:
1. Bạn có thể **tắt máy tính, gập laptop** bất cứ lúc nào, Joy vẫn hoạt động 24/24.
2. Joy kết nối qua giao thức bảo mật `wss://...` trực tiếp từ Wi-Fi của bạn.
3. Thoát hoàn toàn khỏi server `api.tenclass.net`, 100% dữ liệu và AI do bạn làm chủ.

---

## 🚀 Cách 1: Triển Khai Miễn Phí Qua Render.com (Khuyên Dùng - Nhanh Nhất)
1. Truy cập [render.com](https://render.com) và đăng ký/đăng nhập (bằng tài khoản GitHub hoặc Google).
2. Tạo 1 repository mới trên GitHub cá nhân (đặt tên ví dụ: `joy-super-ai`).
3. Đẩy 3 file trong thư mục này lên GitHub repo đó:
   - `xiaozhi_private_server.py`
   - `requirements.txt`
   - `Dockerfile`
4. Trên Dashboard của **Render**:
   - Chọn **New +** -> Chọn **Web Service**.
   - Kết nối tới repo `joy-super-ai` vừa tạo.
   - Phần **Environment** chọn: `Docker`.
   - Phần **Instance Type** chọn: `Free`.
   - Nhấn **Deploy Web Service**.
5. Sau 2-3 phút, Render sẽ cấp cho bạn một đường link công khai dạng:
   `https://joy-super-ai.onrender.com`
   Đường link WebSocket tương ứng của bạn sẽ là:
   `wss://joy-super-ai.onrender.com/xiaozhi/v1/`
6. Quay lại máy tính, chạy lệnh nạp địa chỉ này vào robot Joy (chỉ làm 1 lần duy nhất). Xong là Joy hoàn toàn độc lập!

---

## 🚀 Cách 2: Triển Khai Miễn Phí Qua Hugging Face Spaces
1. Truy cập [huggingface.co](https://huggingface.co) và tạo tài khoản miễn phí.
2. Chọn **New Space**:
   - Space name: `joy-robot`
   - Space SDK: chọn **Docker** (Blank)
   - Privacy: **Public**
3. Tải lên 3 file: `xiaozhi_private_server.py`, `requirements.txt`, `Dockerfile`.
4. Hugging Face sẽ tự động build và chạy container 24/7 miễn phí.
5. Đường link WebSocket trực tiếp:
   `wss://<username>-joy-robot.hf.space/xiaozhi/v1/`

---

## 🔄 Nạp Địa Chỉ Cloud Mới Vào Robot Joy
Khi bạn có link `wss://...` từ Render hoặc Hugging Face, chỉ cần chạy file:
`patch_cloud_url.py` (chúng tôi đã tạo sẵn cho bạn) và nạp vào robot bằng cổng USB `COM5`.
Sau khi nạp xong, rút cáp USB ra, Joy sẽ tự động chạy độc lập vĩnh viễn!
