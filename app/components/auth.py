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
from app.components.brand import logo_data_uri

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
_DATABASE_INITIALIZED = False


def _render_html(html_str: str) -> None:
    """Render HTML chuẩn xác, loại bỏ hoàn toàn khoảng trắng thụt lề ở từng dòng."""
    cleaned = "\n".join(line.strip() for line in html_str.splitlines() if line.strip())
    st.markdown(cleaned, unsafe_allow_html=True)


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
    _render_html(f"""
    <div class="auth-hero-pane">
        <!-- Logo góc trên bên trái -->
        <div class="hero-top-logo">
            <div class="hero-logo-box">
                <img src="{logo_data_uri()}" alt="InvoiceAI" />
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
        st.checkbox("Ghi nhớ đăng nhập", value=True, key="login_remember_checkbox")
        _render_html(
            '<div style="text-align:right; padding-top:2px;">'
            '<a href="?action=forgot_password" target="_self" '
            'style="color:#4F46E5; text-decoration:none; font-size:12.5px; font-weight:500;">'
            'Quên mật khẩu?</a></div>'
        )
        submitted = st.form_submit_button(
            "Đăng nhập →", type="primary", use_container_width=True
        )

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

    auth_css_path = Path(__file__).resolve().parents[1] / "auth.css"
    _render_html(f"<style>{auth_css_path.read_text(encoding='utf-8')}</style>")

    col_hero, col_form = st.columns([1, 1], gap="small")

    with col_hero:
        _render_hero_column()

    with col_form:
        side_space_left, form_column, side_space_right = st.columns(
            [1, 1.8, 1], gap="small"
        )
        with form_column:
            with st.container(key="auth-form-wrapper"):
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


def require_admin() -> dict:
    user = require_auth()
    if user.get("role") != "admin":
        st.error("Bạn không có quyền truy cập trang này. Chỉ quản trị viên mới được phép.")
        st.stop()
    return user


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
