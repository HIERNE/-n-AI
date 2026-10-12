import streamlit as st
from pathlib import Path
import sys
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.db_handler import get_full_history

st.set_page_config(page_title="Lịch sử hóa đơn", layout="wide")
css_path = Path(__file__).resolve().parents[1] / "style.css"
st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

from app.components.sidebar_nav import render_sidebar
render_sidebar("history")


def _strip_html_indent(html: str) -> str:
    """
    Xóa khoảng trắng đầu mỗi dòng trong chuỗi HTML.
    Cần thiết vì Markdown tự hiểu dòng thụt >= 4 dấu cách là code block,
    khiến bảng HTML bị hiển thị dưới dạng text thô thay vì render thành bảng.
    """
    return "\n".join(line.strip() for line in html.split("\n"))


# --- Header ---
col_title, col_status, col_period = st.columns([3, 1, 1])
with col_title:
    st.title("Lịch sử hóa đơn")
    st.caption("Toàn bộ hóa đơn đã xử lý trong hệ thống")
with col_status:
    st.markdown('<div class="status-badge status-done">🟢 Hệ thống hoạt động</div>', unsafe_allow_html=True)
with col_period:
    now = datetime.now()
    st.markdown(
        f'<div class="status-badge" style="background:#EEF2FF;color:#4F46E5;">Kỳ: T{now.month}/{now.year}</div>',
        unsafe_allow_html=True,
    )

history = get_full_history()

# --- 4 thẻ tổng quan ---
total = len(history)
success = sum(1 for r in history if r["status"] == "success")
pending = sum(1 for r in history if r["status"] == "processing")
total_value = sum(r["tong_thanh_toan"] or 0 for r in history if r["status"] == "success")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Tổng hóa đơn", total)
c2.metric("Hoàn tất", success)
c3.metric("Chờ / Đang xử lý", pending)
c4.metric(
    "Tổng giá trị",
    f"{total_value/1_000_000:,.1f}M đ" if total_value >= 1_000_000 else f"{total_value:,.0f} đ",
)

st.write("")

# --- Tìm kiếm + lọc trạng thái ---
col_search, col_filter = st.columns([3, 2])
with col_search:
    keyword = st.text_input(
        "🔍 Tìm theo tên, MST, số hóa đơn...",
        label_visibility="collapsed",
        placeholder="🔍 Tìm theo tên, MST, số hóa đơn...",
    )
with col_filter:
    status_filter = st.radio(
        "Lọc", ["Tất cả", "Hoàn tất", "Đang xử lý", "Lỗi"],
        horizontal=True, label_visibility="collapsed",
    )

STATUS_MAP = {"Hoàn tất": "success", "Đang xử lý": "processing", "Lỗi": "failed"}

filtered = history
if keyword:
    kw = keyword.lower()
    filtered = [
        r for r in filtered
        if kw in (r["ten_cong_ty_ban"] or "").lower()
        or kw in (r["ma_so_thue_ban"] or "").lower()
        or kw in (r["file_name"] or "").lower()
    ]
if status_filter != "Tất cả":
    filtered = [r for r in filtered if r["status"] == STATUS_MAP[status_filter]]

st.caption(f"{len(filtered)} kết quả")

STATUS_BADGE = {
    "success": '<span class="status-badge status-done">Hoàn tất</span>',
    "processing": '<span class="status-badge status-pending">Đang xử lý</span>',
    "failed": '<span class="status-badge status-failed">Lỗi</span>',
}

# --- Bảng danh sách ---
if not filtered:
    st.info("Không có hóa đơn phù hợp.")
else:
    rows_html = ""
    for r in filtered:
        invoice_code = f"INV-{r['created_at'].year}-{r['job_id']:04d}"
        tong_tien = f"{r['tong_thanh_toan']:,.0f} đ" if r["tong_thanh_toan"] is not None else "—"

        row = f"""
        <tr>
            <td><span style="color:#4F46E5; font-weight:700;">{invoice_code}</span></td>
            <td>📄 {r['file_name'] or '—'}</td>
            <td>{r['ten_cong_ty_ban'] or '—'}</td>
            <td>{r['ma_so_thue_ban'] or '—'}</td>
            <td>{r.get('so_hoa_don') or '—'}</td>
            <td>{r['ngay_lap'] or '—'}</td>
            <td style="font-weight:700;">{tong_tien}</td>
            <td style="color:#94A3B8;">{r['created_at'].strftime('%d/%m/%Y %H:%M')}</td>
            <td>{STATUS_BADGE.get(r['status'], '—')}</td>
        </tr>
        """
        rows_html += _strip_html_indent(row)

    table_html = f"""
    <div style="background:white; border-radius:14px; overflow:hidden; border:1px solid #E2E8F0;
                box-shadow:0 1px 3px rgba(0,0,0,0.04);">
        <table style="width:100%; border-collapse:collapse; font-size:14px;">
            <thead>
                <tr style="background:#F8FAFC; text-transform:uppercase; font-size:12px; color:#64748B;">
                    <th style="text-align:left; padding:12px 16px;">Mã hóa đơn</th>
                    <th style="text-align:left; padding:12px 16px;">Tên tệp</th>
                    <th style="text-align:left; padding:12px 16px;">Nhà cung cấp</th>
                    <th style="text-align:left; padding:12px 16px;">MST</th>
                    <th style="text-align:left; padding:12px 16px;">Số hóa đơn</th>
                    <th style="text-align:left; padding:12px 16px;">Ngày HĐ</th>
                    <th style="text-align:left; padding:12px 16px;">Tổng tiền</th>
                    <th style="text-align:left; padding:12px 16px;">Ngày tải lên</th>
                    <th style="text-align:left; padding:12px 16px;">Trạng thái</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>
    """
    st.markdown(_strip_html_indent(table_html), unsafe_allow_html=True)

    # --- Chi tiết lỗi cho các dòng thất bại ---
    failed_rows = [r for r in filtered if r["status"] == "failed"]
    if failed_rows:
        st.write("")
        with st.expander(f"🔴 Xem chi tiết {len(failed_rows)} hóa đơn lỗi"):
            for r in failed_rows:
                st.markdown(f"**{r['file_name']}** — {r['error_reason'] or 'Không xác định'}")
                st.code(r["error_message"] or "(không có thông tin)", language="text")
                st.divider()