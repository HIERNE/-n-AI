import streamlit as st
from datetime import datetime

from src.storage.db_handler import get_all_invoices, get_confirmed_invoices, get_job_counts
from app.components.auth import current_user
from app.components.brand import logo_data_uri

NAV_ITEMS = [
    {"key": "upload", "label": "Tải lên hóa đơn", "icon": "📤", "path": "streamlit_app.py"},
    {"key": "history", "label": "Lịch sử hóa đơn", "icon": "🗂️", "path": "pages/Lich_su_hoa_don.py"},
    {"key": "extract", "label": "Trích xuất dữ liệu", "icon": "🔬", "path": "pages/Trich_xuat_du_lieu.py"},
    {"key": "accounting", "label": "Hạch toán kế toán", "icon": "🧮", "path": "pages/Hach_toan_ke_toan.py"},
    {"key": "report", "label": "Báo cáo tổng hợp", "icon": "📈", "path": "pages/Bao_cao_tong_hop.py"},
]


def _render_brand() -> None:
    st.markdown(f"""
        <div style="display:flex; align-items:center; gap:10px; padding:2px 0 10px; border-bottom:1px solid #334155; margin-bottom:10px;">
            <img src="{logo_data_uri()}" alt="InvoiceAI" style="width:40px; height:40px; object-fit:contain; flex-shrink:0;" />
            <div>
                <div style="font-weight:800; font-size:15px; color:white; letter-spacing: -0.3px;">InvoiceAI <span style="font-size:9.5px; background:#312E81; color:#A5B4FC; padding:1px 5px; border-radius:99px; font-weight:600; vertical-align:middle;">PRO</span></div>
                <div style="font-size:10.5px; color:#94A3B8; margin-top:1px;">Hệ thống AI Kiểm toán &amp; Kế toán</div>
            </div>
        </div>
        <div style="font-size:10px; font-weight:700; letter-spacing:1px;
                    color:#64748B; margin:4px 0 6px 4px; text-transform:uppercase;">
            Menu điều hướng
        </div>
    """, unsafe_allow_html=True)


def _render_summary(total: int, done: int, confirmed: int, pending: int, errors: int) -> None:
    now = datetime.now()
    st.markdown(f"""
        <div style="display:flex; justify-content:space-between; align-items:center; margin:12px 0 6px 4px;">
            <span style="font-size:10px; font-weight:700; letter-spacing:1px; color:#64748B; text-transform:uppercase;">Thống kê kỳ</span>
            <span style="font-size:10.5px; color:#A5B4FC; background:#312E81; padding:1px 6px; border-radius:99px; font-weight:600;">T{now.month}/{now.year}</span>
        </div>
        <div style="background:linear-gradient(145deg, #1E293B 0%, #0F172A 100%); border:1px solid #334155; border-radius:12px; padding:8px 12px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.05);">
            <div style="display:flex; justify-content:space-between; align-items:center; padding:5px 0; border-bottom:1px solid rgba(51, 65, 85, 0.5);">
                <span style="color:#94A3B8; font-size:12px; display:flex; align-items:center; gap:6px;">📁 Tổng hóa đơn</span>
                <span style="color:white; font-weight:700; font-size:12.5px; background:#334155; padding:1px 6px; border-radius:5px;">{total}</span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; padding:5px 0; border-bottom:1px solid rgba(51, 65, 85, 0.5);">
                <span style="color:#94A3B8; font-size:12px; display:flex; align-items:center; gap:6px;">⚡ Đã xử lý xong</span>
                <span style="color:#38BDF8; font-weight:700; font-size:12.5px;">{done}</span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; padding:5px 0; border-bottom:1px solid rgba(51, 65, 85, 0.5);">
                <span style="color:#94A3B8; font-size:12px; display:flex; align-items:center; gap:6px;">🧮 Đã hạch toán</span>
                <span style="color:#4ADE80; font-weight:700; font-size:12.5px;">{confirmed}</span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; padding:5px 0; border-bottom:1px solid rgba(51, 65, 85, 0.5);">
                <span style="color:#94A3B8; font-size:12px; display:flex; align-items:center; gap:6px;">⏳ Đang chờ duyệt</span>
                <span style="color:#FBBF24; font-weight:700; font-size:12.5px;">{pending}</span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; padding:5px 0 2px 0;">
                <span style="color:#94A3B8; font-size:12px; display:flex; align-items:center; gap:6px;">⚠️ Cảnh báo lỗi</span>
                <span style="color:#F87171; font-weight:700; font-size:12.5px;">{errors}</span>
            </div>
        </div>
    """, unsafe_allow_html=True)


def _render_user_profile(user: dict) -> None:
    username = user.get("username", "User")
    role = user.get("role", "member")
    role_badge = "🛡️ Quản trị viên" if role == "admin" else "👤 Thành viên"
    role_color = "#A5B4FC" if role == "admin" else "#94A3B8"
    
    st.markdown(f"""
        <div style="background:#0F172A; border:1px solid #334155; border-radius:10px; padding:8px 10px; margin-top:10px; display:flex; align-items:center; gap:8px;">
            <div style="width:28px; height:28px; border-radius:50%; background:#4F46E5; color:white; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:12px;">
                {username[:1].upper()}
            </div>
            <div style="overflow:hidden; flex:1;">
                <div style="font-weight:700; color:white; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{username}</div>
                <div style="font-size:10.5px; color:{role_color};">{role_badge}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)


def render_sidebar(active_key: str):
    user = current_user()
    admin = user.get("role") == "admin"
    with st.sidebar:
        st.markdown(
            """
            <style>
                div[data-testid="stSidebarNav"] { display: none; }
                section[data-testid="stSidebar"] {
                    background-color: #0B0F19;
                    border-right: 1px solid #1E293B;
                }
                /* Thu hẹp padding của page_link ở Sidebar */
                section[data-testid="stSidebar"] [data-testid="stPageLink"] {
                    background-color: transparent;
                    border-radius: 8px;
                    padding: 4px 10px;
                    margin-bottom: 3px;
                    transition: all 0.2s ease;
                    border: 1px solid transparent;
                }
                section[data-testid="stSidebar"] [data-testid="stPageLink"]:hover {
                    background-color: #1E293B;
                    border-color: #334155;
                }
                section[data-testid="stSidebar"] [data-testid="stPageLink"] span {
                    color: #94A3B8;
                    font-weight: 500;
                    font-size: 13px;
                }
                section[data-testid="stSidebar"] [data-testid="stPageLink"]:hover span {
                    color: #FFFFFF;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )
        
        # 1. Logo & Thương hiệu
        _render_brand()

        # 2. Menu điều hướng
        for item in NAV_ITEMS:
            if not admin and item["key"] == "accounting":
                continue
            
            if item["key"] == active_key:
                st.markdown(f"""
                    <div style="display:flex; align-items:center; gap:10px;
                                background: linear-gradient(135deg, #4F46E5 0%, #6366F1 100%); 
                                border-radius:8px; padding:8px 12px;
                                margin-bottom:3px; position:relative;
                                box-shadow: 0 4px 10px rgba(79, 70, 229, 0.3);">
                        <span style="font-size:15px;">{item['icon']}</span>
                        <span style="color:white; font-weight:700; font-size:13px;">{item['label']}</span>
                        <span style="position:absolute; right:10px; width:5px; height:5px;
                                     border-radius:50%; background:#FFFFFF; box-shadow: 0 0 6px #FFF;"></span>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.page_link(item["path"], label=item["label"], icon=item["icon"])

        st.divider()
        
        # 3. Thẻ thống kê
        user_id = int(user["id"])
        counts = get_job_counts(user_id=user_id, is_admin=admin)
        _render_summary(
            len(get_all_invoices(user_id=user_id, is_admin=admin)),
            counts["success"],
            len(get_confirmed_invoices(user_id=user_id, is_admin=admin)),
            counts["processing"],
            counts["failed"],
        )

        # 4. Thẻ thông tin tài khoản
        _render_user_profile(user)


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