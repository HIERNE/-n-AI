import streamlit as st
st.set_page_config(page_title="Trích xuất dữ liệu", layout="wide")

import json
from pathlib import Path
import sys
import html
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.db_handler import (
    get_all_invoices,
    set_invoice_accounting_status,
    set_invoice_source_image,
    update_invoice_data,
)
from src.preprocessing.pdf_converter import pdf_to_images
from src.structuring.invoice_validation import validate_invoice_data
from src.structuring.duplicate_detection import find_duplicate_groups
from app.components.auth import render_account_menu, require_auth
from app.components.sidebar_nav import render_sidebar

user = require_auth()
USER_ID = int(user["id"])
IS_ADMIN = user["role"] == "admin"

render_sidebar("extract")
render_account_menu()

# Tải CSS dùng chung từ style.css
css_path = Path(__file__).resolve().parents[1] / "style.css"
st.markdown(
    f"<style>{css_path.read_text(encoding='utf-8')}</style>",
    unsafe_allow_html=True,
)


def _strip(s: str) -> str:
    """Xóa khoảng trắng thừa đầu dòng để tránh lỗi Markdown code block."""
    return "\n".join(line.strip() for line in s.split("\n"))


# ─── 1. HEADER TRANG KỸ THUẬT ──────────────────────────────────────────────────
now = datetime.now()
st.markdown(_strip(f"""
<div class="page-header">
    <div class="page-header-left">
        <div class="page-header-badge">
            <span style="width:7px;height:7px;background:#38BDF8;border-radius:50%;display:inline-block;"></span>
            AI OCR &amp; DATA INSPECTION STUDIO
        </div>
        <h1>🔬 Trích xuất &amp; Kiểm toán dữ liệu</h1>
        <p>Bóc tách chi tiết thông tin hóa đơn, kiểm tra tính toàn vẹn số học và đối soát hóa đơn trùng lặp</p>
    </div>
    <div class="header-period-pill">
        <span>KỲ KIỂM ĐỊNH</span>
        Tháng {now.month:02d}/{now.year}
    </div>
</div>
"""), unsafe_allow_html=True)

review_notice = st.session_state.pop("invoice_review_notice", None)
if review_notice:
    notice_type, notice_text = review_notice
    if notice_type == "success":
        st.markdown(f'<div class="success-notice">✅ {notice_text}</div>', unsafe_allow_html=True)
    elif notice_type == "warning":
        st.markdown(f'<div class="warn-notice">⚠️ {notice_text}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="info-bar">ℹ️ {notice_text}</div>', unsafe_allow_html=True)

# ─── 2. TẢI DANH SÁCH HÓA ĐƠN ─────────────────────────────────────────────────
invoices = get_all_invoices(user_id=USER_ID, is_admin=IS_ADMIN)

if not invoices:
    st.markdown(_strip("""
    <div class="empty-state">
        <div class="empty-state-icon">📂</div>
        <h3>Chưa có dữ liệu hóa đơn nào</h3>
        <p>Vui lòng chuyển tới mục <strong>Tải lên hóa đơn</strong> để xử lý tệp PDF hoặc ảnh hóa đơn mới.</p>
    </div>
    """), unsafe_allow_html=True)
else:
    # ─── 3. THANH CHỌN HÓA ĐƠN & THÔNG TIN TỔNG QUAN ───────────────────────────
    options = {
        f"#{r['id']:04d} — {r['ten_cong_ty_ban'] or 'Không rõ NCC'} | {r.get('so_hoa_don') or 'Chưa có số'} ({r['ngay_lap'] or '—'})": r
        for r in invoices
    }

    selected_label = st.selectbox(
        "🔍 Chọn hồ sơ hóa đơn cần xem chi tiết:",
        list(options.keys()),
        help="Chọn một hóa đơn từ danh sách để xem ảnh gốc và toàn bộ trường dữ liệu bóc tách",
    )
    record = options[selected_label]

    status_cfg = {
        "pending": ("#DBEAFE", "#1E40AF", "Chờ xác nhận"),
        "confirmed": ("#DCFCE7", "#15803D", "Đã xác nhận (Approved)"),
        "rejected": ("#FEE2E2", "#991B1B", "Từ chối (Rejected)"),
    }
    cur_status = record.get("accounting_status", "pending")
    st_bg, st_color, st_text = status_cfg.get(cur_status, ("#F1F5F9", "#475569", cur_status))

    uploader_name = (
        record.get("uploader_full_name")
        or record.get("uploader_username")
        or "Chưa xác định"
    )

    st.markdown(_strip(f"""
    <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:14px 20px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
        <div style="display:flex;align-items:center;gap:14px;">
            <span class="inv-code">DOC-ID #{record['id']:04d}</span>
            <span style="font-weight:700;color:#0F172A;font-size:15px;">{html.escape(str(record.get('ten_cong_ty_ban') or 'Chưa rõ nhà cung cấp'))}</span>
            <span style="font-size:13px;color:#64748B;">Số HĐ: <strong style="color:#1E293B;">{html.escape(str(record.get('so_hoa_don') or '—'))}</strong></span>
        </div>
        <div style="display:flex;align-items:center;gap:10px;">
            {"<span style='font-size:12px;color:#64748B;'>Người tải: <strong>" + html.escape(str(uploader_name)) + "</strong></span>" if IS_ADMIN else ""}
            <span style="background:{st_bg};color:{st_color};font-size:12px;font-weight:700;padding:4px 12px;border-radius:99px;border:1px solid {st_color}33;">
                {st_text}
            </span>
        </div>
    </div>
    """), unsafe_allow_html=True)

    # ─── 4. BỐ CỤC 2 CỘT CHUYÊN NGHIỆP ─────────────────────────────────────────
    col_left, col_right = st.columns([1, 1], gap="medium")

    # ─── CỘT TRÁI: DOCUMENT PREVIEW ───────────────────────────────────────────
    with col_left:
        st.markdown(_strip("""
        <div class="tech-card-header">
            <div class="tech-card-title">
                <span>📄</span> Tài liệu nguồn (Original Document)
            </div>
            <span class="tech-card-tag">VIEWER</span>
        </div>
        """), unsafe_allow_html=True)

        source_image = record.get("source_image")
        source_path = None

        if source_image:
            stored_path = Path(source_image)
            user_upload_dir = PROJECT_ROOT / "data" / "uploads" / f"user_{USER_ID}"
            if IS_ADMIN:
                image_candidates = [
                    stored_path,
                    PROJECT_ROOT / stored_path,
                    *(PROJECT_ROOT / folder / stored_path.name for folder in (
                        "data/uploads", "data/raw", "data/processed"
                    )),
                ]
            else:
                image_candidates = [
                    stored_path,
                    PROJECT_ROOT / stored_path,
                    user_upload_dir / stored_path.name,
                ]
            for candidate in image_candidates:
                try:
                    candidate.resolve().relative_to(user_upload_dir.resolve())
                    belongs_to_user = True
                except ValueError:
                    belongs_to_user = IS_ADMIN
                if candidate.is_file() and belongs_to_user:
                    source_path = candidate
                    break

        if source_path is not None:
            if source_path.suffix.lower() == ".pdf":
                preview_paths = [
                    Path(path)
                    for path in pdf_to_images(source_path, output_dir=source_path.parent)
                ]
            else:
                preview_paths = [source_path]

            for page_number, preview_path in enumerate(preview_paths, start=1):
                caption = (
                    f"Trang {page_number}/{len(preview_paths)}"
                    if source_path.suffix.lower() == ".pdf"
                    else None
                )
                st.image(
                    str(preview_path),
                    caption=caption,
                    use_column_width=True,
                )

            file_size_kb = round(source_path.stat().st_size / 1024, 1)
            st.markdown(_strip(f"""
            <div class="doc-meta-bar">
                <span>📁 <strong>{html.escape(source_path.name)}</strong></span>
                <span>Định dạng: <strong>{source_path.suffix.upper()}</strong> ({file_size_kb} KB)</span>
            </div>
            """), unsafe_allow_html=True)
        else:
            if source_image:
                st.markdown(_strip("""
                <div class="warn-notice">
                    ⚠️ Không tìm thấy đường dẫn tệp ảnh gốc trên máy chủ. Bạn có thể liên kết lại từ danh sách bên dưới.
                </div>
                """), unsafe_allow_html=True)
            else:
                st.markdown(_strip("""
                <div class="info-bar">
                    ℹ️ Hóa đơn cũ chưa được gán tệp nguồn. Vui lòng chọn tệp bên dưới để đồng bộ hiển thị.
                </div>
                """), unsafe_allow_html=True)

            source_folders = (
                [
                    PROJECT_ROOT / "data" / "uploads",
                    PROJECT_ROOT / "data" / "raw",
                    PROJECT_ROOT / "data" / "processed",
                ]
                if IS_ADMIN else [PROJECT_ROOT / "data" / "uploads" / f"user_{USER_ID}"]
            )
            available_sources = sorted(
                (
                    path
                    for folder in source_folders
                    if folder.is_dir()
                    for path in folder.rglob("*")
                    if path.is_file()
                    and path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"}
                ),
                key=lambda path: (path.parent.name, path.name.lower()),
            )
            if available_sources:
                source_options = {
                    f"{path.parent.name}/{path.name}": path
                    for path in available_sources
                }
                selected_source = st.selectbox(
                    "Chọn tệp nguồn từ máy chủ để liên kết:",
                    [""] + list(source_options),
                    key=f"source_image_{record['id']}",
                )
                if selected_source:
                    selected_path = source_options[selected_source]
                    if selected_path.suffix.lower() == ".pdf":
                        preview_paths = [
                            Path(path)
                            for path in pdf_to_images(
                                selected_path, output_dir=selected_path.parent
                            )
                        ]
                    else:
                        preview_paths = [selected_path]
                    for page_number, preview_path in enumerate(preview_paths, start=1):
                        caption = (
                            f"Trang {page_number}/{len(preview_paths)}"
                            if selected_path.suffix.lower() == ".pdf"
                            else None
                        )
                        st.image(
                            str(preview_path),
                            caption=caption,
                            use_column_width=True,
                        )
                    if st.button("Lưu liên kết tệp cho hóa đơn này", key=f"save_source_image_{record['id']}", type="primary"):
                        relative_path = selected_path.relative_to(PROJECT_ROOT).as_posix()
                        set_invoice_source_image(
                            record["id"], relative_path, user_id=USER_ID, is_admin=IS_ADMIN
                        )
                        st.success("Đã cập nhật liên kết tệp thành công.")
                        st.rerun()

    # ─── CỘT PHẢI: AI DATA INSPECTION & VALIDATION ────────────────────────────
    with col_right:
        st.markdown(_strip("""
        <div class="tech-card-header">
            <div class="tech-card-title">
                <span>🤖</span> Bóc tách AI &amp; Kiểm toán (Audit Inspector)
            </div>
            <span class="tech-card-tag">SCHEMA V2.0</span>
        </div>
        """), unsafe_allow_html=True)

        # ── Kiểm tra tính toàn vẹn (Validation)
        findings = validate_invoice_data(record)
        if findings:
            findings_html = "".join(f"<li>{html.escape(str(f))}</li>" for f in findings)
            st.markdown(_strip(f"""
            <div class="warn-notice" style="display:block;">
                <div style="font-weight:700;margin-bottom:6px;">⚠️ Cần đối soát lại các điểm số học / logic:</div>
                <ul style="margin:0;padding-left:18px;font-size:12.5px;">{findings_html}</ul>
            </div>
            """), unsafe_allow_html=True)
        else:
            st.markdown(_strip("""
            <div class="success-notice">
                ✅ <strong>Kiểm toán số học hoàn tất:</strong> Tiền hàng + Thuế VAT khớp hoàn toàn với Tổng thanh toán.
            </div>
            """), unsafe_allow_html=True)

        # ── Kiểm tra trùng lặp (Duplicate Detection)
        duplicate_groups = find_duplicate_groups(invoices)
        duplicate_group = next(
            (
                g for g in duplicate_groups
                if any(inv.get("id") == record["id"] for inv in g["invoices"])
            ),
            None,
        )
        if duplicate_group:
            other_invoices = [
                inv for inv in duplicate_group["invoices"]
                if inv.get("id") != record["id"]
            ]
            if other_invoices:
                st.markdown(_strip(f"""
                <div class="warn-notice">
                    ⚠️ <strong>Cảnh báo trùng lặp:</strong> Phát hiện {len(other_invoices)} hóa đơn khác có dữ liệu tương đồng.
                </div>
                """), unsafe_allow_html=True)
                st.dataframe(
                    [
                        {
                            "ID": inv.get("id"),
                            "Số HĐ": inv.get("so_hoa_don") or "—",
                            "Ngày lập": inv.get("ngay_lap") or "—",
                            "Tổng tiền": f"{inv.get('tong_thanh_toan'):,.0f} đ" if inv.get("tong_thanh_toan") else "—",
                            "Tệp nguồn": inv.get("source_image") or "—",
                        }
                        for inv in other_invoices
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

        # ── Đọc danh sách mặt hàng
        items_data = record.get("danh_sach_mat_hang", "[]")
        if isinstance(items_data, str):
            try:
                items_data = json.loads(items_data or "[]")
            except json.JSONDecodeError:
                items_data = []
                st.error("Dữ liệu danh sách mặt hàng bị lỗi định dạng JSON.")

        # ── Form chỉnh sửa & đối soát
        with st.form(f"invoice_review_form_{record['id']}"):
            st.markdown("##### 🏢 Thông tin đối tác bên bán & bên mua")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                ten_cong_ty_ban = st.text_input("Tên công ty bán", record.get("ten_cong_ty_ban") or "")
                ma_so_thue_ban = st.text_input("Mã số thuế bên bán", record.get("ma_so_thue_ban") or "")
            with col_b2:
                ten_cong_ty_mua = st.text_input("Tên công ty mua", record.get("ten_cong_ty_mua") or "")
                ma_so_thue_mua = st.text_input("Mã số thuế bên mua", record.get("ma_so_thue_mua") or "")

            st.markdown("##### 📑 Chi tiết chứng từ hóa đơn")
            col_doc1, col_doc2, col_doc3 = st.columns(3)
            with col_doc1:
                so_hoa_don = st.text_input("Số hóa đơn", record.get("so_hoa_don") or "")
            with col_doc2:
                ngay_lap = st.text_input("Ngày lập hóa đơn", record.get("ngay_lap") or "")
            with col_doc3:
                thue_suat_vat = st.text_input("Thuế suất VAT (%)", record.get("thue_suat_vat") or "")

            st.markdown("##### 📦 Danh mục chi tiết mặt hàng")
            edited_items = st.data_editor(
                items_data,
                num_rows="dynamic",
                use_container_width=True,
                key=f"editor_items_{record['id']}",
            )

            st.markdown("##### 💰 Tổng kết số liệu tài chính")
            col_tot1, col_tot2, col_tot3 = st.columns(3)
            with col_tot1:
                tong_tien_hang = st.number_input(
                    "Tiền hàng (chưa VAT)",
                    value=float(record.get("tong_tien_hang") or 0),
                    format="%.0f",
                )
            with col_tot2:
                tien_thue_vat = st.number_input(
                    "Tiền thuế VAT",
                    value=float(record.get("tien_thue_vat") or 0),
                    format="%.0f",
                )
            with col_tot3:
                tong_thanh_toan = st.number_input(
                    "Tổng thanh toán",
                    value=float(record.get("tong_thanh_toan") or 0),
                    format="%.0f",
                )

            # Thẻ số liệu tài chính dạng widget kỹ thuật
            st.markdown(_strip(f"""
            <div class="finance-summary-grid">
                <div class="finance-cell">
                    <div class="finance-cell-label">Tiền hàng</div>
                    <div class="finance-cell-value">{tong_tien_hang:,.0f} đ</div>
                </div>
                <div class="finance-cell">
                    <div class="finance-cell-label">Thuế VAT</div>
                    <div class="finance-cell-value">{tien_thue_vat:,.0f} đ</div>
                </div>
                <div class="finance-cell">
                    <div class="finance-cell-label">Tổng thanh toán</div>
                    <div class="finance-cell-value highlight">{tong_thanh_toan:,.0f} đ</div>
                </div>
            </div>
            """), unsafe_allow_html=True)

            save_edits = st.form_submit_button(
                "💾 Lưu thay đổi thông tin",
                use_container_width=True,
                type="primary",
                disabled=not IS_ADMIN and cur_status != "pending",
            )

        if not IS_ADMIN and cur_status != "pending":
            st.info("Hóa đơn đã được quản trị viên duyệt/từ chối. Liên hệ Admin nếu cần chỉnh sửa thêm.")

        if save_edits:
            update_invoice_data(record["id"], {
                "ma_so_thue_ban": ma_so_thue_ban.strip(),
                "ten_cong_ty_ban": ten_cong_ty_ban.strip(),
                "so_hoa_don": so_hoa_don.strip() or None,
                "ma_so_thue_mua": ma_so_thue_mua.strip() or None,
                "ten_cong_ty_mua": ten_cong_ty_mua.strip() or None,
                "ngay_lap": ngay_lap.strip(),
                "danh_sach_mat_hang": edited_items.to_dict(orient="records")
                if hasattr(edited_items, "to_dict") else edited_items,
                "tong_tien_hang": tong_tien_hang,
                "thue_suat_vat": thue_suat_vat.strip(),
                "tien_thue_vat": tien_thue_vat,
                "tong_thanh_toan": tong_thanh_toan,
            }, user_id=USER_ID, is_admin=IS_ADMIN)
            st.session_state["invoice_review_notice"] = (
                "success",
                f"Đã cập nhật dữ liệu hóa đơn #{record['id']}. Hồ sơ chuyển về trạng thái chờ xác nhận.",
            )
            st.rerun()

        # ── Phê duyệt / Từ chối (Admin)
        if IS_ADMIN:
            st.markdown("##### ⚖️ Thao tác phê duyệt kế toán (Admin Only)")
            col_acc, col_rej = st.columns(2)
            with col_acc:
                if st.button("✅ Duyệt & Đưa vào hạch toán", use_container_width=True,
                             type="primary", disabled=cur_status == "confirmed", key=f"btn_acc_{record['id']}"):
                    set_invoice_accounting_status(
                        record["id"], "confirmed", is_admin=True, actor_user_id=USER_ID,
                    )
                    st.session_state["invoice_review_notice"] = (
                        "success",
                        f"Đã xác nhận hóa đơn #{record['id']}. Dữ liệu đã sẵn sàng trên Báo cáo tổng hợp & Hạch toán.",
                    )
                    st.rerun()
            with col_rej:
                if st.button("❌ Từ chối hóa đơn", use_container_width=True,
                             disabled=cur_status == "rejected", key=f"btn_rej_{record['id']}"):
                    set_invoice_accounting_status(
                        record["id"], "rejected", is_admin=True, actor_user_id=USER_ID,
                    )
                    st.session_state["invoice_review_notice"] = (
                        "warning",
                        f"Đã từ chối hóa đơn #{record['id']}. Hóa đơn sẽ không được tính vào sổ kế toán.",
                    )
                    st.rerun()
