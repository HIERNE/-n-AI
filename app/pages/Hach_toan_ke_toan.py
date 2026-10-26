import streamlit as st
st.set_page_config(page_title="Hạch toán kế toán", layout="wide")

import pandas as pd
from pathlib import Path
import sys
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.db_handler import get_confirmed_invoices, set_invoice_payment_status
from app.components.auth import render_account_menu, require_admin
from app.components.sidebar_nav import render_sidebar

admin_user = require_admin()
admin_user_id = int(admin_user["id"])
render_sidebar("accounting")
render_account_menu()
css_path = Path(__file__).resolve().parents[1] / "style.css"
st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

st.title("🧮 Hạch toán kế toán")
st.caption("Tổng hợp số liệu để phục vụ hạch toán")
payment_notice = st.session_state.pop("payment_status_notice", None)
if payment_notice:
    st.success(payment_notice)

invoices = get_confirmed_invoices(is_admin=True)


def format_amount(value):
    return f"{value:,.0f}".replace(",", ".") if value is not None else "—"


def create_excel_export(records):
    headers = [
        "STT", "ID", "Ngày lập", "Công ty bán", "MST bán", "Công ty mua",
        "MST mua", "Số hóa đơn", "Tiền hàng (đ)", "Tiền VAT (đ)",
        "Tổng TT (đ)", "Tình trạng thanh toán",
    ]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Hóa đơn đã hạch toán"
    sheet.append(headers)

    for index, record in enumerate(records, start=1):
        sheet.append([
            index,
            record.get("id"),
            record.get("ngay_lap"),
            record.get("ten_cong_ty_ban"),
            record.get("ma_so_thue_ban"),
            record.get("ten_cong_ty_mua"),
            record.get("ma_so_thue_mua"),
            record.get("so_hoa_don"),
            record.get("tong_tien_hang") or 0,
            record.get("tien_thue_vat") or 0,
            record.get("tong_thanh_toan") or 0,
            "Đã thanh toán" if record.get("payment_status", "unpaid") == "paid" else "Chưa thanh toán",
        ])

    total_row = len(records) + 2
    sheet.cell(total_row, 1, "TỔNG CỘNG")
    for column in (9, 10, 11):
        letter = sheet.cell(1, column).column_letter
        sheet.cell(total_row, column, f"=SUM({letter}2:{letter}{total_row - 1})")

    header_fill = PatternFill("solid", fgColor="1F466D")
    total_fill = PatternFill("solid", fgColor="D9E5F5")
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
    for cell in sheet[total_row]:
        cell.font = Font(bold=True)
        cell.fill = total_fill
    for row in sheet.iter_rows(min_row=2, min_col=9, max_col=11):
        for cell in row:
            cell.number_format = '#,##0'

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:L{len(records) + 1}"
    widths = [8, 8, 14, 34, 18, 38, 18, 18, 18, 18, 18, 20]
    for column, width in enumerate(widths, start=1):
        sheet.column_dimensions[sheet.cell(1, column).column_letter].width = width

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()

payment_status_values = {
    "Chưa thanh toán": "unpaid",
    "Đã thanh toán": "paid",
}
paid_invoices = [invoice for invoice in invoices if invoice.get("payment_status", "unpaid") == "paid"]
unpaid_invoices = [
    invoice for invoice in invoices if invoice.get("payment_status", "unpaid") == "unpaid"
]
paid_total = sum(invoice.get("tong_thanh_toan") or 0 for invoice in paid_invoices)
unpaid_total = sum(invoice.get("tong_thanh_toan") or 0 for invoice in unpaid_invoices)

filter_col, count_col, paid_col, unpaid_col = st.columns([1.35, 0.8, 1.1, 1.15])
with filter_col:
    with st.container(border=True):
        st.markdown("**Bộ lọc thanh toán**")
        payment_filter = st.selectbox(
            "Lọc danh sách",
            ["Tất cả", "Chưa thanh toán", "Đã thanh toán"],
            label_visibility="collapsed",
        )
        st.caption("Áp dụng cho bảng và tệp Excel")
with count_col:
    with st.container(border=True):
        st.metric("Tổng hóa đơn", len(invoices))
with paid_col:
    with st.container(border=True):
        st.metric(
            "Đã thanh toán",
            f"{len(paid_invoices)} · {paid_total:,.0f} đ",
        )
with unpaid_col:
    with st.container(border=True):
        st.metric(
            "Chưa thanh toán",
            f"{len(unpaid_invoices)} · {unpaid_total:,.0f} đ",
        )

filtered_invoices = [
    invoice for invoice in invoices
    if payment_filter == "Tất cả"
    or invoice.get("payment_status", "unpaid") == payment_status_values[payment_filter]
]

if not invoices:
    st.info("Chưa có dữ liệu hóa đơn để hạch toán.")
elif not filtered_invoices:
    st.info("Không có hóa đơn phù hợp với tình trạng thanh toán đã chọn.")
else:
    total_before_tax = sum(r.get("tong_tien_hang") or 0 for r in filtered_invoices)
    total_vat = sum(r.get("tien_thue_vat") or 0 for r in filtered_invoices)
    total_payment = sum(r.get("tong_thanh_toan") or 0 for r in filtered_invoices)

    c1, c2, c3 = st.columns(3)
    c1.metric("Tiền hàng theo bộ lọc", f"{total_before_tax:,.0f} đ")
    c2.metric("Thuế VAT theo bộ lọc", f"{total_vat:,.0f} đ")
    c3.metric("Tổng thanh toán theo bộ lọc", f"{total_payment:,.0f} đ")

    st.divider()
    st.markdown(f"##### Chi tiết {len(filtered_invoices)} hóa đơn")
    invoice_rows = [
        {
            "STT": index,
            "ID": record.get("id"),
            "Ngày lập": record.get("ngay_lap"),
            "Công ty bán": record.get("ten_cong_ty_ban"),
            "MST bán": record.get("ma_so_thue_ban"),
            "Công ty mua": record.get("ten_cong_ty_mua"),
            "MST mua": record.get("ma_so_thue_mua"),
            "Số hóa đơn": record.get("so_hoa_don") or "—",
            "Tiền hàng (đ)": format_amount(record.get("tong_tien_hang")),
            "Tiền VAT (đ)": format_amount(record.get("tien_thue_vat")),
            "Tổng TT (đ)": format_amount(record.get("tong_thanh_toan")),
            "Tình trạng thanh toán": (
                "Đã thanh toán"
                if record.get("payment_status", "unpaid") == "paid"
                else "Chưa thanh toán"
            ),
        }
        for index, record in enumerate(filtered_invoices, start=1)
    ]
    edited_invoices = st.data_editor(
        pd.DataFrame(invoice_rows),
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        disabled=[
            "STT", "ID", "Ngày lập", "Công ty bán", "MST bán",
            "Công ty mua", "MST mua", "Tiền hàng (đ)", "Tiền VAT (đ)", "Tổng TT (đ)",
        ],
        column_config={
            "Tình trạng thanh toán": st.column_config.SelectboxColumn(
                "Tình trạng thanh toán",
                options=["Chưa thanh toán", "Đã thanh toán"],
                required=True,
                width="medium",
            ),
        },
        key=f"invoice_payment_editor_{payment_filter}",
    )

    current_status_by_id = {
        invoice["id"]: invoice.get("payment_status", "unpaid")
        for invoice in filtered_invoices
    }
    updated_count = 0
    for edited_invoice in edited_invoices.to_dict(orient="records"):
        invoice_id = edited_invoice["ID"]
        selected_status = payment_status_values[edited_invoice["Tình trạng thanh toán"]]
        if selected_status != current_status_by_id[invoice_id]:
            set_invoice_payment_status(
                invoice_id,
                selected_status,
                is_admin=True,
                actor_user_id=admin_user_id,
            )
            updated_count += 1

    if updated_count:
        st.session_state["payment_status_notice"] = (
            f"Đã cập nhật tình trạng thanh toán cho {updated_count} hóa đơn."
        )
        st.rerun()

    st.download_button(
        "⬇️ Xuất Excel các hóa đơn đã hạch toán",
        data=create_excel_export(filtered_invoices),
        file_name="hoa_don_hach_toan_theo_bo_loc.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.divider()
    st.info(
        "⚙️ Tính năng định khoản tự động (sinh bút toán Nợ/Có theo tài khoản kế toán) "
        "nằm trong hướng phát triển tiếp theo của đồ án, ngoài phạm vi 9 buổi hiện tại."
    )