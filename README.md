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
ADMIN_USERNAME=admin
ADMIN_PASSWORD=replace_with_a_long_unique_password
# Bỏ comment và điền thông tin thật nếu muốn dùng MySQL local thay SQLite:
# MYSQL_HOST=127.0.0.1
# MYSQL_PORT=3306
# MYSQL_USER=root
# MYSQL_PASSWORD=your_local_mysql_password
# MYSQL_DATABASE=invoice_parser
```

Gemini được ưu tiên. xAI chỉ được gọi dự phòng sau khi các API key Gemini đều thất bại; DeepSeek được gọi cuối cùng nếu xAI cũng thất bại.
Các dòng `MYSQL_*` ở trên là ví dụ để chép vào `.env`; khai báo mặc định trong `invoice_parser_config.py` không tự kết nối MySQL. Cần đặt `MYSQL_HOST` và mật khẩu thực tế trong `.env` để bật kết nối MySQL local.

### Tài khoản và phân quyền

- Cấu hình `ADMIN_USERNAME` và `ADMIN_PASSWORD` bằng thông tin riêng, đủ mạnh trong `.env` hoặc Streamlit Secrets. Không dùng mật khẩu mẫu ở trên. Tài khoản này được tạo/cập nhật thành admin khi ứng dụng kết nối database.
- Người dùng tự đăng ký qua giao diện sẽ luôn là tài khoản thường; mật khẩu yêu cầu tối thiểu 6 ký tự và sau đăng ký cần đăng nhập riêng. Admin quản lý toàn bộ hóa đơn và là người duy nhất được đổi trạng thái duyệt/thanh toán.
- Form đăng ký yêu cầu địa chỉ Gmail hợp lệ (`@gmail.com`) cùng họ tên; người dùng có thể đăng nhập bằng Gmail hoặc tên đăng nhập cũ.
- Không có tài khoản/mật khẩu admin mặc định trong mã nguồn. Admin được tạo từ `ADMIN_USERNAME` và `ADMIN_PASSWORD` do người triển khai cấu hình. Nếu chưa cấu hình hai giá trị này thì chưa có admin bootstrap.
- Tài khoản nằm trong bảng `users` của database được cấu hình (`data/outputs/invoices.db` khi dùng SQLite; hoặc database đích khi đặt `DATABASE_URL`/MySQL). Mật khẩu chỉ lưu dưới dạng hash PBKDF2, không lưu mật khẩu gốc.
- Khi ứng dụng khởi động, nó tạo/migrate các bảng `users`, `invoices` và `processing_jobs` trong đúng database mà cấu hình hiện tại trỏ tới. Nếu không thấy `users` trong MySQL, kiểm tra `DATABASE_URL` hoặc các giá trị `MYSQL_*` ở cả app local và web: chúng có thể đang trỏ tới SQLite, hoặc tới một schema/database MySQL khác.
- Hóa đơn và lịch sử xử lý mới gắn với tài khoản tải lên. User chỉ xem dữ liệu của mình; admin xem được toàn hệ thống. Khi admin được khởi tạo, dữ liệu hóa đơn/lịch sử cũ chưa có chủ sở hữu sẽ được gán cho admin.
- Hóa đơn có từ trước khi tài khoản được tạo không lưu thông tin người tải lên; giao diện quản trị sẽ ghi “Chưa xác định” thay vì gán nhầm người tải lên. Các hóa đơn mới sẽ hiển thị tên/email hoặc tên đăng nhập của tài khoản đã tải.
- Ảnh/PDF hiện vẫn lưu trong thư mục `data/uploads`; cần dùng lưu trữ file riêng có kiểm soát truy cập nếu triển khai nhiều người dùng qua Internet.
- Lỗi kỹ thuật và nhật ký hoạt động (khởi động, đăng ký, đăng nhập/đăng xuất, xử lý hóa đơn, đổi trạng thái) đều ghi vào `logs/app.log`. Hoạt động có tiền tố `ACTIVITY` và nội dung JSON; không ghi mật khẩu/email hay lưu nhật ký vào DB. File tự xoay vòng (5 MB, giữ tối đa 5 file). Các cột log lỗi cũ trong database được xóa nội dung khi nâng cấp; công cụ chuyển SQLite → MySQL không chuyển log.

### Deploy lên Streamlit Community Cloud

1. Trong **App settings → Secrets**, cấu hình API key theo định dạng TOML, ví dụ:
   ```toml
   GEMINI_API_KEY = "your_key_here"
   ADMIN_USERNAME = "admin"
   ADMIN_PASSWORD = "a-long-unique-password"
   ```
   Có thể dùng `XAI_API_KEY` hoặc `DEEPSEEK_API_KEY` thay cho Gemini.
2. SQLite và các file trong `data/` bị `.gitignore` loại khỏi Git; Cloud không nhận database hay hóa đơn trên máy local. SQLite trên ổ đĩa của Community Cloud cũng không phải nơi lưu trữ bền vững.
3. Để giữ dữ liệu giữa các lần khởi động, tạo một MySQL database bên ngoài có thể truy cập từ Cloud và thêm các giá trị vào Secrets. Nếu muốn local và web nhìn thấy chung tài khoản/hóa đơn/trạng thái, cấu hình cả hai môi trường dùng cùng host, database/schema và cùng credentials. Nếu muốn thử nghiệm tách biệt để tránh sửa nhầm dữ liệu thật, dùng database/schema riêng cho local; không cần database riêng trên web trừ khi muốn cô lập dữ liệu:
   ```toml
   MYSQL_HOST = "database-host"
   MYSQL_PORT = "3306"
   MYSQL_USER = "invoice_user"
   MYSQL_PASSWORD = "database-password"
   MYSQL_DATABASE = "invoice_parser"
   ```
   Hoặc cung cấp `DATABASE_URL` dạng `mysql+pymysql://...` kết nối tới dịch vụ MySQL bền vững. Nếu mật khẩu có ký tự đặc biệt, URL-encode phần username/password hoặc dùng các biến `MYSQL_*` ở trên. Không đưa API key, mật khẩu, file `.env` hay database chứa dữ liệu hóa đơn vào Git.
4. Database MySQL mới sẽ không tự có các bản ghi trong `data/outputs/invoices.db` trên máy local. Muốn khôi phục dữ liệu hiện có, cần chuyển các bản ghi từ database local sang database Cloud; giữ bản sao lưu gốc trong suốt quá trình chuyển.

Nhật ký file của web được ghi vào `logs/app.log` trong môi trường chạy ứng dụng. Trên dịch vụ hosting có filesystem tạm thời, file này có thể mất khi restart/redeploy; hãy tải log xuống trước khi restart nếu cần giữ. Nhật ký không được đẩy lên MySQL.

#### Chuyển dữ liệu SQLite local sang MySQL Cloud

Chạy trên máy đang có file SQLite gốc, không chạy trên Streamlit Cloud:

1. Sao lưu `data/outputs/invoices.db` và giữ nguyên file gốc. Tạo `.env` local (file này đã bị Git ignore) với `DATABASE_URL` trỏ đến đúng MySQL Cloud, hoặc điền các biến `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`.
2. Chạy xem trước; lệnh này chỉ đọc SQLite và kiểm tra số bản ghi ở database đích:
   ```bash
   python -m scripts.migrate_sqlite_to_mysql
   ```
3. Chỉ khi số liệu nguồn đúng và database đích đúng, thực hiện chuyển:
   ```bash
   python -m scripts.migrate_sqlite_to_mysql --apply
   ```
   Công cụ giữ nguyên tài khoản người dùng (bao gồm hash mật khẩu), ID/chủ sở hữu hóa đơn, trạng thái hạch toán/thanh toán, dữ liệu mặt hàng và lịch sử job; không sửa SQLite nguồn. Để tránh ghi đè/trùng, công cụ từ chối chạy nếu các bảng `users`, `invoices` hoặc `processing_jobs` trong MySQL đích đã có dữ liệu.
4. Redeploy ứng dụng với Secrets trỏ đúng database MySQL đó. Giữ bản sao SQLite đến khi kiểm tra số hóa đơn và báo cáo trên Cloud.

Nếu MySQL đã có hóa đơn/job và chỉ cần bổ sung tài khoản từ SQLite, dùng:
```bash
python -m scripts.migrate_sqlite_to_mysql --users-only
```
Lệnh chỉ thêm tài khoản chưa có (đối chiếu username không phân biệt hoa/thường), giữ nguyên hash mật khẩu, không ghi đè admin hiện có và không sửa hóa đơn/job. Chỉ tài khoản admin được cấu hình trong môi trường mới được giữ quyền admin khi nhập.

Các file PDF/ảnh được lưu riêng trong `data/uploads` và `data/raw`, không nhúng vào SQLite và không được chuyển bởi công cụ này. Muốn tiếp tục xem ảnh trên Cloud cần đưa các file đó lên lưu trữ bền vững và liên kết chúng với hóa đơn; SQLite transfer chỉ khôi phục bản ghi, trạng thái, lịch sử và dữ liệu phục vụ báo cáo.

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
