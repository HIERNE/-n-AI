from pathlib import Path

import streamlit as st
st.set_page_config(
    page_title="Lịch sử hóa đơn",
    page_icon=str(Path(__file__).resolve().parents[1] / "assets" / "invoiceai_logo.png"),
    layout="wide",
)

import pandas as pd
import sys
import html
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
from app.components.auth import render_account_menu, require_auth
from app.components.sidebar_nav import render_sidebar

user = require_auth()
USER_ID = int(user["id"])
IS_ADMIN = user["role"] == "admin"

# Tải file CSS tập trung
css_path = Path(__file__).resolve().parents[1] / "style.css"
st.markdown(
    f"<style>{css_path.read_text(encoding='utf-8')}</style>",
    unsafe_allow_html=True,
)

render_sidebar("history")
render_account_menu()


def _strip(s: str) -> str:
    """Xóa thụt lề đầu dòng để tránh Markdown nhận diện nhầm thành code block."""
    return "\n".join(line.strip() for line in s.split("\n"))


# ─── 1. TẢI DỮ LIỆU & THỐNG KÊ ────────────────────────────────────────────────
cleanup_notice = st.session_state.pop("duplicate_cleanup_notice", None)
delete_notice = st.session_state.pop("history_delete_notice", None)

history = get_full_history(user_id=USER_ID, is_admin=IS_ADMIN)
deletable_rows = [row for row in history if row["status"] in {"duplicate", "failed"}]

total = len(history)
success_count = sum(1 for r in history if r["status"] == "success")
duplicate_count = sum(1 for r in history if r["status"] == "duplicate")
pending_count = sum(1 for r in history if r["status"] == "processing")
failed_count = sum(1 for r in history if r["status"] == "failed")
total_value = sum(
    r["tong_thanh_toan"] or 0
    for r in history
    if r["status"] == "success"
)
success_rate = round(success_count / total * 100) if total else 0


# ─── 2. HEADER TRANG CÔNG NGHỆ CAO ─────────────────────────────────────────────
now = datetime.now()
page_desc = "Toàn bộ hóa đơn đã xử lý trong hệ thống" if IS_ADMIN else "Lịch sử hóa đơn do tài khoản của bạn xử lý"

st.markdown(_strip(f"""
<div class="page-header">
    <div class="page-header-left">
        <div class="page-header-badge">
            <span style="width:7px;height:7px;background:#4ADE80;border-radius:50%;display:inline-block;"></span>
            {'ADMIN AUDIT & SYSTEM HISTORY' if IS_ADMIN else 'LỊCH SỬ XỬ LÝ HÓA ĐƠN'}
        </div>
        <h1>📋 Lịch sử hóa đơn</h1>
        <p>{page_desc}</p>
    </div>
    <div class="header-period-pill">
        <span>KỲ XỬ LÝ HIỆN TẠI</span>
        Tháng {now.month:02d}/{now.year}
    </div>
</div>
"""), unsafe_allow_html=True)


# ─── 3. THÔNG BÁO HỆ THỐNG ────────────────────────────────────────────────────
if cleanup_notice:
    st.markdown(f'<div class="success-notice">✅ {cleanup_notice}</div>', unsafe_allow_html=True)
if delete_notice:
    st.markdown(f'<div class="success-notice">🗑️ {delete_notice}</div>', unsafe_allow_html=True)


# ─── 4. CÁC THẺ CHỈ SỐ METRIC ─────────────────────────────────────────────────
total_value_fmt = (
    f"{total_value / 1_000_000:,.1f}M đ"
    if total_value >= 1_000_000
    else f"{total_value:,.0f} đ"
)

st.markdown(_strip(f"""
<div class="metric-grid">
    <div class="metric-card blue" data-icon="📄">
        <div class="metric-label">Tổng hóa đơn</div>
        <div class="metric-value">{total}</div>
        <div class="metric-sub">{duplicate_count} trùng · {failed_count} lỗi</div>
    </div>
    <div class="metric-card green" data-icon="✅">
        <div class="metric-label">Hoàn tất</div>
        <div class="metric-value">{success_count}</div>
        <div class="metric-sub">Tỉ lệ chính xác: {success_rate}%</div>
    </div>
    <div class="metric-card orange" data-icon="⏳">
        <div class="metric-label">Đang xử lý / Chờ</div>
        <div class="metric-value">{pending_count}</div>
        <div class="metric-sub">{duplicate_count} trùng lặp đã nhận diện</div>
    </div>
    <div class="metric-card purple" data-icon="💰">
        <div class="metric-label">Tổng giá trị</div>
        <div class="metric-value" style="font-size:22px;">{total_value_fmt}</div>
        <div class="metric-sub">Từ {success_count} hóa đơn thành công</div>
    </div>
</div>
"""), unsafe_allow_html=True)


# ─── 5. QUẢN TRỊ ADMIN (NẾU CÓ) ───────────────────────────────────────────────
if IS_ADMIN:
    with st.expander("⚙️ Bảng quản trị nâng cao — Dọn dẹp & xóa hóa đơn trùng lặp/lỗi", expanded=False):
        if deletable_rows:
            st.markdown("##### 🗑️ Xóa dòng lịch sử trùng hoặc lỗi theo lựa chọn")
            row_by_label = {
                (
                    f"#{row['job_id']} — {row['file_name'] or 'Không tên'} "
                    f"— {'Trùng hóa đơn' if row['status'] == 'duplicate' else 'Lỗi'}"
                ): row
                for row in deletable_rows
            }
            selected_labels = st.multiselect(
                "Chọn các hóa đơn cần loại bỏ khỏi lịch sử",
                options=list(row_by_label),
                placeholder="Chọn hóa đơn trùng hoặc bị lỗi...",
            )
            confirm_delete = st.checkbox("Xác nhận xóa vĩnh viễn các dòng đã chọn.")
            if st.button("Xóa các bản ghi đã chọn", type="primary",
                         disabled=not selected_labels or not confirm_delete):
                selected_job_ids = [row_by_label[lbl]["job_id"] for lbl in selected_labels]
                deleted = delete_selected_history_jobs(selected_job_ids, is_admin=True)
                st.session_state["history_delete_notice"] = (
                    f"Đã xóa {deleted['job_count']} dòng lịch sử và {deleted['invoice_count']} bản ghi trùng."
                )
                st.rerun()
        else:
            st.info("Không có hóa đơn trùng hoặc bị lỗi cần xóa.")

        st.divider()

        duplicate_cleanup = get_duplicate_cleanup_preview(is_admin=True)
        if duplicate_cleanup["invoice_count"] or duplicate_cleanup["job_count"]:
            st.markdown(_strip(f"""
            <div class="warn-notice">
                ⚠️ Hệ thống phát hiện <strong>{duplicate_cleanup['invoice_count']}</strong> bản ghi trùng lặp
                và <strong>{duplicate_cleanup['job_count']}</strong> dòng lịch sử có thể dọn dẹp.
                Hệ thống sẽ giữ lại bản gốc được tạo sớm nhất.
            </div>
            """), unsafe_allow_html=True)
            confirm_cleanup = st.checkbox("Xác nhận dọn dẹp toàn bộ dữ liệu trùng lặp.")
            if st.button("Dọn dẹp bản ghi trùng", type="primary", disabled=not confirm_cleanup):
                deleted = cleanup_duplicate_invoices(is_admin=True)
                st.session_state["duplicate_cleanup_notice"] = (
                    f"Đã xóa {deleted['job_count']} dòng lịch sử và {deleted['invoice_count']} bản ghi trùng."
                )
                st.rerun()


# ─── 6. BỘ LỌC & TÌM KIẾM ────────────────────────────────────────────────────
col_search, col_filter = st.columns([4, 3])
with col_search:
    keyword = st.text_input(
        "search",
        label_visibility="collapsed",
        placeholder="🔍 Tìm theo mã HĐ, tên công ty, MST, số hóa đơn, tên tệp...",
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
    kw = keyword.lower()
    filtered = [
        r for r in filtered
        if kw in (r["ten_cong_ty_ban"] or "").lower()
        or kw in (r["ma_so_thue_ban"] or "").lower()
        or kw in (r["file_name"] or "").lower()
        or kw in (r.get("so_hoa_don") or "").lower()
    ]
if status_filter != "Tất cả":
    filtered = [r for r in filtered if r["status"] == STATUS_MAP[status_filter]]


# Thanh tóm tắt kết quả
def _stat_pill(label: str, count: int, bg: str, color: str) -> str:
    return (
        f'<span class="stat-pill" style="background:{bg};color:{color};">'
        f'{label}: <strong>{count}</strong></span>'
    )

pills = "".join([
    _stat_pill("Hiển thị", len(filtered), "#EEF2FF", "#4F46E5"),
    _stat_pill("Hoàn tất", sum(1 for r in filtered if r["status"] == "success"), "#DCFCE7", "#15803D"),
    _stat_pill("Trùng", sum(1 for r in filtered if r["status"] == "duplicate"), "#FEF3C7", "#92400E"),
    _stat_pill("Đang xử lý", sum(1 for r in filtered if r["status"] == "processing"), "#DBEAFE", "#1E40AF"),
    _stat_pill("Lỗi", sum(1 for r in filtered if r["status"] == "failed"), "#FEE2E2", "#991B1B"),
])
st.markdown(f'<div class="stat-row">{pills}</div>', unsafe_allow_html=True)


# ─── 7. BẢNG DỮ LIỆU KỸ THUẬT ────────────────────────────────────────────────
def _badge(status: str) -> str:
    cfg = {
        "success": ("badge-success", "Hoàn tất"),
        "duplicate": ("badge-duplicate", "Trùng hóa đơn"),
        "processing": ("badge-processing", "Đang xử lý"),
        "failed": ("badge-failed", "Lỗi"),
    }
    cls, label = cfg.get(status, ("", status))
    return f'<span class="badge {cls}"><span class="badge-dot"></span>{label}</span>'


if not filtered:
    st.markdown(_strip("""
    <div class="empty-state">
        <div class="empty-state-icon">🔍</div>
        <h3>Không tìm thấy dữ liệu hóa đơn phù hợp</h3>
        <p>Vui lòng thử tìm kiếm với từ khóa khác hoặc chuyển chế độ lọc trạng thái.</p>
    </div>
    """), unsafe_allow_html=True)
else:
    admin_th = "<th>Người tải lên</th>" if IS_ADMIN else ""
    rows_html = ""

    for idx, row in enumerate(filtered, 1):
        created_at = pd.to_datetime(row["created_at"])
        invoice_code = f"INV-{created_at.year}-{row['job_id']:04d}"

        # Số tiền
        if row["tong_thanh_toan"] is not None:
            v = row["tong_thanh_toan"]
            amt_fmt = f"{v/1_000_000:,.2f}M đ" if v >= 1_000_000 else f"{v:,.0f} đ"
            amount_cell = f'<td><span class="amount-cell">{amt_fmt}</span></td>'
        else:
            amount_cell = '<td><span class="amount-none">—</span></td>'

        # Tên tệp
        fname = html.escape(str(row["file_name"] or "—"))
        file_cell = f'<td><span class="file-chip" title="{fname}">📄 {fname}</span></td>'

        # Người tải lên (Admin)
        uploader_cell = ""
        if IS_ADMIN:
            upl = html.escape(str(
                row.get("uploader_full_name") or row.get("uploader_username") or "—"
            ))
            uploader_cell = f'<td><span class="uploader-pill">👤 {upl}</span></td>'

        date_upload = created_at.strftime("%d/%m/%Y %H:%M")
        ngay_lap = html.escape(str(row["ngay_lap"] or "—"))
        supplier = html.escape(str(row["ten_cong_ty_ban"] or "—"))
        mst = html.escape(str(row["ma_so_thue_ban"] or "—"))
        so_hd = html.escape(str(row.get("so_hoa_don") or "—"))

        rows_html += _strip(f"""
        <tr>
            <td class="row-idx">{idx}</td>
            <td><span class="inv-code">{invoice_code}</span></td>
            {file_cell}
            {uploader_cell}
            <td style="max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{supplier}">{supplier}</td>
            <td style="font-family:'JetBrains Mono',monospace;font-size:12px;color:#4F46E5;">{mst}</td>
            <td style="color:#475569;font-weight:600;">{so_hd}</td>
            <td class="date-cell">{ngay_lap}</td>
            {amount_cell}
            <td class="date-cell">{date_upload}</td>
            <td>{_badge(row['status'])}</td>
        </tr>
        """)

    table_html = f"""
    <div class="inv-table-wrap">
    <table class="inv-table">
    <thead><tr>
    <th style="width:36px;text-align:center;">#</th>
    <th>Mã hóa đơn</th>
    <th>Tên tệp</th>
    {admin_th}
    <th>Nhà cung cấp</th>
    <th>Mã số thuế</th>
    <th>Số HĐ</th>
    <th>Ngày lập</th>
    <th>Tổng thanh toán</th>
    <th>Thời gian tải</th>
    <th>Trạng thái</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
    </table>
    </div>
    """
    st.markdown(_strip(table_html), unsafe_allow_html=True)

    failed_rows = [r for r in filtered if r["status"] == "failed"]
    if failed_rows:
        st.markdown(
            f'<div class="info-bar">ℹ️ <strong>{len(failed_rows)}</strong> hóa đơn gặp sự cố xử lý. '
            f'Chi tiết kỹ thuật đã được ghi nhận vào hệ thống nhật ký (Server Logs).</div>',
            unsafe_allow_html=True,
        )
