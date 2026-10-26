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

_BW = 'div[data-testid="stVerticalBlockBorderWrapper"]'
_P = (
    'html body div[data-testid="stMain"] :is('
    f'{_BW}:has(form[data-testid="stForm"]), {_BW}:has(.auth-card-marker), .st-key-auth_card)'
)

def _minify(css: str) -> str:
    """Streamlit cắt khối <style> tại dòng trống/thụt lề -> gộp thành các dòng liền nhau."""
    return "\n".join(line.strip() for line in css.splitlines() if line.strip())


AUTH_CSS = _minify("""
<style>
.auth-card-marker { display:none; }
.auth-brand { text-align:center; padding:6px 0 2px; }
.auth-icon { display:inline-flex; align-items:center; justify-content:center; width:54px; height:54px; border-radius:16px; font-size:24px; background:linear-gradient(135deg,#06B6D4,#22D3EE); color:#06202B; box-shadow:0 10px 26px rgba(6,182,212,.32); }
.auth-title { color:#F8FAFC !important; font-size:22px; font-weight:800; line-height:1.3; margin-top:14px; letter-spacing:-.2px; }
.auth-subtitle { margin-top:4px; color:#8A9BB3 !important; font-size:13px; }
.auth-forgot { text-align:right; color:#8A9BB3 !important; font-size:12px; margin:-6px 0 12px; }
.auth-forgot b { color:#22D3EE; font-weight:600; }
.auth-security { color:#5B6B82 !important; font-size:11px; text-align:center; margin-top:18px; }
.auth-security span { color:#2DD4BF !important; }
@@P@@, @@P@@ > div { background:#0B1626 !important; border-color:#1E3348 !important; }
@@P@@ { border:1px solid #1E3348 !important; border-radius:22px !important; box-shadow:0 30px 70px rgba(2,8,23,.35) !important; width:min(100%,460px); margin:0 auto; }
@@P@@ > div { padding:32px 30px 24px !important; border:0 !important; box-shadow:none !important; border-radius:22px !important; }
@@P@@ form[data-testid="stForm"] { border:0 !important; padding:0 !important; background:transparent !important; }
@@P@@ div[data-testid="stRadio"] > div[role="radiogroup"] { display:grid !important; grid-template-columns:1fr 1fr; gap:4px; background:#0F1C2E; border:1px solid #1E3348; border-radius:13px; padding:4px; margin:18px 0 8px; width:100%; }
@@P@@ div[data-testid="stRadio"] label { justify-content:center; margin:0 !important; padding:10px 0; border-radius:10px; cursor:pointer; background:transparent !important; }
@@P@@ div[data-testid="stRadio"] label > div:first-child { display:none !important; }
@@P@@ div[data-testid="stRadio"] label p { color:#8A9BB3 !important; font-weight:600; font-size:14px; }
@@P@@ div[data-testid="stRadio"] label:has(input:checked) { background:#12394A !important; box-shadow:inset 0 0 0 1px #16708A; }
@@P@@ div[data-testid="stRadio"] label:has(input:checked) p { color:#22D3EE !important; }
@@P@@ form[data-testid="stForm"] label p { color:#A7B6CC !important; font-size:13px !important; font-weight:600 !important; }
@@P@@ div[data-baseweb="input"], @@P@@ div[data-baseweb="base-input"] { background:#111C2D !important; border-color:#243449 !important; border-radius:12px !important; }
@@P@@ div[data-baseweb="input"] { border-width:1px !important; }
@@P@@ div[data-baseweb="input"]:focus-within { border-color:#06B6D4 !important; box-shadow:0 0 0 3px rgba(6,182,212,.18) !important; }
@@P@@ input { background:transparent !important; color:#F1F5F9 !important; min-height:46px; font-size:15px !important; -webkit-text-fill-color:#F1F5F9 !important; }
@@P@@ input::placeholder { color:#53647C !important; -webkit-text-fill-color:#53647C !important; }
@@P@@ div[data-baseweb="input"] button { background:transparent !important; border:0 !important; box-shadow:none !important; }
@@P@@ div[data-baseweb="input"] svg { fill:#8A9BB3 !important; color:#8A9BB3 !important; }
@@P@@ div[data-testid="stButton"] button { background:transparent !important; border:0 !important; box-shadow:none !important; color:#8A9BB3 !important; min-height:36px; }
@@P@@ div[data-testid="stButton"] button p { color:#8A9BB3 !important; font-weight:500 !important; }
@@P@@ div[data-testid="stButton"] button:hover p { color:#22D3EE !important; }
@@P@@ form[data-testid="stForm"] button[kind] { min-height:48px; border-radius:12px !important; border:0 !important; background:linear-gradient(100deg,#06B6D4,#22D3EE) !important; box-shadow:0 10px 24px rgba(6,182,212,.28) !important; }
@@P@@ form[data-testid="stForm"] button[kind]:hover { filter:brightness(1.08); }
@@P@@ form[data-testid="stForm"] button[kind] p { color:#06202B !important; font-weight:700 !important; font-size:15px !important; }
@@P@@ div[data-testid="stAlert"] { background:#111C2D !important; border:1px solid #243449 !important; border-radius:12px !important; }
@@P@@ div[data-testid="stAlert"] p { color:#E2E8F0 !important; font-size:13px; }
@media (max-width: 700px) { @@P@@ > div { padding:24px 18px 18px !important; } }
</style>
""").replace("@@P@@", _P)


def _render_guest_styles() -> None:
    css_path = Path(__file__).resolve().parents[1] / "style.css"
    try:
        st.markdown(
            f"<style>{_minify(css_path.read_text(encoding='utf-8'))}</style>",
            unsafe_allow_html=True,
        )
    except OSError:
        pass
    st.markdown(AUTH_CSS, unsafe_allow_html=True)


def _render_home() -> None:
    title_column, status_column, period_column = st.columns([3, 1, 1])
    with title_column:
        st.title("Tải lên hóa đơn")
        st.caption("Nhập hóa đơn từ PDF, ảnh")
    with status_column:
        st.markdown(
            '<div class="status-badge status-done">🟢 Hệ thống hoạt động</div>',
            unsafe_allow_html=True,
        )
    with period_column:
        now = datetime.now()
        st.markdown(
            '<div class="status-badge" style="background:#EEF2FF;color:#4F46E5;">'
            f"Kỳ: T{now.month}/{now.year}</div>",
            unsafe_allow_html=True,
        )

    st.info("Đăng nhập hoặc đăng ký để tải lên và quản lý hóa đơn của bạn.")
    metrics = st.columns(5)
    for column, label in zip(
        metrics, ["Tổng hóa đơn", "Đã xử lý", "Hạch toán", "Đang xử lý", "Lỗi"]
    ):
        column.metric(label, 0)
    st.markdown("##### 📋 Hóa đơn gần đây")
    st.info("Đăng nhập để xem hóa đơn trong tài khoản của bạn.")


def _login_form() -> None:
    with st.form("login_form"):
        username = st.text_input("Email / tên đăng nhập", placeholder="ten@gmail.com")
        password = st.text_input("Mật khẩu", type="password", placeholder="Nhập mật khẩu")
        st.markdown(
            '<div class="auth-forgot">Quên mật khẩu? <b>Liên hệ quản trị viên</b></div>',
            unsafe_allow_html=True,
        )
        submitted = st.form_submit_button(
            "Đăng nhập", type="primary", use_container_width=True
        )
    if submitted:
        if not username.strip() or not password:
            st.error("Vui lòng nhập đầy đủ tài khoản và mật khẩu.")
            return
        user = authenticate_user(username, password)
        if user is None:
            log_activity("login_failed")
            st.error("Email/tên đăng nhập hoặc mật khẩu không đúng.")
        else:
            log_activity("login_succeeded", user_id=int(user["id"]))
            st.session_state["authenticated_user"] = user
            st.session_state.pop("auth_mode", None)
            st.rerun()


def _register_form() -> None:
    with st.form("registration_form"):
        full_name = st.text_input("Họ và tên", placeholder="Nguyễn Văn A")
        email = st.text_input("Gmail", placeholder="ten@gmail.com")
        password = st.text_input(
            "Mật khẩu", type="password", placeholder="Tối thiểu 6 ký tự"
        )
        submitted = st.form_submit_button(
            "Tạo tài khoản", type="primary", use_container_width=True
        )
    if not submitted:
        return

    email = email.strip()
    if not full_name.strip():
        st.error("Vui lòng nhập họ và tên.")
    elif not EMAIL_RE.fullmatch(email):
        st.error("Vui lòng nhập email Gmail hợp lệ (ví dụ: ten@gmail.com).")
    elif len(password) < 6:
        st.error("Mật khẩu phải có tối thiểu 6 ký tự.")
    else:
        try:
            register_user(email, password, full_name=full_name.strip(), email=email)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["auth_mode"] = "login"
            st.session_state["registration_notice"] = (
                "Đăng ký thành công. Vui lòng đăng nhập để tiếp tục."
            )
            st.rerun()


def _render_auth_form(mode: str) -> None:
    _, center, _ = st.columns([1, 2, 1])
    with center:
        try:
            card = st.container(border=True, key="auth_card")
        except TypeError:  # Streamlit cũ chưa hỗ trợ key
            card = st.container(border=True)
        with card:
            st.markdown('<div class="auth-card-marker"></div>', unsafe_allow_html=True)
            title = "Chào mừng trở lại" if mode == "login" else "Tạo tài khoản InvoiceAI"
            subtitle = (
                "Đăng nhập để tiếp tục quản lý hóa đơn"
                if mode == "login" else "Bắt đầu xử lý hóa đơn tự động trong vài giây"
            )
            st.markdown(
                f'<div class="auth-brand"><div class="auth-icon">▣</div>'
                f'<div class="auth-title">{title}</div>'
                f'<div class="auth-subtitle">{subtitle}</div></div>',
                unsafe_allow_html=True,
            )

            labels = {"login": "Đăng nhập", "register": "Đăng ký"}
            choice = st.radio(
                "Chế độ", list(labels.values()),
                index=0 if mode == "login" else 1,
                key=f"auth_radio_{mode}", horizontal=True,
                label_visibility="collapsed",
            )
            new_mode = "login" if choice == labels["login"] else "register"
            if new_mode != mode:
                st.session_state["auth_mode"] = new_mode
                st.rerun()

            notice = st.session_state.pop("registration_notice", None)
            if notice and mode == "login":
                st.success(notice)

            if mode == "login":
                _login_form()
            else:
                _register_form()

            st.markdown(
                '<div class="auth-security"><span>●</span> Mật khẩu được mã hóa · '
                "Dữ liệu riêng tư theo tài khoản</div>",
                unsafe_allow_html=True,
            )
            if st.button("← Quay lại trang chủ", key="close_auth", use_container_width=True):
                st.session_state.pop("auth_mode", None)
                st.rerun()


def require_auth() -> dict:
    global _DATABASE_INITIALIZED
    if not _DATABASE_INITIALIZED:
        initialize_database()
        log_activity("application_started")
        _DATABASE_INITIALIZED = True

    user = st.session_state.get("authenticated_user")
    if user:
        return user

    _render_guest_styles()
    from app.components.sidebar_nav import render_guest_sidebar

    render_guest_sidebar()
    mode = st.session_state.get("auth_mode")
    header_left, login_column, register_column = st.columns([5, 2.5, 2.5])
    with header_left:
        st.markdown("### 📄 InvoiceAI")
    with login_column:
        if st.button("Đăng nhập", key="top_login", type="primary", use_container_width=True):
            st.session_state["auth_mode"] = "login"
            st.rerun()
    with register_column:
        if st.button("Đăng ký", key="top_register", use_container_width=True):
            st.session_state["auth_mode"] = "register"
            st.rerun()

    if mode in {"login", "register"}:
        _render_auth_form(mode)
    else:
        _render_home()

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