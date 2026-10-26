import streamlit as st
st.set_page_config(page_title="Trích xuất dữ liệu", layout="wide")

import json
from pathlib import Path
import sys

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
css_path = Path(__file__).resolve().parents[1] / "style.css"
st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

st.title("📊 Chi tiết trích xuất dữ liệu")
review_notice = st.session_state.pop("invoice_review_notice", None)
if review_notice:
    notice_type, notice_text = review_notice
    getattr(st, notice_type)(notice_text)

invoices = get_all_invoices(user_id=USER_ID, is_admin=IS_ADMIN)
if not invoices:
    st.info("Chưa có hóa đơn nào được xử lý.")
else:
    options = {f"#{r['id']} — {r['ten_cong_ty_ban']} ({r['ngay_lap']})": r for r in invoices}
    selected_label = st.selectbox("Chọn hóa đơn để xem chi tiết", list(options.keys()))
    record = options[selected_label]

    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Ảnh gốc")
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
                preview_path = source_path.with_name(f"{source_path.stem}_page1.jpg")
                if not preview_path.is_file():
                    preview_path = Path(
                        pdf_to_images(source_path, output_dir=source_path.parent)[0]
                    )
            else:
                preview_path = source_path
            st.image(str(preview_path))
        else:
            if source_image:
                st.warning("Không tìm thấy ảnh đã liên kết. Có thể chọn lại từ các tệp cục bộ.")
            else:
                st.info("Hóa đơn cũ chưa liên kết ảnh nguồn. Chọn tệp bên dưới để xem và liên kết.")

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
                    "Tệp ảnh/PDF có sẵn trên máy",
                    [""] + list(source_options),
                    key=f"source_image_{record['id']}",
                )
                if selected_source:
                    selected_path = source_options[selected_source]
                    if selected_path.suffix.lower() == ".pdf":
                        preview_path = selected_path.with_name(
                            f"{selected_path.stem}_page1.jpg"
                        )
                        if not preview_path.is_file():
                            preview_path = Path(
                                pdf_to_images(
                                    selected_path, output_dir=selected_path.parent
                                )[0]
                            )
                    else:
                        preview_path = selected_path
                    st.image(str(preview_path))
                    if st.button(
                        "Lưu liên kết ảnh cho hóa đơn này",
                        key=f"save_source_image_{record['id']}",
                    ):
                        relative_path = selected_path.relative_to(PROJECT_ROOT).as_posix()
                        set_invoice_source_image(
                            record["id"], relative_path, user_id=USER_ID, is_admin=IS_ADMIN
                        )
                        st.success("Đã lưu liên kết ảnh cho hóa đơn.")
                        st.rerun()
            else:
                st.warning("Không tìm thấy tệp ảnh/PDF có thể truy cập cho tài khoản này.")

    with col_right:
        st.subheader("Dữ liệu AI trích xuất")
        if IS_ADMIN:
            uploader = record.get("uploader_full_name") or record.get(
                "uploader_username"
            )
            st.caption(f"Người tải lên: {uploader or 'Chưa xác định (dữ liệu cũ)'}")

        accounting_status = record.get("accounting_status", "pending")
        status_labels = {
            "pending": "Chờ xác nhận",
            "confirmed": "Đã xác nhận",
            "rejected": "Từ chối toàn bộ",
        }
        st.caption(f"Trạng thái: **{status_labels.get(accounting_status, accounting_status)}**")

        items_data = record.get("danh_sach_mat_hang", "[]")
        if isinstance(items_data, str):
            try:
                items_data = json.loads(items_data or "[]")
            except json.JSONDecodeError:
                items_data = []
                st.error("Danh sách mặt hàng không đọc được; vui lòng kiểm tra thủ công.")

        findings = validate_invoice_data(record)
        if findings:
            st.warning("Phát hiện dữ liệu cần rà soát:")
            for finding in findings:
                st.markdown(f"- {finding}")
        else:
            st.success("Không phát hiện sai lệch theo các quy tắc kiểm tra hiện có.")

        duplicate_groups = find_duplicate_groups(invoices)
        duplicate_group = next(
            (
                group for group in duplicate_groups
                if any(invoice.get("id") == record["id"] for invoice in group["invoices"])
            ),
            None,
        )
        if duplicate_group:
            other_invoices = [
                invoice for invoice in duplicate_group["invoices"]
                if invoice.get("id") != record["id"]
            ]
            match_description = (
                "Số hóa đơn, ngày lập và tổng thanh toán khớp."
                if duplicate_group["exact_match"]
                else "Trùng mã số thuế bên bán và số hóa đơn; ngày hoặc tổng tiền có khác biệt cần kiểm tra."
            )
            st.warning(
                f"Có {len(other_invoices)} hóa đơn có khả năng trùng. "
                f"{match_description} Hệ thống không tự xóa hoặc chặn hóa đơn."
            )
            st.dataframe(
                [
                    {
                        "ID": invoice.get("id"),
                        "Số hóa đơn": invoice.get("so_hoa_don") or "—",
                        "Ngày lập": invoice.get("ngay_lap") or "—",
                        "Tổng thanh toán": invoice.get("tong_thanh_toan"),
                        "Tệp nguồn": invoice.get("source_image") or "—",
                    }
                    for invoice in other_invoices
                ],
                use_container_width=True,
                hide_index=True,
            )

        with st.form(f"invoice_review_{record['id']}"):
            st.markdown("**Thông tin hóa đơn**")
            ma_so_thue_ban = st.text_input("Mã số thuế bên bán", record.get("ma_so_thue_ban") or "")
            ten_cong_ty_ban = st.text_input("Tên công ty bên bán", record.get("ten_cong_ty_ban") or "")
            so_hoa_don = st.text_input("Số hóa đơn", record.get("so_hoa_don") or "")
            ma_so_thue_mua = st.text_input("Mã số thuế bên mua", record.get("ma_so_thue_mua") or "")
            ten_cong_ty_mua = st.text_input("Tên công ty bên mua", record.get("ten_cong_ty_mua") or "")
            ngay_lap = st.text_input("Ngày lập", record.get("ngay_lap") or "")
            thue_suat_vat = st.text_input("Thuế suất VAT", record.get("thue_suat_vat") or "")

            st.markdown("**Danh sách mặt hàng**")
            edited_items = st.data_editor(
                items_data,
                num_rows="dynamic",
                use_container_width=True,
                key=f"invoice_items_{record['id']}",
            )

            col_total, col_vat, col_payment = st.columns(3)
            with col_total:
                tong_tien_hang = st.number_input(
                    "Tổng tiền hàng", value=float(record.get("tong_tien_hang") or 0),
                )
            with col_vat:
                tien_thue_vat = st.number_input(
                    "Tiền thuế VAT", value=float(record.get("tien_thue_vat") or 0),
                )
            with col_payment:
                tong_thanh_toan = st.number_input(
                    "Tổng thanh toán", value=float(record.get("tong_thanh_toan") or 0),
                )

            save_edits = st.form_submit_button(
                "Lưu chỉnh sửa",
                use_container_width=True,
                disabled=not IS_ADMIN and accounting_status != "pending",
            )

        if not IS_ADMIN and accounting_status != "pending":
            st.info("Chỉ quản trị viên có thể mở lại hóa đơn đã được duyệt/từ chối.")

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
                f"Đã lưu chỉnh sửa hóa đơn #{record['id']}. Hóa đơn trở về trạng thái chờ xác nhận.",
            )
            st.rerun()

        st.divider()
        if IS_ADMIN:
            col_accept, col_reject = st.columns(2)
            with col_accept:
                if st.button("Chấp nhận", type="primary", use_container_width=True,
                             disabled=accounting_status == "confirmed", key=f"accept_{record['id']}"):
                    set_invoice_accounting_status(
                        record["id"], "confirmed", is_admin=True,
                        actor_user_id=USER_ID,
                    )
                    st.session_state["invoice_review_notice"] = (
                        "success",
                        f"Đã xác nhận hóa đơn #{record['id']}. Hóa đơn đã được đưa vào hạch toán và báo cáo.",
                    )
                    st.rerun()
            with col_reject:
                if st.button("Từ chối toàn bộ", use_container_width=True,
                             disabled=accounting_status == "rejected", key=f"reject_{record['id']}"):
                    set_invoice_accounting_status(
                        record["id"], "rejected", is_admin=True,
                        actor_user_id=USER_ID,
                    )
                    st.session_state["invoice_review_notice"] = (
                        "warning",
                        f"Đã từ chối hóa đơn #{record['id']}. Hóa đơn không được đưa vào hạch toán và báo cáo.",
                    )
                    st.rerun()
        else:
            st.info("Trạng thái duyệt hóa đơn chỉ do quản trị viên thay đổi.")