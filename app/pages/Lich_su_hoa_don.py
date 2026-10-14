import streamlit as st
from pathlib import Path
import pandas as pd
import sys
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.db_handler import (
    cleanup_duplicate_invoices,
    delete_selected_history_jobs,
    get_duplicate_cleanup_preview,
    get_full_history,
)

st.set_page_config(page_title="Lịch sử hóa đơn", layout="wide")
css_path = Path(__file__).resolve().parents[1] / "style.css"
st.markdown(
    f"<style>{css_path.read_text(encoding='utf-8')}</style>",
    unsafe_allow_html=True,
)

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
    st.markdown(
        '<div class="status-badge status-done">🟢 Hệ thống hoạt động</div>',
        unsafe_allow_html=True,
    )

with col_period:
    now = datetime.now()
    st.markdown(
        f'<div class="status-badge" '
        f'style="background:#EEF2FF;color:#4F46E5;">'
        f'Kỳ: T{now.month}/{now.year}</div>',
        unsafe_allow_html=True,
    )


cleanup_notice = st.session_state.pop("duplicate_cleanup_notice", None)
if cleanup_notice:
    st.success(cleanup_notice)

history = get_full_history()
deletable_rows = [
    row for row in history
    if row["status"] in {"duplicate", "failed"}
]

if deletable_rows:
    st.subheader("Xóa hóa đơn trùng hoặc bị lỗi")

    row_by_label = {
        (
            f"#{row['job_id']} — {row['file_name'] or 'Không tên'} "
            f"— {'Trùng hóa đơn' if row['status'] == 'duplicate' else 'Lỗi'}"
        ): row
        for row in deletable_rows
    }

    selected_labels = st.multiselect(
        "Chọn các hóa đơn cần xóa",
        options=list(row_by_label),
        placeholder="Chọn hóa đơn trùng hoặc bị lỗi...",
    )

    confirm_delete = st.checkbox(
        "Tôi xác nhận xóa các dòng lịch sử đã chọn."
    )

    if st.button(
        "Xóa các hóa đơn đã chọn",
        type="primary",
        disabled=not selected_labels or not confirm_delete,
    ):
        selected_job_ids = [
            row_by_label[label]["job_id"]
            for label in selected_labels
        ]

        deleted = delete_selected_history_jobs(selected_job_ids)

        st.session_state["history_delete_notice"] = (
            f"Đã xóa {deleted['job_count']} dòng lịch sử và "
            f"{deleted['invoice_count']} bản ghi trích xuất trùng."
        )
        st.rerun()
else:
    st.info("Không có hóa đơn trùng hoặc bị lỗi để xóa.")

delete_notice = st.session_state.pop("history_delete_notice", None)
if delete_notice:
    st.success(delete_notice)
# --- Xóa hóa đơn trùng ---
duplicate_cleanup = get_duplicate_cleanup_preview()

if duplicate_cleanup["invoice_count"] or duplicate_cleanup["job_count"]:
    st.warning(
        "Đã tìm thấy "
        f"{duplicate_cleanup['invoice_count']} bản ghi dữ liệu hóa đơn trùng chính xác "
        f"và {duplicate_cleanup['job_count']} dòng lịch sử trùng/lỗi có thể xóa. "
        "Hệ thống sẽ giữ lại bản gốc được xử lý sớm nhất."
    )

    confirm_cleanup = st.checkbox(
        "Tôi xác nhận xóa các bản ghi trùng khỏi lịch sử và dữ liệu trích xuất."
    )

    if st.button(
        "Xóa hóa đơn trùng",
        type="primary",
        disabled=not confirm_cleanup,
    ):
        deleted = cleanup_duplicate_invoices()
        st.session_state["duplicate_cleanup_notice"] = (
            f"Đã xóa {deleted['job_count']} dòng lịch sử và "
            f"{deleted['invoice_count']} bản ghi trích xuất bị trùng."
        )
        st.rerun()


# --- 4 thẻ tổng quan ---
total = len(history)
success = sum(1 for row in history if row["status"] == "success")
duplicate = sum(1 for row in history if row["status"] == "duplicate")
pending = sum(1 for row in history if row["status"] == "processing")
total_value = sum(
    row["tong_thanh_toan"] or 0
    for row in history
    if row["status"] == "success"
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Tổng hóa đơn", total)
c2.metric(
    "Hoàn tất",
    success,
    help=f"{duplicate} lượt tải được nhận diện trùng và liên kết với dữ liệu đã có.",
)
c3.metric("Chờ / Đang xử lý", pending)
c4.metric(
    "Tổng giá trị",
    (
        f"{total_value / 1_000_000:,.1f}M đ"
        if total_value >= 1_000_000
        else f"{total_value:,.0f} đ"
    ),
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
        "Lọc",
        ["Tất cả", "Hoàn tất", "Trùng hóa đơn", "Đang xử lý", "Lỗi"],
        horizontal=True,
        label_visibility="collapsed",
    )

STATUS_MAP = {
    "Hoàn tất": "success",
    "Trùng hóa đơn": "duplicate",
    "Đang xử lý": "processing",
    "Lỗi": "failed",
}

filtered = history

if keyword:
    search_keyword = keyword.lower()
    filtered = [
        row
        for row in filtered
        if search_keyword in (row["ten_cong_ty_ban"] or "").lower()
        or search_keyword in (row["ma_so_thue_ban"] or "").lower()
        or search_keyword in (row["file_name"] or "").lower()
    ]

if status_filter != "Tất cả":
    filtered = [
        row
        for row in filtered
        if row["status"] == STATUS_MAP[status_filter]
    ]

st.caption(f"{len(filtered)} kết quả")

STATUS_BADGE = {
    "success": '<span class="status-badge status-done">Hoàn tất</span>',
    "duplicate": (
        '<span class="status-badge status-duplicate">Trùng hóa đơn</span>'
    ),
    "processing": (
        '<span class="status-badge status-pending">Đang xử lý</span>'
    ),
    "failed": '<span class="status-badge status-failed">Lỗi</span>',
}

# --- Bảng danh sách ---
if not filtered:
    st.info("Không có hóa đơn phù hợp.")
else:
    rows_html = ""

    for row in filtered:
        invoice_code = f"INV-{row['created_at'].year}-{row['job_id']:04d}"
        total_amount = (
            f"{row['tong_thanh_toan']:,.0f} đ"
            if row["tong_thanh_toan"] is not None
            else "—"
        )

        row_html = f"""
        <tr>
            <td><span style="color:#4F46E5; font-weight:700;">{invoice_code}</span></td>
            <td>📄 {row['file_name'] or '—'}</td>
            <td>{row['ten_cong_ty_ban'] or '—'}</td>
            <td>{row['ma_so_thue_ban'] or '—'}</td>
            <td>{row.get('so_hoa_don') or '—'}</td>
            <td>{row['ngay_lap'] or '—'}</td>
            <td style="font-weight:700;">{total_amount}</td>
            <td style="color:#94A3B8;">{row['created_at'].strftime('%d/%m/%Y %H:%M')}</td>
            <td>{STATUS_BADGE.get(row['status'], '—')}</td>
        </tr>
        """
        rows_html += _strip_html_indent(row_html)

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
    st.markdown(
        _strip_html_indent(table_html),
        unsafe_allow_html=True,
    )

    # --- Chi tiết lỗi cho các dòng thất bại ---
    failed_rows = [
        row for row in filtered
        if row["status"] == "failed"
    ]

    if failed_rows:
        st.write("")
        with st.expander(f"🔴 Xem chi tiết {len(failed_rows)} hóa đơn lỗi"):
            for row in failed_rows:
                st.markdown(
                    f"**{row['file_name']}** — "
                    f"{row['error_reason'] or 'Không xác định'}"
                )
                st.code(
                    row["error_message"] or "(không có thông tin)",
                    language="text",
                )
                st.divider()