import streamlit as st
from datetime import datetime
from src.storage.db_handler import get_confirmed_invoices, get_job_counts
NAV_ITEMS = [
    {"key": "upload", "label": "Tải lên hóa đơn", "icon": "⬆️", "path": "streamlit_app.py"},
    {"key": "history", "label": "Lịch sử hóa đơn", "icon": "🕐", "path": "pages/Lich_su_hoa_don.py"},
    {"key": "extract", "label": "Trích xuất dữ liệu", "icon": "📄", "path": "pages/Trich_xuat_du_lieu.py"},
    {"key": "accounting", "label": "Hạch toán kế toán", "icon": "🧮", "path": "pages/Hach_toan_ke_toan.py"},
    {"key": "report", "label": "Báo cáo tổng hợp", "icon": "📊", "path": "pages/Bao_cao_tong_hop.py"},
]


def render_sidebar(active_key: str):
    with st.sidebar:
        # Ẩn menu điều hướng mặc định của Streamlit (tên file thô, không đẹp)
        st.markdown(
            '<style>div[data-testid="stSidebarNav"] { display: none; }</style>',
            unsafe_allow_html=True,
        )

        # --- Logo ---
        st.markdown("""
            <div style="display:flex; align-items:center; gap:10px; padding: 4px 0 18px 0;">
                <div style="background:#4F46E5; width:36px; height:36px; border-radius:10px;
                            display:flex; align-items:center; justify-content:center; font-size:18px;">
                    📄
                </div>
                <div>
                    <div style="font-weight:800; font-size:17px; color:white;">InvoiceAI</div>
                    <div style="font-size:11px; color:#94A3B8;">Phiên bản 2.4</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        # --- Tiêu đề nhóm "ĐIỀU HƯỚNG" ---
        st.markdown("""
            <div style="font-size:11px; font-weight:700; letter-spacing:1.2px;
                        color:#64748B; margin: 4px 0 10px 4px; text-transform:uppercase;">
                Điều hướng
            </div>
        """, unsafe_allow_html=True)

        # --- Danh sách mục điều hướng ---
        for item in NAV_ITEMS:
            if item["key"] == active_key:
                # Mục đang chọn: không phải link, chỉ hiển thị tô đậm + chấm tròn
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

        # --- Thẻ số liệu tổng quan (card tối, 4 dòng) ---
        now = datetime.now()

        st.markdown(
            f'<div style="font-size:12px; color:#94A3B8; letter-spacing:1px; '
            f'text-transform:uppercase; margin-bottom:10px;">Tháng {now.month} / {now.year}</div>',
            unsafe_allow_html=True,
        )

        counts = get_job_counts()
        done = counts["success"]
        confirmed = len(get_confirmed_invoices())
        pending = counts["processing"]
        errors = counts["failed"] 
        st.markdown(f"""
        <div style="background:#1E293B; border-radius:14px; padding:6px 16px;">
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