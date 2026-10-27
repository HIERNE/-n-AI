import streamlit as st
from datetime import datetime

from src.storage.db_handler import get_all_invoices, get_confirmed_invoices, get_job_counts
from app.components.auth import current_user


NAV_ITEMS = [
    {"key": "upload", "label": "Tải lên hóa đơn", "icon": "⬆️", "path": "streamlit_app.py"},
    {"key": "history", "label": "Lịch sử hóa đơn", "icon": "🕐", "path": "pages/Lich_su_hoa_don.py"},
    {"key": "extract", "label": "Trích xuất dữ liệu", "icon": "📄", "path": "pages/Trich_xuat_du_lieu.py"},
    {"key": "accounting", "label": "Hạch toán kế toán", "icon": "🧮", "path": "pages/Hach_toan_ke_toan.py"},
    {"key": "report", "label": "Báo cáo tổng hợp", "icon": "📊", "path": "pages/Bao_cao_tong_hop.py"},
]


def _render_brand() -> None:
    st.markdown("""
        <div style="display:flex; align-items:center; gap:10px; padding:4px 0 18px;">
            <div style="background:#4F46E5; width:36px; height:36px; border-radius:10px;
                        display:flex; align-items:center; justify-content:center; font-size:18px;">
                📄
            </div>
            <div>
                <div style="font-weight:800; font-size:17px; color:white;">InvoiceAI</div>
                <div style="font-size:11px; color:#94A3B8;">Phiên bản 2.4</div>
            </div>
        </div>
        <div style="font-size:11px; font-weight:700; letter-spacing:1.2px;
                    color:#64748B; margin:4px 0 10px 4px; text-transform:uppercase;">
            Điều hướng
        </div>
    """, unsafe_allow_html=True)


def _render_summary(total: int, done: int, confirmed: int, pending: int, errors: int) -> None:
    now = datetime.now()
    st.markdown(
        f'<div style="font-size:12px; color:#94A3B8; letter-spacing:1px; '
        f'text-transform:uppercase; margin-bottom:10px;">Tháng {now.month} / {now.year}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f"""
    <div style="background:#1E293B; border-radius:14px; padding:6px 16px;">
        <div style="display:flex; justify-content:space-between; padding:10px 0; border-bottom:1px solid #334155;">
            <span style="color:#94A3B8; font-size:13px;">Tổng hóa đơn</span>
            <span style="color:white; font-weight:700; font-size:14px;">{total}</span>
        </div>
        <div style="display:flex; justify-content:space-between; padding:10px 0; border-bottom:1px solid #334155;">
            <span style="color:#94A3B8; font-size:13px;">Đã xử lý</span>
            <span style="color:white; font-weight:700; font-size:14px;">{done}</span>
        </div>
        <div style="display:flex; justify-content:space-between; padding:10px 0; border-bottom:1px solid #334155;">
            <span style="color:#94A3B8; font-size:13px;">Hạch toán</span>
            <span style="color:#4ADE80; font-weight:700; font-size:14px;">{confirmed}</span>
        </div>
        <div style="display:flex; justify-content:space-between; padding:10px 0; border-bottom:1px solid #334155;">
            <span style="color:#94A3B8; font-size:13px;">Chờ xử lý</span>
            <span style="color:#FBBF24; font-weight:700; font-size:14px;">{pending}</span>
        </div>
        <div style="display:flex; justify-content:space-between; padding:10px 0;">
            <span style="color:#94A3B8; font-size:13px;">Lỗi</span>
            <span style="color:#F87171; font-weight:700; font-size:14px;">{errors}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_sidebar(active_key: str):
    user = current_user()
    admin = user.get("role") == "admin"
    with st.sidebar:
        st.markdown(
            '<style>div[data-testid="stSidebarNav"] { display: none; }</style>',
            unsafe_allow_html=True,
        )
        _render_brand()

        for item in NAV_ITEMS:
            if not admin and item["key"] == "accounting":
                continue
            if item["key"] == active_key:
                st.markdown(f"""
                    <div style="display:flex; align-items:center; gap:10px;
                                background:#4F46E5; border-radius:10px; padding:10px 14px;
                                margin-bottom:4px; position:relative;">
                        <span style="font-size:15px;">{item['icon']}</span>
                        <span style="color:white; font-weight:700; font-size:14px;">{item['label']}</span>
                        <span style="position:absolute; right:14px; width:6px; height:6px;
                                     border-radius:50%; background:#C7D2FE;"></span>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.page_link(item["path"], label=item["label"], icon=item["icon"])

        st.divider()
        user_id = int(user["id"])
        counts = get_job_counts(user_id=user_id, is_admin=admin)
        _render_summary(
            len(get_all_invoices(user_id=user_id, is_admin=admin)),
            counts["success"],
            len(get_confirmed_invoices(user_id=user_id, is_admin=admin)),
            counts["processing"],
            counts["failed"],
        )


def render_guest_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            """
            <style>
            section[data-testid="stSidebar"],
            [data-testid="stSidebarCollapsedControl"] {
                display: none !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
