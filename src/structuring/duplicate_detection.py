import re
from datetime import datetime
from decimal import Decimal, InvalidOperation


AMOUNT_TOLERANCE = Decimal("1")
DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y")


def _normalize_identifier(value):
    if value is None:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def _normalize_date(value):
    if value is None:
        return ""
    raw_value = str(value).strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(raw_value, date_format).date().isoformat()
        except ValueError:
            continue
    return ""


def _normalize_amount(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount.is_finite() else None


def find_duplicate_groups(invoices):
    """Group invoice records by normalized seller tax ID and invoice number."""
    candidates_by_key = {}
    for invoice in invoices:
        seller_tax_id = _normalize_identifier(invoice.get("ma_so_thue_ban"))
        invoice_number = _normalize_identifier(invoice.get("so_hoa_don"))
        if not seller_tax_id or not invoice_number:
            continue
        candidates_by_key.setdefault((seller_tax_id, invoice_number), []).append(invoice)

    duplicate_groups = []
    for (seller_tax_id, invoice_number), matching_invoices in candidates_by_key.items():
        if len(matching_invoices) < 2:
            continue

        reference = matching_invoices[0]
        reference_date = _normalize_date(reference.get("ngay_lap"))
        reference_amount = _normalize_amount(reference.get("tong_thanh_toan"))
        dates_match = bool(reference_date) and all(
            _normalize_date(invoice.get("ngay_lap")) == reference_date
            for invoice in matching_invoices[1:]
        )
        amounts_match = reference_amount is not None and all(
            (amount := _normalize_amount(invoice.get("tong_thanh_toan"))) is not None
            and abs(amount - reference_amount) <= AMOUNT_TOLERANCE
            for invoice in matching_invoices[1:]
        )

        duplicate_groups.append({
            "seller_tax_id": seller_tax_id,
            "invoice_number": invoice_number,
            "invoices": matching_invoices,
            "dates_match": dates_match,
            "amounts_match": amounts_match,
            "exact_match": dates_match and amounts_match,
        })
    return duplicate_groups
