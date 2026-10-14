import json
from typing import Any

from sqlalchemy import create_engine, inspect, text

from config import DATABASE_URL, DB_PATH
from src.structuring.schemas import Invoice


def _make_engine():
    try:
        import pymysql  # noqa: F401
        return create_engine(DATABASE_URL, pool_pre_ping=True)
    except Exception:
        sqlite_url = f"sqlite:///{DB_PATH}"
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(sqlite_url)


def _id_column(engine) -> str:
    is_sqlite = engine.url.get_backend_name() == "sqlite"
    if is_sqlite:
        return "id INTEGER PRIMARY KEY AUTOINCREMENT"
    return "id INTEGER NOT NULL AUTO_INCREMENT, PRIMARY KEY (id)"


def _ensure_table(engine) -> None:
    id_column = _id_column(engine)
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS invoices (
                {id_column},
                source_image VARCHAR(500),
                source_hash VARCHAR(64),
                ma_so_thue_ban VARCHAR(255),
                ten_cong_ty_ban VARCHAR(255),
                so_hoa_don VARCHAR(100),
                ma_so_thue_mua VARCHAR(255),
                ten_cong_ty_mua VARCHAR(255),
                ngay_lap VARCHAR(50),
                danh_sach_mat_hang LONGTEXT,
                tong_tien_hang DOUBLE,
                thue_suat_vat VARCHAR(50),
                tien_thue_vat DOUBLE,
                tong_thanh_toan DOUBLE,
                accounting_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                payment_status VARCHAR(20) NOT NULL DEFAULT 'unpaid',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        columns = {column["name"] for column in inspect(engine).get_columns("invoices")}
        if "accounting_status" not in columns:
            conn.execute(text(
                "ALTER TABLE invoices ADD COLUMN accounting_status "
                "VARCHAR(20) NOT NULL DEFAULT 'pending'"
            ))
        if "payment_status" not in columns:
            conn.execute(text(
                "ALTER TABLE invoices ADD COLUMN payment_status "
                "VARCHAR(20) NOT NULL DEFAULT 'unpaid'"
            ))
        if "so_hoa_don" not in columns:
            conn.execute(text(
                "ALTER TABLE invoices ADD COLUMN so_hoa_don VARCHAR(100)"
            ))
        if "source_hash" not in columns:
            conn.execute(text(
                "ALTER TABLE invoices ADD COLUMN source_hash VARCHAR(64)"
            ))


def _ensure_jobs_table(engine) -> None:
    id_column = _id_column(engine)
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS processing_jobs (
                {id_column},
                file_name VARCHAR(500),
                source_image VARCHAR(500),
                source_hash VARCHAR(64),
                status VARCHAR(20) DEFAULT 'processing',
                error_message TEXT,
                error_reason VARCHAR(255),
                invoice_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        columns = {column["name"] for column in inspect(engine).get_columns("processing_jobs")}
        if "source_hash" not in columns:
            conn.execute(text(
                "ALTER TABLE processing_jobs ADD COLUMN source_hash VARCHAR(64)"
            ))


# ===================== INVOICES (dữ liệu đã xác nhận thành công) =====================

def save_invoice_to_db(invoice: Invoice, source_image: str, source_hash: str = None) -> int:
    from pathlib import Path
    engine = _make_engine()
    _ensure_table(engine)

    source_image_name = Path(source_image).name

    payload = json.dumps(
        [item.model_dump() for item in invoice.danh_sach_mat_hang],
        ensure_ascii=False,
    )

    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO invoices (
                    source_image, source_hash, ma_so_thue_ban, ten_cong_ty_ban, so_hoa_don, ma_so_thue_mua,
                    ten_cong_ty_mua, ngay_lap, danh_sach_mat_hang, tong_tien_hang,
                    thue_suat_vat, tien_thue_vat, tong_thanh_toan, accounting_status
                ) VALUES (
                    :source_image, :source_hash, :ma_so_thue_ban, :ten_cong_ty_ban, :so_hoa_don, :ma_so_thue_mua,
                    :ten_cong_ty_mua, :ngay_lap, :danh_sach_mat_hang, :tong_tien_hang,
                    :thue_suat_vat, :tien_thue_vat, :tong_thanh_toan, 'pending'
                )
            """),
            {
                "source_image": source_image_name,
                "source_hash": source_hash,
                "ma_so_thue_ban": invoice.ma_so_thue_ban,
                "ten_cong_ty_ban": invoice.ten_cong_ty_ban,
                "so_hoa_don": invoice.so_hoa_don,
                "ma_so_thue_mua": invoice.ma_so_thue_mua,
                "ten_cong_ty_mua": invoice.ten_cong_ty_mua,
                "ngay_lap": invoice.ngay_lap,
                "danh_sach_mat_hang": payload,
                "tong_tien_hang": invoice.tong_tien_hang,
                "thue_suat_vat": invoice.thue_suat_vat,
                "tien_thue_vat": invoice.tien_thue_vat,
                "tong_thanh_toan": invoice.tong_thanh_toan,
            },
        )
        return int(result.lastrowid)


def get_processed_image_names() -> set:
    engine = _make_engine()
    _ensure_table(engine)
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT source_image FROM invoices")).fetchall()
    return {row[0] for row in rows if row[0] is not None}


def _get_invoices(accounting_status: str = None) -> list[dict[str, Any]]:
    engine = _make_engine()
    _ensure_table(engine)
    with engine.begin() as conn:
        query = """
            SELECT id, source_image, source_hash, ma_so_thue_ban, ten_cong_ty_ban,
                   so_hoa_don, ma_so_thue_mua, ten_cong_ty_mua, ngay_lap,
                   danh_sach_mat_hang, tong_tien_hang, thue_suat_vat,
                   tien_thue_vat, tong_thanh_toan, accounting_status,
                   payment_status, created_at
            FROM invoices
        """
        params = {}
        if accounting_status is not None:
            query += " WHERE accounting_status = :accounting_status"
            params["accounting_status"] = accounting_status
        query += " ORDER BY created_at DESC"
        rows = conn.execute(text(query), params).mappings().fetchall()
    return [dict(row) for row in rows]


def get_all_invoices() -> list[dict[str, Any]]:
    return _get_invoices()


def get_confirmed_invoices() -> list[dict[str, Any]]:
    return _get_invoices("confirmed")


def update_invoice_data(invoice_id: int, fields: dict[str, Any]) -> None:
    allowed_fields = {
        "ma_so_thue_ban", "ten_cong_ty_ban", "so_hoa_don", "ma_so_thue_mua",
        "ten_cong_ty_mua", "ngay_lap", "danh_sach_mat_hang",
        "tong_tien_hang", "thue_suat_vat", "tien_thue_vat", "tong_thanh_toan",
    }
    if not fields or set(fields) - allowed_fields:
        raise ValueError("Các trường hóa đơn cần cập nhật không hợp lệ.")

    values = dict(fields)
    if "danh_sach_mat_hang" in values and not isinstance(values["danh_sach_mat_hang"], str):
        values["danh_sach_mat_hang"] = json.dumps(values["danh_sach_mat_hang"], ensure_ascii=False)

    assignments = ", ".join(f"{field} = :{field}" for field in values)
    engine = _make_engine()
    _ensure_table(engine)
    with engine.begin() as conn:
        result = conn.execute(
            text(f"UPDATE invoices SET {assignments}, accounting_status = 'pending' WHERE id = :id"),
            {**values, "id": invoice_id},
        )
        if result.rowcount == 0:
            raise ValueError(f"Không tìm thấy hóa đơn #{invoice_id}.")


def set_invoice_accounting_status(invoice_id: int, accounting_status: str) -> None:
    if accounting_status not in {"pending", "confirmed", "rejected"}:
        raise ValueError("Trạng thái duyệt hóa đơn không hợp lệ.")

    engine = _make_engine()
    _ensure_table(engine)
    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE invoices SET accounting_status = :status WHERE id = :id"),
            {"status": accounting_status, "id": invoice_id},
        )
        if result.rowcount == 0:
            raise ValueError(f"Không tìm thấy hóa đơn #{invoice_id}.")


def set_invoice_payment_status(invoice_id: int, payment_status: str) -> None:
    if payment_status not in {"paid", "unpaid"}:
        raise ValueError("Trạng thái thanh toán không hợp lệ.")

    engine = _make_engine()
    _ensure_table(engine)
    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE invoices SET payment_status = :status WHERE id = :id"),
            {"status": payment_status, "id": invoice_id},
        )
        if result.rowcount == 0:
            raise ValueError(f"Không tìm thấy hóa đơn #{invoice_id}.")


# ===================== PROCESSING JOBS (nhật ký xử lý — bền vững toàn hệ thống) =====================

FRIENDLY_ERROR_RULES = [
    (("503", "unavailable", "overloaded", "high demand"),
     "Mô hình AI (Gemini) đang quá tải do nhu cầu sử dụng cao, hệ thống đã tự thử lại nhưng chưa thành công"),
    (("timeout", "timed out"),
     "Hết thời gian chờ phản hồi, có thể do kết nối mạng chậm"),
    (("validationerror", "validate"),
     "Dữ liệu AI trả về không đúng định dạng mong đợi"),
    (("poppler", "pdfinfo"),
     "Lỗi khi chuyển đổi file PDF sang ảnh"),
    (("không đọc được ảnh", "filenotfound"),
     "Không đọc được file ảnh/PDF đã tải lên"),
]


def get_friendly_error_reason(error_message: str) -> str:
    """Chuyển traceback kỹ thuật thành lý do ngắn gọn, dễ hiểu cho người dùng cuối."""
    lowered = (error_message or "").lower()
    for keywords, friendly in FRIENDLY_ERROR_RULES:
        if any(k in lowered for k in keywords):
            return friendly
    return "Lỗi không xác định trong quá trình xử lý, xem chi tiết kỹ thuật bên dưới"


def create_job(file_name: str, source_image: str = None, source_hash: str = None) -> int:
    """Tạo 1 bản ghi job trạng thái 'processing' NGAY KHI bắt đầu xử lý."""
    engine = _make_engine()
    _ensure_jobs_table(engine)
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO processing_jobs (file_name, source_image, source_hash, status)
                VALUES (:file_name, :source_image, :source_hash, 'processing')
            """),
            {
                "file_name": file_name,
                "source_image": source_image,
                "source_hash": source_hash,
            },
        )
        return int(result.lastrowid)


def get_upload_duplicate_candidates(source_hash: str, file_name: str) -> list[dict[str, Any]]:
    engine = _make_engine()
    _ensure_table(engine)
    _ensure_jobs_table(engine)
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT j.id AS job_id, j.file_name, j.source_image, j.source_hash,
                       j.status, COALESCE(j.invoice_id, i.id) AS invoice_id,
                       i.so_hoa_don, i.ngay_lap, i.tong_thanh_toan
                FROM processing_jobs j
                LEFT JOIN invoices i ON i.id = COALESCE(
                    j.invoice_id,
                    (
                        SELECT MIN(i2.id)
                        FROM invoices i2
                        WHERE j.source_hash IS NOT NULL
                          AND i2.source_hash = j.source_hash
                    )
                )
                WHERE j.source_hash = :source_hash OR j.file_name = :file_name
                ORDER BY j.created_at DESC
            """),
            {"source_hash": source_hash, "file_name": file_name},
        ).mappings().fetchall()
    return [dict(row) for row in rows]


def mark_job_success(job_id: int, invoice_id: int) -> None:
    engine = _make_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE processing_jobs
                SET status = 'success', invoice_id = :invoice_id, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """),
            {"invoice_id": invoice_id, "id": job_id},
        )


def mark_job_duplicate(job_id: int, invoice_id: int) -> None:
    engine = _make_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE processing_jobs
                SET status = 'duplicate', invoice_id = :invoice_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """),
            {"invoice_id": invoice_id, "id": job_id},
        )


def mark_job_failed(job_id: int, error_message: str) -> None:
    friendly = get_friendly_error_reason(error_message)
    engine = _make_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE processing_jobs
                SET status = 'failed', error_message = :msg, error_reason = :reason,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """),
            {"msg": error_message, "reason": friendly, "id": job_id},
        )


# def cancel_failed_job(job_id: int) -> None:
#     """Mark a failed job as cancelled without deleting its audit history or source file."""
#     engine = _make_engine()
#     _ensure_jobs_table(engine)
#     with engine.begin() as conn:
#         result = conn.execute(
#             text("""
#                 UPDATE processing_jobs
#                 SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
#                 WHERE id = :id AND status = 'failed' AND invoice_id IS NULL
#             """),
#             {"id": job_id},
#         )
#         if result.rowcount == 0:
#             raise ValueError(
#                 f"Không thể hủy hóa đơn #{job_id}: chỉ hủy được job lỗi chưa tạo hóa đơn."
#             )


def get_job_counts() -> dict:
    """Đếm số job theo từng trạng thái — dùng cho sidebar, bền vững toàn hệ thống."""
    engine = _make_engine()
    _ensure_jobs_table(engine)
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT status, COUNT(*) FROM processing_jobs GROUP BY status")
        ).fetchall()
    counts = {
        "processing": 0,
        "success": 0,
        "duplicate": 0,
        "failed": 0,
        "cancelled": 0,
    }
    for status, cnt in rows:
        counts[status] = cnt
    return counts


def get_recent_jobs(limit: int = 5) -> list[dict]:
    engine = _make_engine()
    _ensure_jobs_table(engine)
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT id, file_name, source_image, status, error_message,
                       error_reason, invoice_id, source_hash, created_at
                FROM processing_jobs
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).mappings().fetchall()
    return [dict(row) for row in rows]


def get_all_jobs() -> list[dict]:
    engine = _make_engine()
    _ensure_jobs_table(engine)
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT id, file_name, source_image, status, error_message,
                       error_reason, invoice_id, source_hash, created_at
                FROM processing_jobs
                ORDER BY created_at DESC
            """)
        ).mappings().fetchall()
    return [dict(row) for row in rows]
def get_full_history() -> list[dict]:
    """Kết hợp processing_jobs với invoices -> dùng cho trang Lịch sử hóa đơn,
    hiển thị đúng trạng thái thật (success/processing/failed), không gắn cứng."""
    engine = _make_engine()
    _ensure_table(engine)
    _ensure_jobs_table(engine)

    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT
                j.id AS job_id, j.file_name, j.source_image, j.source_hash,
                CASE
                    WHEN j.status = 'success' AND j.invoice_id IS NULL
                         AND i.id IS NOT NULL AND i.created_at < j.created_at
                        THEN 'duplicate'
                    ELSE j.status
                END AS status,
                j.error_reason, j.error_message, j.created_at,
                i.ma_so_thue_ban, i.ten_cong_ty_ban, i.so_hoa_don,
                i.ngay_lap, i.tong_thanh_toan
            FROM processing_jobs j
            LEFT JOIN invoices i ON i.id = COALESCE(
                j.invoice_id,
                (
                    SELECT MIN(i2.id)
                    FROM invoices i2
                    WHERE j.source_hash IS NOT NULL
                      AND i2.source_hash = j.source_hash
                )
            )
            ORDER BY j.created_at DESC
        """)).mappings().fetchall()
    return [dict(row) for row in rows]


def _duplicate_cleanup_ids(conn) -> tuple[set[int], set[int]]:
    from src.structuring.duplicate_detection import (
        AMOUNT_TOLERANCE,
        _normalize_amount,
        _normalize_date,
        find_duplicate_groups,
    )

    invoices = conn.execute(
        text("""
            SELECT id, source_hash, ma_so_thue_ban, so_hoa_don, ngay_lap,
                   tong_thanh_toan, created_at
            FROM invoices
            ORDER BY created_at, id
        """)
    ).mappings().fetchall()
    invoices = [dict(invoice) for invoice in invoices]

    invoice_ids_to_delete: set[int] = set()
    canonical_invoice_ids: set[int] = set()
    duplicate_invoice_to_canonical_id: dict[int, int] = {}
    for group in find_duplicate_groups(invoices):
        ordered_invoices = sorted(
            group["invoices"],
            key=lambda invoice: (invoice.get("created_at"), invoice["id"]),
        )
        retained_invoices = []
        for invoice in ordered_invoices:
            invoice_date = _normalize_date(invoice.get("ngay_lap"))
            invoice_amount = _normalize_amount(invoice.get("tong_thanh_toan"))
            matching_invoice = next(
                (
                    retained
                    for retained in retained_invoices
                    if invoice_date
                    and invoice_date == _normalize_date(retained.get("ngay_lap"))
                    and invoice_amount is not None
                    and (retained_amount := _normalize_amount(
                        retained.get("tong_thanh_toan")
                    )) is not None
                    and abs(invoice_amount - retained_amount) <= AMOUNT_TOLERANCE
                ),
                None,
            )
            if matching_invoice is None:
                retained_invoices.append(invoice)
                continue
            canonical_invoice_id = matching_invoice["id"]
            canonical_invoice_ids.add(canonical_invoice_id)
            invoice_ids_to_delete.add(invoice["id"])
            duplicate_invoice_to_canonical_id[invoice["id"]] = canonical_invoice_id

    jobs = conn.execute(
        text("""
            SELECT id, status, invoice_id, source_hash, created_at
            FROM processing_jobs
            WHERE status IN ('success', 'failed', 'duplicate')
        """)
    ).mappings().fetchall()
    invoice_by_id = {invoice["id"]: invoice for invoice in invoices}
    duplicate_hash_to_canonical_id = {}
    for invoice_id in canonical_invoice_ids:
        source_hash = invoice_by_id[invoice_id].get("source_hash")
        if source_hash:
            duplicate_hash_to_canonical_id[source_hash] = invoice_id
    for invoice_id, canonical_invoice_id in duplicate_invoice_to_canonical_id.items():
        source_hash = invoice_by_id[invoice_id].get("source_hash")
        if source_hash:
            duplicate_hash_to_canonical_id[source_hash] = canonical_invoice_id

    job_ids_to_delete: set[int] = set()
    canonical_success_job_preserved: set[int] = set()
    for job in sorted(jobs, key=lambda item: (item.get("created_at"), item["id"])):
        linked_invoice_id = job["invoice_id"]
        if linked_invoice_id in invoice_ids_to_delete:
            job_ids_to_delete.add(job["id"])
            continue
        canonical_invoice_id = linked_invoice_id
        if canonical_invoice_id not in canonical_invoice_ids:
            canonical_invoice_id = duplicate_hash_to_canonical_id.get(job["source_hash"])
        if canonical_invoice_id not in canonical_invoice_ids:
            continue
        if (
            job["status"] == "success"
            and canonical_invoice_id not in canonical_success_job_preserved
        ):
            canonical_success_job_preserved.add(canonical_invoice_id)
        else:
            job_ids_to_delete.add(job["id"])

    return invoice_ids_to_delete, job_ids_to_delete


def get_duplicate_cleanup_preview() -> dict[str, int]:
    engine = _make_engine()
    _ensure_table(engine)
    _ensure_jobs_table(engine)
    with engine.begin() as conn:
        invoice_ids, job_ids = _duplicate_cleanup_ids(conn)
    return {"invoice_count": len(invoice_ids), "job_count": len(job_ids)}


def cleanup_duplicate_invoices() -> dict[str, int]:
    """Delete exact duplicate invoice data and its success/failed history jobs."""
    engine = _make_engine()
    _ensure_table(engine)
    _ensure_jobs_table(engine)
    with engine.begin() as conn:
        invoice_ids, job_ids = _duplicate_cleanup_ids(conn)
        for job_id in job_ids:
            conn.execute(
                text("DELETE FROM processing_jobs WHERE id = :id"),
                {"id": job_id},
            )
        for invoice_id in invoice_ids:
            conn.execute(
                text("DELETE FROM invoices WHERE id = :id"),
                {"id": invoice_id},
            )
    return {"invoice_count": len(invoice_ids), "job_count": len(job_ids)}


def reset_job_to_processing(job_id: int) -> None:
    """Đặt lại 1 job về trạng thái 'processing', xóa lỗi cũ -- dùng khi thử lại."""
    engine = _make_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE processing_jobs
                SET status = 'processing', error_message = NULL, error_reason = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """),
            {"id": job_id},
        )
def delete_selected_history_jobs(job_ids: list[int]) -> dict[str, int]:
    from sqlalchemy import bindparam

    selected_ids = sorted({int(job_id) for job_id in job_ids})
    if not selected_ids:
        return {"job_count": 0, "invoice_count": 0}

    engine = _make_engine()
    _ensure_table(engine)
    _ensure_jobs_table(engine)

    with engine.begin() as conn:
        duplicate_invoice_ids, _ = _duplicate_cleanup_ids(conn)

        selected_jobs = conn.execute(
            text("""
                SELECT id, status, invoice_id, source_hash
                FROM processing_jobs
                WHERE id IN :ids
            """).bindparams(bindparam("ids", expanding=True)),
            {"ids": selected_ids},
        ).mappings().fetchall()

        invoice_hashes = {
            row[0]
            for row in conn.execute(
                text("SELECT source_hash FROM invoices WHERE source_hash IS NOT NULL")
            ).fetchall()
        }

        jobs_to_delete = set()
        invoices_to_delete = set()

        for job in selected_jobs:
            invoice_id = job["invoice_id"]
            is_failed_or_duplicate = job["status"] in {"failed", "duplicate"}
            is_detected_duplicate = (
                job["status"] == "success"
                and (
                    invoice_id in duplicate_invoice_ids
                    or (
                        invoice_id is None
                        and job["source_hash"] in invoice_hashes
                    )
                )
            )

            if not (is_failed_or_duplicate or is_detected_duplicate):
                continue

            jobs_to_delete.add(job["id"])

            if invoice_id in duplicate_invoice_ids:
                invoices_to_delete.add(invoice_id)

        if invoices_to_delete:
            related_jobs = conn.execute(
                text("""
                    SELECT id
                    FROM processing_jobs
                    WHERE invoice_id IN :invoice_ids
                """).bindparams(bindparam("invoice_ids", expanding=True)),
                {"invoice_ids": sorted(invoices_to_delete)},
            ).fetchall()
            jobs_to_delete.update(row[0] for row in related_jobs)

        if jobs_to_delete:
            conn.execute(
                text("""
                    DELETE FROM processing_jobs
                    WHERE id IN :ids
                """).bindparams(bindparam("ids", expanding=True)),
                {"ids": sorted(jobs_to_delete)},
            )

        if invoices_to_delete:
            conn.execute(
                text("""
                    DELETE FROM invoices
                    WHERE id IN :ids
                """).bindparams(bindparam("ids", expanding=True)),
                {"ids": sorted(invoices_to_delete)},
            )

    return {
        "job_count": len(jobs_to_delete),
        "invoice_count": len(invoices_to_delete),
    }

def get_job_by_id(job_id: int) -> dict | None:
    engine = _make_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT * FROM processing_jobs WHERE id = :id"),
            {"id": job_id},
        ).mappings().fetchone()
    return dict(row) if row else None   

def backfill_jobs_from_invoices() -> int:
    """
    Chạy 1 lần: với mỗi hóa đơn đã có trong bảng invoices (từ trước khi có
    processing_jobs), tạo 1 bản ghi job 'success' tương ứng, tránh mất số liệu
    lịch sử khi chuyển sang hệ thống theo dõi job mới.
    Bỏ qua các invoice đã có job liên kết (an toàn khi chạy lại nhiều lần).
    """
    engine = _make_engine()
    _ensure_table(engine)
    _ensure_jobs_table(engine)

    with engine.begin() as conn:
        already_linked = {
            row[0] for row in conn.execute(
                text("SELECT invoice_id FROM processing_jobs WHERE invoice_id IS NOT NULL")
            ).fetchall()
        }

        invoices = conn.execute(
            text("SELECT id, source_image, created_at FROM invoices")
        ).mappings().fetchall()

        inserted = 0
        for inv in invoices:
            if inv["id"] in already_linked:
                continue
            conn.execute(
                text("""
                    INSERT INTO processing_jobs
                        (file_name, source_image, status, invoice_id, created_at, updated_at)
                    VALUES
                        (:file_name, :source_image, 'success', :invoice_id, :created_at, :created_at)
                """),
                {
                    "file_name": inv["source_image"],
                    "source_image": inv["source_image"],
                    "invoice_id": inv["id"],
                    "created_at": inv["created_at"],
                },
            )
            inserted += 1

        return inserted
__all__ = [
    "save_invoice_to_db", "get_processed_image_names", "get_all_invoices",
    "get_confirmed_invoices", "update_invoice_data", "set_invoice_accounting_status",
    "set_invoice_payment_status",
    "create_job", "get_upload_duplicate_candidates", "cancel_failed_job",
    "mark_job_success", "mark_job_duplicate", "mark_job_failed",
    "get_duplicate_cleanup_preview", "cleanup_duplicate_invoices",
    "get_job_counts", "get_recent_jobs", "get_all_jobs", "get_friendly_error_reason",
    "delete_selected_history_jobs",
]