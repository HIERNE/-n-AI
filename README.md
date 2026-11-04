# Invoice Pro

Hệ thống tự động trích xuất và số hóa thông tin hóa đơn GTGT (hóa đơn đỏ)
sử dụng OCR (PaddleOCR + VietOCR) và dịch vụ xử lý ngôn ngữ để cấu trúc hóa dữ liệu.

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

Mã nguồn được tách thành `backend/` (FastAPI, Streamlit, OCR, database, scripts và tests) và `frontend/` (React/Vite). `.env`, `data/` và `logs/` vẫn ở thư mục gốc để giữ nguyên cấu hình và dữ liệu local.

Các màn hình React được chia riêng trong `frontend/src/page/`: `DashboardPage.tsx`, `UploadPage.tsx`, `HistoryPage.tsx`, `ExtractionPage.tsx`, `AccountingPage.tsx` và `ReportsPage.tsx`. `Workspace.tsx` giữ phần khung giao diện/điều hướng; `shared.tsx` và `utils.ts` chứa thành phần và hàm dùng chung giữa các trang.

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
ADMIN_EMAIL=admin@gmail.com
# Bỏ comment và điền thông tin thật nếu muốn dùng MySQL local thay SQLite:
# MYSQL_HOST=127.0.0.1
# MYSQL_PORT=3306
# MYSQL_USER=root
# MYSQL_PASSWORD=your_local_mysql_password
# MYSQL_DATABASE=invoice_parser
```

Gemini được ưu tiên; dịch vụ dự phòng được gọi theo cấu hình khi dịch vụ trước đó thất bại.
Các dòng `MYSQL_*` ở trên là ví dụ để chép vào `.env`; khai báo mặc định trong `backend/invoice_parser_config.py` không tự kết nối MySQL. Cần đặt `MYSQL_HOST` và mật khẩu thực tế trong `.env` để bật kết nối MySQL local.

### Tài khoản và phân quyền

- Cấu hình `ADMIN_USERNAME` và `ADMIN_PASSWORD` bằng thông tin riêng, đủ mạnh trong `.env` hoặc Streamlit Secrets. Không dùng mật khẩu mẫu ở trên. Tài khoản này được tạo hoặc cấp quyền quản trị khi ứng dụng kết nối database. Mật khẩu admin đã đổi trong ứng dụng sẽ được giữ lại sau khi khởi động lại; nếu admin quên mật khẩu, cập nhật `ADMIN_PASSWORD` trong cấu hình rồi khởi động lại để đặt mật khẩu mới.
- Khi chạy local, `.env` dùng MySQL local với schema `invoice_parser`. Hosting cloud nhận cấu hình database riêng qua environment/secrets của dịch vụ (ví dụ `MYSQL_DATABASE=invoice_parser_host`); không thêm cấu hình cloud thứ hai vào `.env` local vì dotenv đọc giá trị khai báo sau cùng. Dùng cùng `ADMIN_USERNAME`/`ADMIN_PASSWORD` ở local hoặc cloud không tự sao chép tài khoản giữa hai schema.
- Người dùng tự đăng ký qua giao diện sẽ luôn là tài khoản thường; mật khẩu yêu cầu tối thiểu 6 ký tự và sau đăng ký cần đăng nhập riêng. Có thể đăng nhập bằng email hoặc tên đăng nhập đã cấu hình trong `ADMIN_USERNAME`. Admin quản lý toàn bộ hóa đơn và là người duy nhất được đổi trạng thái duyệt/thanh toán.
- Form đăng ký yêu cầu địa chỉ Gmail hợp lệ (`@gmail.com`) cùng họ tên; người dùng có thể đăng nhập bằng Gmail hoặc tên đăng nhập cũ.
- Người dùng đã đăng nhập có thể đổi mật khẩu trong menu tài khoản; cần xác nhận mật khẩu hiện tại và mật khẩu mới tối thiểu 6 ký tự. Nếu quên mật khẩu, liên hệ quản trị viên để được hỗ trợ; ứng dụng không gửi email đặt lại mật khẩu.
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
   ADMIN_EMAIL = "admin@gmail.com"
   ```
   Có thể dùng `XAI_API_KEY` hoặc `DEEPSEEK_API_KEY` làm dịch vụ dự phòng cho Gemini.
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

### Giao diện React (chuyển đổi từng bước)

Frontend React hiện có đăng nhập/đăng ký, tổng quan, tải hóa đơn, lịch sử, trích xuất/chỉnh sửa dữ liệu, hạch toán, báo cáo, và đổi mật khẩu. FastAPI dùng chung tài khoản và database với ứng dụng hiện tại; Streamlit vẫn được giữ làm phương án dự phòng cho tới khi bản React được triển khai và kiểm thử trên hosting.

Chạy API và frontend trong hai cửa sổ terminal trên Windows:

1. Tại thư mục dự án, đặt khóa ký phiên đăng nhập ngẫu nhiên và chạy API:
   ```powershell
   $env:APP_AUTH_SECRET = (& .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))")
   .\.venv\Scripts\python.exe -m uvicorn api.main:app --app-dir .\backend --reload --reload-dir .\backend --host 127.0.0.1 --port 8000
   ```
   Chạy lệnh từ thư mục gốc của dự án (`smart_invoice_parser`). `--app-dir` giúp Uvicorn tìm mã trong `backend`, kể cả khi chạy tiến trình reload trên Windows; `--reload-dir` tránh theo dõi `frontend` và `node_modules`. API dùng `DATABASE_URL`/`MYSQL_*` hiện có và mặc định SQLite nếu chưa cấu hình MySQL. Không dùng khóa phát triển này để deploy.
2. Tại thư mục dự án, chạy giao diện:
   ```powershell
   npm run dev --prefix frontend
   ```
   Mở địa chỉ local do Vite in ra. Các request `/api` được proxy tới FastAPI.
3. Khi deploy React, cần FastAPI phục vụ frontend trên cùng một origin. `APP_ENV=production`, khóa `APP_AUTH_SECRET` dài ít nhất 32 ký tự và database ngoài được yêu cầu ở production. Nếu dùng domain riêng, thêm origin HTTPS chính xác vào `APP_ALLOWED_ORIGINS`. Web service tự thêm `RENDER_EXTERNAL_URL` vào danh sách origin được chấp nhận.

Streamlit Community Cloud hiện vẫn chạy giao diện Streamlit cũ; nó không tự deploy giao diện React mới. Chỉ chuyển URL chính sau khi các màn hình React và API tương ứng đã được kiểm thử, cấu hình database/file storage bền vững và triển khai trên hosting hỗ trợ FastAPI.

#### Deploy React + FastAPI trên Render

Repo có `render.yaml`, `Dockerfile` và `.dockerignore` để build frontend rồi chạy FastAPI trong cùng một web service. Blueprint cấu hình plan Standard và persistent disk 10 GB tại `/app/data` để các tệp hóa đơn không mất khi service restart. Kết quả OCR vẫn cần database TiDB/MySQL bền vững; không dùng SQLite làm database production.

1. Đẩy các thay đổi lên GitHub, rồi trên Render chọn **New → Blueprint** và kết nối repository này.
2. Trong phần environment của service, đặt `DATABASE_URL` tới TiDB, `GEMINI_API_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` mạnh và `ADMIN_EMAIL`. Render tự sinh `APP_AUTH_SECRET`; không tự thay bằng khóa dùng local.
3. Nếu dùng domain riêng, đặt `APP_ALLOWED_ORIGINS` thành origin HTTPS chính xác, ví dụ `https://invoice.example.com` (không có dấu `/` cuối). URL `onrender.com` mặc định được nhận diện tự động.
4. Chờ Docker build và health check hoàn tất; thử đăng nhập, tải một hóa đơn nhỏ, kiểm tra trạng thái OCR và mở lại tệp sau khi service restart. Kiểm tra log nếu OCR thiếu bộ nhớ; tăng plan khi cần.

Không gửi các khóa/credentials trong chat hoặc commit chúng vào repository. Chưa có deploy production nào được thực hiện cho tới khi repository được kết nối trong tài khoản Render và các Secrets được cấu hình.

Nhật ký file của web được ghi vào `logs/app.log` trong môi trường chạy ứng dụng. Trên dịch vụ hosting có filesystem tạm thời, file này có thể mất khi restart/redeploy; hãy tải log xuống trước khi restart nếu cần giữ. Nhật ký không được đẩy lên MySQL.

#### Chuyển dữ liệu SQLite local sang MySQL Cloud

Chạy trên máy đang có file SQLite gốc, không chạy trên Streamlit Cloud:

1. Sao lưu `data/outputs/invoices.db` và giữ nguyên file gốc. Tạo `.env` local (file này đã bị Git ignore) với `DATABASE_URL` trỏ đến đúng MySQL Cloud, hoặc điền các biến `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`.
2. Chạy xem trước; lệnh này chỉ đọc SQLite và kiểm tra số bản ghi ở database đích:
   ```bash
   cd backend
   python -m scripts.migrate_sqlite_to_mysql
   ```
3. Chỉ khi số liệu nguồn đúng và database đích đúng, thực hiện chuyển:
   ```bash
   cd backend
   python -m scripts.migrate_sqlite_to_mysql --apply
   ```
   Công cụ giữ nguyên tài khoản người dùng (bao gồm hash mật khẩu), ID/chủ sở hữu hóa đơn, trạng thái hạch toán/thanh toán, dữ liệu mặt hàng và lịch sử job; không sửa SQLite nguồn. Để tránh ghi đè/trùng, công cụ từ chối chạy nếu các bảng `users`, `invoices` hoặc `processing_jobs` trong MySQL đích đã có dữ liệu.
4. Redeploy ứng dụng với Secrets trỏ đúng database MySQL đó. Giữ bản sao SQLite đến khi kiểm tra số hóa đơn và báo cáo trên Cloud.

Nếu MySQL đã có hóa đơn/job và chỉ cần bổ sung tài khoản từ SQLite, dùng:
```bash
cd backend
python -m scripts.migrate_sqlite_to_mysql --users-only
```
Lệnh chỉ thêm tài khoản chưa có (đối chiếu username không phân biệt hoa/thường), giữ nguyên hash mật khẩu, không ghi đè admin hiện có và không sửa hóa đơn/job. Chỉ tài khoản admin được cấu hình trong môi trường mới được giữ quyền admin khi nhập.

Các file PDF/ảnh được lưu riêng trong `data/uploads` và `data/raw`, không nhúng vào SQLite và không được chuyển bởi công cụ này. Muốn tiếp tục xem ảnh trên Cloud cần đưa các file đó lên lưu trữ bền vững và liên kết chúng với hóa đơn; SQLite transfer chỉ khôi phục bản ghi, trạng thái, lịch sử và dữ liệu phục vụ báo cáo.

### Kiểm tra cảnh báo hóa đơn trùng

1. Tải lên và xử lý thành công một hóa đơn.
2. Tải lại đúng tệp đó (có thể đổi tên tệp). Nếu đã có dữ liệu trích xuất gắn với SHA-256 đó, hệ thống liên kết job mới với hóa đơn cũ, ghi trạng thái **Trùng hóa đơn** và không chạy OCR lần nữa. Nếu chưa có dữ liệu cũ để liên kết, hệ thống yêu cầu chọn **Tiếp tục xử lý** hoặc **Bỏ qua hóa đơn này**.
3. Nếu đổi tên và nội dung hóa đơn giống nhau nhưng tệp được scan/nén lại, cảnh báo sẽ dựa trên số hóa đơn, MST bên bán, ngày lập và tổng thanh toán sau khi trích xuất.
4. Xem các nhóm nghi trùng ở trang **Báo cáo tổng hợp**. Với dữ liệu đã có trước khi bổ sung SHA-256, cần tải lại tệp cũ hoặc nhập số hóa đơn để hệ thống đối chiếu được.
5. Trong **Lịch sử hóa đơn**, thao tác **Xóa hóa đơn trùng** sẽ chỉ xóa bản trích xuất khớp cùng MST bên bán, số hóa đơn, ngày lập và tổng thanh toán (sai số tối đa 1 đồng), cùng các job thành công/lỗi tương ứng. Bản gốc xử lý sớm nhất được giữ lại; các trường hợp cùng số hóa đơn nhưng khác ngày hoặc số tiền không bị xóa. Cần xác nhận trước khi xóa.

## Cách chạy

### Chạy pipeline xử lý 1 hóa đơn
```bash
cd backend
python -m src.pipeline --input ..\data\raw\invoice_01.jpg
```

### Chạy giao diện Streamlit
```bash
streamlit run backend/app/streamlit_app.py
```

### Chạy đánh giá mô hình
```bash
cd backend
python -m src.evaluation.ocr_metrics
python -m src.evaluation.extraction_metrics
```

## Cấu trúc dự án
Xem chi tiết trong `docs/architecture_diagram.png`

## Công nghệ sử dụng
- **OCR**: PaddleOCR (detection), VietOCR (recognition)
- **Structuring**: Gemini, dịch vụ dự phòng, DeepSeek API + Pydantic
- **UI**: Streamlit (ứng dụng hiện tại), React + TypeScript (bản chuyển đổi)
- **API**: FastAPI
- **Lưu trữ**: Excel (openpyxl) / SQLite (SQLAlchemy)

## Tác giả
Võ Minh Hiển và Trần Minh Khâm - Đại học Kiến trúc Đà Nẵng - Lớp 23CT2
Đồ án môn Trí tuệ nhân tạo
