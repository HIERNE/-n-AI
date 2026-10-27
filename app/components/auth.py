import re
from datetime import datetime
from pathlib import Path
import streamlit as st

from src.storage.db_handler import (
    authenticate_user,
    get_auth_configuration,
    initialize_database,
    register_user,
)
from src.logging_config import log_activity

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
_DATABASE_INITIALIZED = False


def _render_html(html_str: str) -> None:
    """Render HTML chuẩn xác, loại bỏ hoàn toàn khoảng trắng thụt lề ở từng dòng."""
    cleaned = "\n".join(line.strip() for line in html_str.splitlines() if line.strip())
    st.markdown(cleaned, unsafe_allow_html=True)


AUTH_PAGE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap');

/* 1. Ẩn hoàn toàn các thành phần UI mặc định của Streamlit */
header, [data-testid="stHeader"], footer, .stApp header,
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], #MainMenu,
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarNav"] {
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}

/* 2. KHÓA CHẶT MÀN HÌNH Ở CẤP ĐỘ ROOT (HTML, BODY) */
html, body {
    background-color: #FFFFFF !important;
    margin: 0 !important;
    padding: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    max-width: 100vw !important;
    max-height: 100vh !important;
    overflow: hidden !important; /* Chặn hoàn toàn thanh cuộn */
    position: fixed !important; /* Khóa khung hình vào cửa sổ trình duyệt */
    top: 0 !important; 
    left: 0 !important;
    touch-action: none !important; /* Ngăn chặn vuốt trượt trên thiết bị cảm ứng */
    font-family: 'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

/* 3. TIÊU DIỆT KHOẢNG TRẮNG THỪA BÊN DƯỚI (Thủ phạm gây cuộn) */
/* Streamlit luôn tự động thêm padding-bottom ~10rem, ta bắt buộc phải ép về 0 */
.stApp,
div[data-testid="stAppViewContainer"],
div[data-testid="stMain"],
div[data-testid="stMain"] > div.block-container,
.main .block-container,
div.block-container {
    width: 100vw !important;
    height: 100vh !important;
    max-width: 100vw !important;
    max-height: 100vh !important;
    margin: 0 !important;
    padding-top: 0 !important;
    padding-bottom: 0 !important; /* ĐÂY LÀ DÒNG CHỐNG TRƯỢT KHOẢNG TRẮNG DƯỚI CÙNG */
    padding-left: 0 !important;
    padding-right: 0 !important;
    overflow: hidden !important;
    position: absolute !important;
    top: 0 !important; 
    left: 0 !important; 
    right: 0 !important; 
    bottom: 0 !important;
}

/* 4. Khung 2 cột chính tràn viền (100vh) */
div[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:first-of-type,
.main .block-container > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"] {
    height: 100vh !important;
    min-height: 100vh !important;
    max-height: 100vh !important;
    margin: 0 !important;
    padding: 0 !important;
    gap: 0 !important; /* Vô hiệu hóa 'gap' của Streamlit để ko trồi sụt bố cục */
    align-items: stretch !important;
    overflow: hidden !important;
}

/* Cột Hero (Bên trái) */
div[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="stColumn"]:first-child,
div[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="column"]:first-child {
    padding: 0 !important;
    margin: 0 !important;
    height: 100vh !important;
    max-height: 100vh !important;
    overflow: hidden !important;
}

.auth-hero-pane {
    background: linear-gradient(145deg, #303E9F 0%, #3B4BBE 40%, #4758CF 75%, #5163DF 100%) !important;
    height: 100vh !important;
    padding: 56px 64px !important;
    position: relative !important;
    overflow: hidden !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: space-between !important;
    color: #FFFFFF !important;
    box-sizing: border-box !important;
    width: 100% !important;
}

/* Cột Form (Bên phải) */
div[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="stColumn"]:last-child,
div[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="column"]:last-child {
    background: #FFFFFF !important;
    padding: 32px 48px !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
    align-items: center !important;
    box-sizing: border-box !important;
    height: 100vh !important;
    max-height: 100vh !important;
    overflow: hidden !important; /* Không cho cuộn khối form */
}

/* Khung form rộng chuẩn 380px cân xứng */
div[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="stColumn"]:last-child > div[data-testid="stVerticalBlock"],
div[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="column"]:last-child > div[data-testid="stVerticalBlock"] {
    width: 100% !important;
    max-width: 384px !important;
    margin: auto !important;
}

/* Reset các khối hàng ngang nằm bên trong form */
form div[data-testid="stHorizontalBlock"] {
    min-height: auto !important;
    height: auto !important;
    padding: 0 !important;
    margin: 6px 0 14px 0 !important;
    background: transparent !important;
    align-items: center !important;
}
form div[data-testid="stHorizontalBlock"] :is(div[data-testid="column"], div[data-testid="stColumn"]) {
    background: transparent !important;
    min-height: auto !important;
    height: auto !important;
    padding: 0 !important;
}

/* Chi tiết Cột Hero (Bên trái) */
.hero-top-logo {
    display: flex;
    align-items: center;
    gap: 12px;
}
.hero-logo-box {
    width: 42px;
    height: 42px;
    border-radius: 11px;
    background: rgba(255, 255, 255, 0.16);
    border: 1px solid rgba(255, 255, 255, 0.25);
    display: flex;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(8px);
    flex-shrink: 0;
}
.hero-logo-title {
    font-size: 21px;
    font-weight: 700;
    color: #FFFFFF;
    letter-spacing: -0.4px;
}
.hero-middle-content {
    margin: 32px 0;
}
.hero-badge-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(255, 255, 255, 0.14);
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 9999px;
    padding: 5px 13px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    color: #F1F5F9;
    text-transform: uppercase;
    margin-bottom: 22px;
}
.hero-badge-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #22C55E;
    box-shadow: 0 0 8px #22C55E;
}
.hero-main-heading {
    font-size: 44px;
    font-weight: 800;
    line-height: 1.14;
    color: #FFFFFF;
    letter-spacing: -1.2px;
    margin: 0 0 16px 0;
}
.hero-sub-description {
    font-size: 14.5px;
    line-height: 1.6;
    color: rgba(255, 255, 255, 0.82);
    max-width: 430px;
    margin-bottom: 34px;
}
.hero-feature-list {
    display: flex;
    flex-direction: column;
    gap: 15px;
}
.hero-feature-row {
    display: flex;
    align-items: center;
    gap: 13px;
}
.hero-feature-squircle {
    width: 36px;
    height: 36px;
    border-radius: 9px;
    background: rgba(255, 255, 255, 0.12);
    border: 1px solid rgba(255, 255, 255, 0.18);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}
.hero-feature-label {
    font-size: 13.5px;
    font-weight: 500;
    color: #FFFFFF;
}
.hero-bottom-copyright {
    font-size: 12.5px;
    color: rgba(255, 255, 255, 0.52);
    padding-top: 16px;
}
.hero-decorative-rings {
    position: absolute;
    right: -100px;
    bottom: -100px;
    width: 520px;
    height: 520px;
    pointer-events: none;
    z-index: 1;
}

/* Tab Segmented Control [ Đăng nhập ] [ Đăng ký ] */
div[data-testid="stRadio"] {
    display: flex !important;
    justify-content: center !important;
    width: 100% !important;
    margin-bottom: 24px !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"] {
    display: flex !important;
    flex-direction: row !important;
    background: #F1F4F9 !important;
    border-radius: 12px !important;
    padding: 3px !important;
    gap: 3px !important;
    width: 310px !important;
    margin: 0 auto !important;
    border: none !important;
}
div[data-testid="stRadio"] label {
    flex: 1 1 0 !important;
    justify-content: center !important;
    align-items: center !important;
    text-align: center !important;
    margin: 0 !important;
    padding: 8px 14px !important;
    border-radius: 9px !important;
    cursor: pointer !important;
    background: transparent !important;
    transition: all 0.2s ease !important;
}
div[data-testid="stRadio"] input[type="radio"] {
    display: none !important;
    position: absolute !important;
}
div[data-testid="stRadio"] label > div:not(:has(p)),
div[data-testid="stRadio"] label > span {
    display: none !important;
}
div[data-testid="stRadio"] label p {
    color: #64748B !important;
    font-weight: 500 !important;
    font-size: 13px !important;
    margin: 0 !important;
    text-align: center !important;
}
div[data-testid="stRadio"] label:has(input:checked) {
    background: #FFFFFF !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.07) !important;
}
div[data-testid="stRadio"] label:has(input:checked) p {
    color: #0F172A !important;
    font-weight: 600 !important;
}

/* Tiêu đề Form */
.form-heading-title {
    font-size: 25px !important;
    font-weight: 700 !important;
    color: #0F172A !important;
    letter-spacing: -0.4px !important;
    margin: 0 0 6px 0 !important;
    line-height: 1.25 !important;
}
.form-heading-desc {
    font-size: 13px !important;
    color: #64748B !important;
    margin: 0 0 20px 0 !important;
    line-height: 1.45 !important;
}

/* Form và Input Streamlit */
div[data-testid="stForm"] {
    border: none !important;
    padding: 0 !important;
    background: transparent !important;
    width: 100% !important;
}
div[data-testid="stTextInput"] {
    margin-bottom: 11px !important;
}
div[data-testid="stTextInput"] label p {
    color: #334155 !important;
    font-weight: 600 !important;
    font-size: 12.5px !important;
    margin-bottom: 5px !important;
}
div[data-baseweb="input"],
div[data-baseweb="base-input"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 10px !important;
    height: 44px !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}
div[data-baseweb="input"]:focus-within {
    border-color: #4F46E5 !important;
    box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.12) !important;
}
div[data-baseweb="input"] input {
    color: #1E293B !important;
    font-size: 13.5px !important;
    -webkit-text-fill-color: #1E293B !important;
    background-color: transparent !important;
}
div[data-baseweb="input"] input::placeholder {
    color: #94A3B8 !important;
    -webkit-text-fill-color: #94A3B8 !important;
    font-size: 13px !important;
}

/* Nhúng biểu tượng vào bên trái các Input */
input[placeholder*="Nguyễn Văn"] {
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2394A3B8' stroke-width='1.8'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' d='M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z'/%3E%3C/svg%3E") !important;
    background-repeat: no-repeat !important;
    background-position: 13px center !important;
    background-size: 17px 17px !important;
    padding-left: 40px !important;
}
input[placeholder*="name@company"],
input[placeholder*="@company"] {
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2394A3B8' stroke-width='1.8'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' d='M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z'/%3E%3C/svg%3E") !important;
    background-repeat: no-repeat !important;
    background-position: 13px center !important;
    background-size: 17px 17px !important;
    padding-left: 40px !important;
}
input[type="password"] {
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2394A3B8' stroke-width='1.8'%3E%3Crect x='4' y='11' width='16' height='10' rx='2' ry='2'/%3E%3Cpath d='M7 11V7a5 5 0 0 1 10 0v4'/%3E%3C/svg%3E") !important;
    background-repeat: no-repeat !important;
    background-position: 13px center !important;
    background-size: 17px 17px !important;
    padding-left: 40px !important;
    padding-right: 42px !important;
}

/* Checkbox */
div[data-testid="stCheckbox"] {
    margin: 0 !important;
}
div[data-testid="stCheckbox"] label p {
    font-size: 12.5px !important;
    color: #475569 !important;
    margin: 0 !important;
    line-height: 1.4 !important;
}
div[data-testid="stCheckbox"] label p a {
    color: #4F46E5 !important;
    font-weight: 500 !important;
    text-decoration: none !important;
}
div[data-testid="stCheckbox"] label span[role="checkbox"] {
    border-radius: 4px !important;
}

/* Nút Submit chính */
form[data-testid="stForm"] button[kind="primary"] {
    background: #4F46E5 !important;
    border: none !important;
    border-radius: 10px !important;
    height: 44px !important;
    font-size: 14.5px !important;
    font-weight: 600 !important;
    color: #FFFFFF !important;
    box-shadow: 0 4px 12px rgba(79, 70, 229, 0.28) !important;
    margin-top: 6px !important;
    transition: all 0.15s ease !important;
    width: 100% !important;
}
form[data-testid="stForm"] button[kind="primary"]:hover {
    background: #4338CA !important;
    box-shadow: 0 6px 16px rgba(79, 70, 229, 0.36) !important;
    transform: translateY(-1px);
}
form[data-testid="stForm"] button[kind="primary"] p {
    color: #FFFFFF !important;
    font-weight: 600 !important;
    font-size: 14.5px !important;
}

/* Dòng chuyển đổi dưới form */
.auth-switch-box {
    text-align: center;
    margin-top: 14px;
    font-size: 12.5px;
    color: #64748B;
}
.auth-switch-box a {
    color: #4F46E5;
    font-weight: 600;
    text-decoration: none;
    margin-left: 3px;
}
.auth-switch-box a:hover {
    text-decoration: underline;
}

/* Dòng bảo mật SSL */
.auth-security-ssl {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    font-size: 11.5px;
    color: #94A3B8;
    margin-top: 22px;
}

/* Khi màn hình quá nhỏ (điện thoại), CHỈ Ở LÚC NÀY mới mở khóa Scroll */
@media (max-width: 960px) {
    html, body, .stApp, 
    div[data-testid="stAppViewContainer"], div[data-testid="stMain"], .main .block-container {
        position: relative !important;
        height: auto !important;
        max-height: auto !important;
        overflow-y: auto !important; 
        touch-action: auto !important; 
    }
    div[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:first-of-type {
        flex-direction: column !important;
        height: auto !important;
    }
    .auth-hero-pane {
        height: auto !important;
        min-height: auto !important;
        padding: 40px 24px !important;
    }
    div[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="stColumn"]:last-child,
    div[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="column"]:last-child {
        height: auto !important;
        min-height: auto !important;
        padding: 40px 20px !important;
        overflow: visible !important;
    }
}
</style>
"""


@st.dialog("Khôi phục mật khẩu")
def _show_forgot_password_dialog():
    st.markdown("### 🔑 Đặt lại mật khẩu tài khoản")
    st.info(
        "Vì lý do bảo mật dữ liệu tài chính doanh nghiệp, việc cấp lại mật khẩu "
        "được thực hiện bởi Quản trị viên hệ thống."
    )
    st.markdown("""
    **Cách thức liên hệ hỗ trợ:**
    - 📧 **Email IT/Admin:** `admin@invoiceai.com`
    - 📞 **Hotline:** 1900 8888 (08:00 - 18:00 các ngày trong tuần)
    - 🏢 **Phòng Kế toán & Quản trị hệ thống InvoiceAI**
    
    *Vui lòng cung cấp Email đã đăng ký để được cấp mã kích hoạt lại tài khoản trong vòng 15 phút.*
    """)
    if st.button("Đã hiểu và Đóng", use_container_width=True, type="primary"):
        st.query_params.pop("action", None)
        st.rerun()


@st.dialog("Điều khoản sử dụng & Chính sách bảo mật")
def _show_terms_dialog():
    st.markdown("### 📋 Điều khoản sử dụng & Chính sách bảo mật InvoiceAI")
    st.markdown("""
    **1. Cam kết bảo mật dữ liệu (SSL 256-bit):**
    Mọi thông tin hóa đơn, chứng từ và dữ liệu doanh nghiệp tải lên hệ thống đều được 
    mã hóa đầu cuối và lưu trữ bảo mật trên hạ tầng chuyên dụng.

    **2. Quyền sở hữu dữ liệu:**
    Doanh nghiệp toàn quyền sở hữu các dữ liệu hóa đơn, báo cáo tài chính và lịch sử xử lý. 
    InvoiceAI cam kết không chia sẻ dữ liệu cho bên thứ ba.

    **3. Trách nhiệm người dùng:**
    Người dùng có trách nhiệm bảo mật thông tin đăng nhập và thông báo ngay cho Quản trị viên 
    nếu phát hiện truy cập trái phép.
    """)
    if st.button("Đóng", use_container_width=True, type="primary"):
        st.query_params.pop("action", None)
        st.rerun()


def _render_hero_column():
    _render_html("""
    <div class="auth-hero-pane">
        <!-- Logo góc trên bên trái -->
        <div class="hero-top-logo">
            <div class="hero-logo-box">
                <img src="data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='22' height='22' viewBox='0 0 24 24' fill='none' stroke='%23FFFFFF' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/%3E%3Cpolyline points='14 2 14 8 20 8'/%3E%3Cline x1='16' y1='13' x2='8' y2='13'/%3E%3Cline x1='16' y1='17' x2='8' y2='17'/%3E%3Cpolyline points='10 9 9 9 8 9'/%3E%3C/svg%3E" width="22" height="22" alt="InvoiceAI" />
            </div>
            <span class="hero-logo-title">InvoiceAI</span>
        </div>

        <!-- Khối nội dung chính giữa -->
        <div class="hero-middle-content">
            <div class="hero-badge-pill">
                <span class="hero-badge-dot"></span>
                <span>NỀN TẢNG HÓA ĐƠN THÔNG MINH</span>
            </div>
            
            <h1 class="hero-main-heading">
                Quản lý hóa đơn<br>
                nhẹ nhàng hơn.
            </h1>
            
            <p class="hero-sub-description">
                Tự động hóa quy trình nhập liệu, lưu trữ và theo dõi hóa đơn của doanh nghiệp trên một nền tảng bảo mật.
            </p>

            <div class="hero-feature-list">
                <div class="hero-feature-row">
                    <div class="hero-feature-squircle">
                        <img src="data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='%23A5B4FC' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='13 2 3 14 12 14 11 22 21 10 12 10 13 2'/%3E%3C/svg%3E" width="18" height="18" alt="AI" />
                    </div>
                    <span class="hero-feature-label">Trích xuất dữ liệu bằng AI trong vài giây</span>
                </div>

                <div class="hero-feature-row">
                    <div class="hero-feature-squircle">
                        <img src="data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='%23A5B4FC' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'/%3E%3Cpath d='m9 12 2 2 4-4'/%3E%3C/svg%3E" width="18" height="18" alt="Security" />
                    </div>
                    <span class="hero-feature-label">Dữ liệu được mã hóa và bảo mật</span>
                </div>

                <div class="hero-feature-row">
                    <div class="hero-feature-squircle">
                        <img src="data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='%23A5B4FC' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cline x1='18' y1='20' x2='18' y2='10'/%3E%3Cline x1='12' y1='20' x2='12' y2='4'/%3E%3Cline x1='6' y1='20' x2='6' y2='14'/%3E%3C/svg%3E" width="18" height="18" alt="Chart" />
                    </div>
                    <span class="hero-feature-label">Theo dõi chi phí trực quan, chính xác</span>
                </div>
            </div>
        </div>

        <!-- Bản quyền góc dưới bên trái -->
        <div class="hero-bottom-copyright">
            © 2026 InvoiceAI. Bảo lưu mọi quyền.
        </div>

        <!-- Hoa văn vòng tròn đồng tâm ở góc dưới bên phải -->
        <img src="data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='500' height='500' viewBox='0 0 500 500' fill='none'%3E%3Ccircle cx='450' cy='450' r='180' stroke='rgba(255,255,255,0.08)' stroke-width='2'/%3E%3Ccircle cx='450' cy='450' r='280' stroke='rgba(255,255,255,0.06)' stroke-width='2'/%3E%3Ccircle cx='450' cy='450' r='380' stroke='rgba(255,255,255,0.04)' stroke-width='2'/%3E%3Ccircle cx='450' cy='450' r='480' stroke='rgba(255,255,255,0.03)' stroke-width='2'/%3E%3C/svg%3E" class="hero-decorative-rings" alt="Rings" />
    </div>
    """)


def _render_login_form():
    _render_html("""
        <div class="form-heading-title">Chào mừng trở lại</div>
        <div class="form-heading-desc">Đăng nhập để tiếp tục quản lý hóa đơn của bạn.</div>
    """)

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Email", placeholder="name@company.com", key="login_username_field")
        password = st.text_input("Mật khẩu", type="password", placeholder="Tối thiểu 8 ký tự", key="login_password_field")

        col_remember, col_forgot = st.columns([1.1, 0.9])
        with col_remember:
            st.checkbox("Ghi nhớ đăng nhập", value=True, key="login_remember_checkbox")
        with col_forgot:
            _render_html(
                '<div style="text-align:right; padding-top:2px;">'
                '<a href="?action=forgot_password" target="_self" '
                'style="color:#4F46E5; text-decoration:none; font-size:12.5px; font-weight:500;">'
                'Quên mật khẩu?</a></div>'
            )

        submitted = st.form_submit_button("Đăng nhập →", type="primary", use_container_width=True)

    if submitted:
        u = username.strip()
        if not u or not password:
            st.error("Vui lòng nhập đầy đủ Email và Mật khẩu.")
            return
        user = authenticate_user(u, password)
        if user is None:
            log_activity("login_failed")
            st.error("Email hoặc mật khẩu không chính xác. Vui lòng kiểm tra lại.")
        else:
            log_activity("login_succeeded", user_id=int(user["id"]))
            st.session_state["authenticated_user"] = user
            st.session_state.pop("auth_mode", None)
            st.query_params.clear()
            st.rerun()

    _render_html("""
        <div class="auth-switch-box">
            Chưa có tài khoản? <a href="?mode=register" target="_self">Đăng ký miễn phí</a>
        </div>
    """)


def _render_register_form():
    _render_html("""
        <div class="form-heading-title">Tạo tài khoản mới</div>
        <div class="form-heading-desc">Bắt đầu quản lý hóa đơn chuyên nghiệp ngay hôm nay.</div>
    """)

    with st.form("register_form", clear_on_submit=False):
        full_name = st.text_input("Họ và tên", placeholder="Nguyễn Văn An", key="reg_fullname_field")
        email = st.text_input("Email", placeholder="name@company.com", key="reg_email_field")
        password = st.text_input("Mật khẩu", type="password", placeholder="Tối thiểu 8 ký tự", key="reg_password_field")
        confirm_password = st.text_input("Xác nhận mật khẩu", type="password", placeholder="Nhập lại mật khẩu", key="reg_confirm_password_field")

        agreed = st.checkbox(
            "Tôi đồng ý với [Điều khoản sử dụng](?action=terms) và [Chính sách bảo mật](?action=terms).",
            key="reg_terms_checkbox",
        )

        submitted = st.form_submit_button("Tạo tài khoản →", type="primary", use_container_width=True)

    if submitted:
        f_name = full_name.strip()
        e_mail = email.strip()
        if not f_name:
            st.error("Vui lòng nhập họ và tên của bạn.")
        elif not e_mail:
            st.error("Vui lòng nhập địa chỉ email.")
        elif not EMAIL_RE.fullmatch(e_mail):
            st.error("Vui lòng nhập định dạng email hợp lệ (ví dụ: name@company.com).")
        elif len(password) < 6:
            st.error("Mật khẩu phải có tối thiểu 6 ký tự (khuyến nghị từ 8 ký tự).")
        elif password != confirm_password:
            st.error("Mật khẩu xác nhận không khớp. Vui lòng nhập lại.")
        elif not agreed:
            st.error("Vui lòng tích chọn đồng ý với Điều khoản sử dụng và Chính sách bảo mật.")
        else:
            try:
                register_user(e_mail, password, full_name=f_name, email=e_mail)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state["auth_mode"] = "login"
                st.query_params["mode"] = "login"
                st.session_state["registration_notice"] = (
                    "Đăng ký tài khoản thành công! Vui lòng đăng nhập để bắt đầu."
                )
                st.rerun()

    _render_html("""
        <div class="auth-switch-box">
            Đã có tài khoản? <a href="?mode=login" target="_self">Đăng nhập ngay</a>
        </div>
    """)


def _render_auth_page():
    action = st.query_params.get("action")
    if action == "forgot_password":
        _show_forgot_password_dialog()
    elif action in {"terms", "privacy"}:
        _show_terms_dialog()

    query_mode = st.query_params.get("mode")
    if query_mode in {"login", "register"} and query_mode != st.session_state.get("auth_mode"):
        st.session_state["auth_mode"] = query_mode

    mode = st.session_state.get("auth_mode", "login")

    _render_html(AUTH_PAGE_CSS)

    col_hero, col_form = st.columns([1, 1], gap="small")

    with col_hero:
        _render_hero_column()

    with col_form:
        tab_labels = {"login": "Đăng nhập", "register": "Đăng ký"}
        selected = st.radio(
            "Chế độ xác thực",
            list(tab_labels.values()),
            index=0 if mode == "login" else 1,
            horizontal=True,
            label_visibility="collapsed",
            key=f"auth_tab_radio_{mode}",
        )
        new_mode = "login" if selected == tab_labels["login"] else "register"
        if new_mode != mode:
            st.session_state["auth_mode"] = new_mode
            st.query_params["mode"] = new_mode
            st.rerun()

        notice = st.session_state.pop("registration_notice", None)
        if notice and mode == "login":
            st.success(notice)

        if mode == "login":
            _render_login_form()
        else:
            _render_register_form()

        _render_html("""
            <div class="auth-security-ssl">
                <img src="data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='13' height='13' viewBox='0 0 24 24' fill='none' stroke='%2394A3B8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'/%3E%3C/svg%3E" width="13" height="13" alt="SSL" />
                <span>Kết nối an toàn với mã hóa SSL 256-bit</span>
            </div>
        """)


def require_auth() -> dict:
    global _DATABASE_INITIALIZED
    if not _DATABASE_INITIALIZED:
        initialize_database()
        log_activity("application_started")
        _DATABASE_INITIALIZED = True

    user = st.session_state.get("authenticated_user")
    if user:
        return user

    from app.components.sidebar_nav import render_guest_sidebar
    render_guest_sidebar()

    _render_auth_page()

    if not get_auth_configuration()["admin_configured"]:
        st.warning(
            "Quản trị viên chưa được cấu hình. Hãy đặt ADMIN_USERNAME và "
            "ADMIN_PASSWORD trong biến môi trường/Secrets trước khi sử dụng."
        )
    st.stop()


def render_account_menu() -> None:
    user = st.session_state.get("authenticated_user")
    if not user:
        return

    _, account_column = st.columns([10, 1])
    with account_column:
        with st.popover("👤", use_container_width=True):
            st.markdown(f"**{user.get('full_name') or user['username']}**")
            st.caption(user.get("email") or user["username"])
            st.divider()
            if st.button("↪ Đăng xuất", use_container_width=True):
                log_activity("logout", user_id=int(user["id"]))
                st.session_state.clear()
                st.rerun()


def current_user() -> dict:
    return st.session_state["authenticated_user"]


def is_admin() -> bool:
    return current_user().get("role") == "admin"


def require_admin() -> dict:
    user = require_auth()
    if user.get("role") != "admin":
        st.error("Bạn không có quyền truy cập chức năng quản trị.")
        st.stop()
    return user