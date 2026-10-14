# Smart Invoice Parser

Hệ thống tự động trích xuất và số hóa thông tin hóa đơn GTGT (hóa đơn đỏ)
sử dụng OCR (PaddleOCR + VietOCR) kết hợp LLM (Gemini API) để cấu trúc hóa dữ liệu.

## Tính năng chính
- Trích xuất tự động: MST, tên công ty, ngày lập, danh sách mặt hàng, tổng tiền, thuế VAT
- Giao diện kiểm đối side-by-side (ảnh gốc + dữ liệu trích xuất)
- Cảnh báo sai lệch dữ liệu và báo cáo các hóa đơn cần rà soát trước khi hạch toán
- Theo dõi tình trạng thanh toán bằng combobox trực tiếp trong bảng, lọc danh sách và xuất Excel theo bộ lọc
- Phát hiện nhóm hóa đơn có khả năng trùng dựa trên MST bên bán, số hóa đơn, ngày lập và tổng thanh toán
- Cảnh báo ngay trước OCR nếu tệp tải lên có nội dung giống tệp đã xử lý; tiếp tục đối chiếu dữ liệu hóa đơn sau OCR
- Lưu kết quả vào Excel/SQLite
- Đánh giá độ chính xác OCR (CER) và trích xuất (Precision/Recall)

## Cài đặt

```bash
git clone <repo-url>
cd smart_invoice_parser
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Tạo file `.env` và thêm API key:
```env
GEMINI_API_KEY=your_key_here
XAI_API_KEY=your_xai_key_here
# Tùy chọn; mặc định là grok-4.7
XAI_MODEL_NAME=grok-4.7
# Tùy chọn dự phòng sau xAI; có thể dùng tên biến DEEPSEEK_API_KEY thay cho DEEPSEEK
DEEPSEEK=your_deepseek_key_here
# Tùy chọn; mặc định là deepseek-chat
DEEPSEEK_MODEL_NAME=deepseek-chat
```

Gemini được ưu tiên. xAI chỉ được gọi dự phòng sau khi các API key Gemini đều thất bại; DeepSeek được gọi cuối cùng nếu xAI cũng thất bại.

### Kiểm tra cảnh báo hóa đơn trùng

1. Tải lên và xử lý thành công một hóa đơn.
2. Tải lại đúng tệp đó (có thể đổi tên tệp). Nếu đã có dữ liệu trích xuất gắn với SHA-256 đó, hệ thống liên kết job mới với hóa đơn cũ, ghi trạng thái **Trùng hóa đơn** và không chạy OCR lần nữa. Nếu chưa có dữ liệu cũ để liên kết, hệ thống yêu cầu chọn **Tiếp tục xử lý** hoặc **Bỏ qua hóa đơn này**.
3. Nếu đổi tên và nội dung hóa đơn giống nhau nhưng tệp được scan/nén lại, cảnh báo sẽ dựa trên số hóa đơn, MST bên bán, ngày lập và tổng thanh toán sau khi AI trích xuất.
4. Xem các nhóm nghi trùng ở trang **Báo cáo tổng hợp**. Với dữ liệu đã có trước khi bổ sung SHA-256, cần tải lại tệp cũ hoặc nhập số hóa đơn để hệ thống đối chiếu được.
5. Trong **Lịch sử hóa đơn**, thao tác **Xóa hóa đơn trùng** sẽ chỉ xóa bản trích xuất khớp cùng MST bên bán, số hóa đơn, ngày lập và tổng thanh toán (sai số tối đa 1 đồng), cùng các job thành công/lỗi tương ứng. Bản gốc xử lý sớm nhất được giữ lại; các trường hợp cùng số hóa đơn nhưng khác ngày hoặc số tiền không bị xóa. Cần xác nhận trước khi xóa.

## Cách chạy

### Chạy pipeline xử lý 1 hóa đơn
```bash
python -m src.pipeline --input data/raw/invoice_01.jpg
```

### Chạy giao diện Streamlit
```bash
streamlit run app/streamlit_app.py
```

### Chạy đánh giá mô hình
```bash
python -m src.evaluation.ocr_metrics
python -m src.evaluation.extraction_metrics
```

## Cấu trúc dự án
Xem chi tiết trong `docs/architecture_diagram.png`

## Công nghệ sử dụng
- **OCR**: PaddleOCR (detection), VietOCR (recognition)
- **Structuring**: Gemini, xAI và DeepSeek API + Pydantic
- **UI**: Streamlit
- **Lưu trữ**: Excel (openpyxl) / SQLite (SQLAlchemy)

## Tác giả
Võ Minh Hiển và Trần Minh Khâm - Đại học Kiến trúc Đà Nẵng - Lớp 23CT2
Đồ án môn Trí tuệ nhân tạo
