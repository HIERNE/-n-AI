import json
from datetime import datetime
from decimal import Decimal, InvalidOperation


AMOUNT_TOLERANCE = Decimal("1")


def _to_decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount.is_finite() else None


def _format_amount(value):
    return f"{value:,.0f}".replace(",", ".")


def _load_items(value):
    if isinstance(value, str):
        try:
            value = json.loads(value or "[]")
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, list) else None


def _is_date_format(value, date_format):
    try:
        datetime.strptime(str(value).strip(), date_format)
    except ValueError:
        return False
    return True


def validate_invoice_data(invoice):
    """Return human-readable data-quality findings without modifying the invoice."""
    findings = []

    required_fields = {
        "ma_so_thue_ban": "Mã số thuế bên bán",
        "ten_cong_ty_ban": "Tên công ty bên bán",
        "ngay_lap": "Ngày lập hóa đơn",
        "thue_suat_vat": "Thuế suất VAT",
    }
    for field, label in required_fields.items():
        value = invoice.get(field)
        if value is None or not str(value).strip():
            findings.append(f"Thiếu {label.lower()}.")
    issue_date = invoice.get("ngay_lap")
    if issue_date and not any(
        _is_date_format(issue_date, date_format)
        for date_format in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d")
    ):
        findings.append("Ngày lập hóa đơn không đúng định dạng ngày hợp lệ.")

    amount_fields = {
        "tong_tien_hang": "Tổng tiền hàng",
        "tien_thue_vat": "Tiền thuế VAT",
        "tong_thanh_toan": "Tổng thanh toán",
    }
    amounts = {}
    for field, label in amount_fields.items():
        value = _to_decimal(invoice.get(field))
        if value is None:
            findings.append(f"{label} không có giá trị số hợp lệ.")
        elif value < 0:
            findings.append(f"{label} đang là số âm.")
        else:
            amounts[field] = value

    if len(amounts) == len(amount_fields):
        expected_total = amounts["tong_tien_hang"] + amounts["tien_thue_vat"]
        difference = abs(expected_total - amounts["tong_thanh_toan"])
        if difference > AMOUNT_TOLERANCE:
            findings.append(
                "Tổng tiền hàng + VAT không khớp tổng thanh toán "
                f"(lệch {_format_amount(difference)} đ)."
            )

    items = _load_items(invoice.get("danh_sach_mat_hang", []))
    if items is None:
        findings.append("Danh sách mặt hàng không đúng định dạng.")
        return findings

    if not items:
        findings.append("Không có mặt hàng để đối chiếu.")
        return findings

    item_amounts = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            findings.append(f"Mặt hàng {index} không đúng định dạng.")
            continue

        name = item.get("ten_hang")
        if name is None or not str(name).strip():
            findings.append(f"Mặt hàng {index} thiếu tên hàng.")

        quantity = _to_decimal(item.get("so_luong"))
        unit_price = _to_decimal(item.get("don_gia"))
        line_total = _to_decimal(item.get("thanh_tien"))
        if quantity is None or unit_price is None or line_total is None:
            findings.append(
                f"Mặt hàng {index} thiếu số lượng, đơn giá hoặc thành tiền hợp lệ."
            )
            continue
        if unit_price < 0 or line_total < 0:
            findings.append(f"Mặt hàng {index} có đơn giá hoặc thành tiền âm.")
        expected_line_total = quantity * unit_price
        difference = abs(expected_line_total - line_total)
        if difference > AMOUNT_TOLERANCE:
            findings.append(
                f"Mặt hàng {index}: số lượng × đơn giá không khớp thành tiền "
                f"(lệch {_format_amount(difference)} đ)."
            )
        item_amounts.append(line_total)

    if item_amounts and len(item_amounts) == len(items) and "tong_tien_hang" in amounts:
        items_total = sum(item_amounts, Decimal("0"))
        difference = abs(items_total - amounts["tong_tien_hang"])
        if difference > AMOUNT_TOLERANCE:
            findings.append(
                "Tổng thành tiền các mặt hàng không khớp tổng tiền hàng "
                f"(lệch {_format_amount(difference)} đ)."
            )

    return findings
