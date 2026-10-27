import json
import hashlib
import hmac
import os
import re
import secrets
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from invoice_parser_config import ADMIN_PASSWORD, ADMIN_USERNAME, DATABASE_URL
from src.structuring.schemas import Invoice

_BOOTSTRAPPED_ADMINS: set[tuple[str, str, str]] = set()
_GMAIL_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@gmail\.com$", re.IGNORECASE)


def _needs_tls(url) -> bool:
    """MySQL trên cloud (TiDB, Aiven...) bắt buộc TLS; MySQL local thì không.
    Có thể ép bằng biến môi trường MYSQL_SSL=true/false."""
    flag = os.getenv("MYSQL_SSL", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    return url.host not in {None, "", "localhost", "127.0.0.1", "::1"}


@lru_cache(maxsize=1)
def _make_engine():
    """Tạo engine MỘT LẦN rồi dùng lại (tránh bắt tay TLS lại ở mỗi truy vấn)."""
    url = make_url(DATABASE_URL)
    backend = url.get_backend_name()
    options: dict[str, Any] = {"pool_pre_ping": True, "pool_recycle": 280}
    if backend == "mysql" and _needs_tls(url):
        import certifi

        options["connect_args"] = {"ssl": {"ca": certifi.where()}}
    elif backend == "sqlite":
        options["connect_args"] = {"check_same_thread": False}
    return create_engine(DATABASE_URL, **options)


def describe_database() -> str:
    """Chuỗi mô tả DB đang dùng (không chứa mật khẩu) để hiển thị/kiểm tra."""
    url = make_url(DATABASE_URL)
    if url.get_backend_name() == "sqlite":
        return f"SQLite ({url.database})"
    return f"{url.get_backend_name()} @ {url.host}:{url.port or ''}/{url.database}"


def _id_column(engine) -> str:
    is_sqlite = engine.url.get_backend_name() == "sqlite"
    if is_sqlite:
        return "id INTEGER PRIMARY KEY AUTOINCREMENT"
    return "id INTEGER NOT NULL AUTO_INCREMENT, PRIMARY KEY (id)"


def _ensure_table(engine, bootstrap_admin: bool = True) -> None:
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
                user_id INTEGER,
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
        if "source_image" not in columns:
            conn.execute(text(
                "ALTER TABLE invoices ADD COLUMN source_image VARCHAR(500)"
            ))
        if "source_hash" not in columns:
            conn.execute(text(
                "ALTER TABLE invoices ADD COLUMN source_hash VARCHAR(64)"
            ))
        if "user_id" not in columns:
            conn.execute(text("ALTER TABLE invoices ADD COLUMN user_id INTEGER"))
    _ensure_auth_table(engine, bootstrap_admin=bootstrap_admin)


def _ensure_jobs_table(engine, bootstrap_admin: bool = True) -> None:
    _ensure_table(engine, bootstrap_admin=bootstrap_admin)
    id_column = _id_column(engine)
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS processing_jobs (
                {id_column},
                file_name VARCHAR(500),
                source_image VARCHAR(500),
                source_hash VARCHAR(64),
                status VARCHAR(20) DEFAULT 'processing',
                invoice_id INTEGER,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        columns = {column["name"] for column in inspect(engine).get_columns("processing_jobs")}
        if "source_hash" not in columns:
            conn.execute(text(
                "ALTER TABLE processing_jobs ADD COLUMN source_hash VARCHAR(64)"
            ))
        if "user_id" not in columns:
            conn.execute(text("ALTER TABLE processing_jobs ADD COLUMN user_id INTEGER"))
        legacy_error_columns = columns.intersection({"error_message", "error_reason"})
        if legacy_error_columns:
            conn.execute(text(
                "UPDATE processing_jobs SET "
                + ", ".join(f"{column} = NULL" for column in sorted(legacy_error_columns))
            ))
    _ensure_auth_table(engine, bootstrap_admin=bootstrap_admin)
    if "invoices" in inspect(engine).get_table_names():
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE processing_jobs
                SET user_id = (
                    SELECT invoices.user_id FROM invoices
                    WHERE invoices.id = processing_jobs.invoice_id
                )
                WHERE user_id IS NULL AND invoice_id IS NOT NULL
            """))


def initialize_database() -> None:
    """Create and migrate the application schema before serving requests."""
    _ensure_jobs_table(_make_engine())


def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"


def _password_matches(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (TypeError, ValueError):
        return False


def _ensure_auth_table(engine, bootstrap_admin: bool = True) -> None:
    id_column = _id_column(engine)
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS users (
                {id_column},
                username VARCHAR(64) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                full_name VARCHAR(255),
                email VARCHAR(255),
                role VARCHAR(20) NOT NULL DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        user_columns = {
            column["name"] for column in inspect(engine).get_columns("users")
        }
        if "full_name" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR(255)"))
        if "email" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255)"))

    if not bootstrap_admin:
        return
    if bool(ADMIN_USERNAME) != bool(ADMIN_PASSWORD):
        raise RuntimeError(
            "Cần cấu hình đồng thời ADMIN_USERNAME và ADMIN_PASSWORD để khởi tạo admin."
        )
    if not ADMIN_USERNAME:
        return

    username = ADMIN_USERNAME.strip()
    if not username:
        raise RuntimeError("ADMIN_USERNAME không được để trống.")
    if len(ADMIN_PASSWORD) < 6:
        raise RuntimeError("ADMIN_PASSWORD cần có ít nhất 6 ký tự.")
    bootstrap_key = (
        str(engine.url),
        username,
        hashlib.sha256(ADMIN_PASSWORD.encode("utf-8")).hexdigest(),
    )
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM users WHERE username = :username"),
            {"username": username},
        ).first()
        if existing:
            admin_id = existing[0]
            if bootstrap_key not in _BOOTSTRAPPED_ADMINS:
                conn.execute(text("""
                    UPDATE users SET password_hash = :password_hash, role = 'admin'
                    WHERE id = :id
                """), {
                    "password_hash": _password_hash(ADMIN_PASSWORD),
                    "id": admin_id,
                })
        else:
            result = conn.execute(text("""
                INSERT INTO users (username, password_hash, role)
                VALUES (:username, :password_hash, 'admin')
            """), {
                "username": username,
                "password_hash": _password_hash(ADMIN_PASSWORD),
            })
            admin_id = result.lastrowid

        tables = set(inspect(engine).get_table_names())
        for table in {"invoices", "processing_jobs"} & tables:
            columns = {
                column["name"] for column in inspect(engine).get_columns(table)
            }
            if "user_id" in columns:
                conn.execute(text(
                    f"UPDATE {table} SET user_id = :admin_id WHERE user_id IS NULL"
                ), {"admin_id": admin_id})
    _BOOTSTRAPPED_ADMINS.add(bootstrap_key)


def register_user(
    username: str,
    password: str,
    full_name: str | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    email_value = email
    email = (email or "").strip().casefold()
    full_name = (full_name or "").strip() or None
    if email_value is not None:
        if not _GMAIL_EMAIL_RE.fullmatch(email):
            raise ValueError("Vui lòng nhập email Gmail hợp lệ (ví dụ: ten@gmail.com).")
        username = email
    else:
        username = (username or "").strip()
        if len(username) < 3 or len(username) > 64:
            raise ValueError("Tên đăng nhập cần có từ 3 đến 64 ký tự.")
        if not all(character.isalnum() or character in "._-" for character in username):
            raise ValueError("Tên đăng nhập chỉ được chứa chữ, số, dấu chấm, gạch dưới hoặc gạch ngang.")
        username = username.casefold()
    if len(password or "") < 6:
        raise ValueError("Mật khẩu cần có ít nhất 6 ký tự.")

    engine = _make_engine()
    _ensure_auth_table(engine)
    try:
        with engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO users (username, password_hash, full_name, email, role)
                VALUES (:username, :password_hash, :full_name, :email, 'user')
            """), {
                "username": username,
                "password_hash": _password_hash(password),
                "full_name": full_name,
                "email": email or None,
            })
            user_id = int(result.lastrowid)
    except IntegrityError as exc:
        raise ValueError("Tên đăng nhập đã được sử dụng.") from exc
    from src.logging_config import log_activity

    log_activity("user_registered", user_id=user_id)
    return {
        "id": user_id,
        "username": username,
        "full_name": full_name,
        "email": email or None,
        "role": "user",
    }


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    engine = _make_engine()
    _ensure_auth_table(engine)
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT id, username, password_hash, role, full_name, email
                FROM users
                WHERE LOWER(username) = :username OR LOWER(email) = :username
            """),
            {"username": (username or "").strip().casefold()},
        ).mappings().first()
    if not row or not _password_matches(password or "", row["password_hash"]):
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "email": row["email"],
        "role": row["role"],
    }


def get_auth_configuration() -> dict[str, bool]:
    return {
        "admin_configured": bool(
            ADMIN_USERNAME and ADMIN_PASSWORD and len(ADMIN_PASSWORD) >= 6
        )
    }


# ===================== INVOICES (dữ liệu đã xác nhận thành công) =====================

def _ownership_filter(user_id: int | None, is_admin: bool, table_alias: str = "") -> tuple[str, dict]:
    if is_admin:
        return "1 = 1", {}
    if user_id is None:
        return "1 = 0", {}
    return f"{table_alias}user_id = :user_id", {"user_id": user_id}


def save_invoice_to_db(
    invoice: Invoice,
    source_image: str,
    source_hash: str = None,
    user_id: int | None = None,
) -> int:
    from pathlib import Path
    engine = _make_engine()
    _ensure_table(engine)

    source_image_name = Path(source_image).as_posix()

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
                    thue_suat_vat, tien_thue_vat, tong_thanh_toan, accounting_status, user_id
                ) VALUES (
                    :source_image, :source_hash, :ma_so_thue_ban, :ten_cong_ty_ban, :so_hoa_don, :ma_so_thue_mua,
                    :ten_cong_ty_mua, :ngay_lap, :danh_sach_mat_hang, :tong_tien_hang,
                    :thue_suat_vat, :tien_thue_vat, :tong_thanh_toan, 'pending', :user_id
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
                "user_id": (
                    user_id if user_id is not None else _configured_admin_user_id(conn)
                ),
            },
        )
        return int(result.lastrowid)


def _configured_admin_user_id(conn) -> int | None:
    if not ADMIN_USERNAME:
        return None
    row = conn.execute(
        text("SELECT id FROM users WHERE username = :username AND role = 'admin'"),
        {"username": ADMIN_USERNAME.strip()},
    ).first()
    return int(row[0]) if row else None


def get_processed_image_names(user_id: int | None = None, is_admin: bool = False) -> set:
    engine = _make_engine()
    _ensure_table(engine)
    ownership, params = _ownership_filter(user_id, is_admin)
    with engine.begin() as conn:
        rows = conn.execute(
            text(f"SELECT source_image FROM invoices WHERE {ownership}"), params
        ).fetchall()
    return {row[0] for row in rows if row[0] is not None}


def _get_invoices(
    accounting_status: str = None,
    user_id: int | None = None,
    is_admin: bool = False,
) -> list[dict[str, Any]]:
    engine = _make_engine()
    _ensure_table(engine)
    ownership, params = _ownership_filter(user_id, is_admin, "invoices.")
    with engine.begin() as conn:
        query = """
            SELECT invoices.id, invoices.source_image, invoices.source_hash,
                   invoices.ma_so_thue_ban, invoices.ten_cong_ty_ban,
                   invoices.so_hoa_don, invoices.ma_so_thue_mua,
                   invoices.ten_cong_ty_mua, invoices.ngay_lap,
                   invoices.danh_sach_mat_hang, invoices.tong_tien_hang,
                   invoices.thue_suat_vat, invoices.tien_thue_vat,
                   invoices.tong_thanh_toan, invoices.accounting_status,
                   invoices.payment_status, invoices.created_at, invoices.user_id,
                   CASE
                       WHEN invoices.created_at IS NULL
                            OR invoices.created_at < uploader.created_at
                           THEN NULL
                       ELSE uploader.username
                   END AS uploader_username,
                   CASE
                       WHEN invoices.created_at IS NULL
                            OR invoices.created_at < uploader.created_at
                           THEN NULL
                       ELSE uploader.full_name
                   END AS uploader_full_name
            FROM invoices
            LEFT JOIN users AS uploader ON uploader.id = invoices.user_id
            WHERE 
        """
        query += ownership
        if accounting_status is not None:
            query += " AND accounting_status = :accounting_status"
            params["accounting_status"] = accounting_status
        query += " ORDER BY invoices.created_at DESC"
        rows = conn.execute(text(query), params).mappings().fetchall()
    return [dict(row) for row in rows]


def get_all_invoices(user_id: int | None = None, is_admin: bool = False) -> list[dict[str, Any]]:
    return _get_invoices(user_id=user_id, is_admin=is_admin)


def get_confirmed_invoices(user_id: int | None = None, is_admin: bool = False) -> list[dict[str, Any]]:
    return _get_invoices("confirmed", user_id=user_id, is_admin=is_admin)


def get_invoice_count(user_id: int | None = None, is_admin: bool = False) -> int:
    engine = _make_engine()
    _ensure_table(engine)
    ownership, params = _ownership_filter(user_id, is_admin)
    with engine.begin() as conn:
        return int(conn.execute(
            text(f"SELECT COUNT(*) FROM invoices WHERE {ownership}"), params
        ).scalar_one())


def set_invoice_source_image(
    invoice_id: int,
    source_image: str,
    user_id: int | None = None,
    is_admin: bool = False,
) -> None:
    if not source_image or not source_image.strip():
        raise ValueError("Đường dẫn ảnh hóa đơn không được để trống.")

    engine = _make_engine()
    _ensure_table(engine)
    ownership, params = _ownership_filter(user_id, is_admin)
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"UPDATE invoices SET source_image = :source_image "
                f"WHERE id = :id AND {ownership}"
            ),
            {"source_image": source_image, "id": invoice_id, **params},
        )
        if result.rowcount == 0:
            raise ValueError(f"Không tìm thấy hóa đơn #{invoice_id} hoặc bạn không có quyền truy cập.")

    from src.logging_config import log_activity

    log_activity(
        "invoice_source_linked",
        user_id=user_id,
        resource_type="invoice",
        resource_id=invoice_id,
    )


def update_invoice_data(
    invoice_id: int,
    fields: dict[str, Any],
    user_id: int | None = None,
    is_admin: bool = False,
) -> None:
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
    status_assignment = ", accounting_status = 'pending'" if is_admin else ""
    engine = _make_engine()
    _ensure_table(engine)
    ownership, params = _ownership_filter(user_id, is_admin)
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"UPDATE invoices SET {assignments}{status_assignment} "
                f"WHERE id = :id AND {ownership} "
                "AND (:is_admin = 1 OR accounting_status = 'pending')"
            ),
            {**values, "id": invoice_id, "is_admin": int(is_admin), **params},
        )
        if result.rowcount == 0:
            raise ValueError(f"Không tìm thấy hóa đơn #{invoice_id} hoặc bạn không có quyền truy cập.")

    from src.logging_config import log_activity

    log_activity(
        "invoice_data_updated",
        user_id=user_id,
        resource_type="invoice",
        resource_id=invoice_id,
    )


def set_invoice_accounting_status(
    invoice_id: int,
    accounting_status: str,
    is_admin: bool = False,
    actor_user_id: int | None = None,
) -> None:
    if not is_admin:
        raise PermissionError("Chỉ quản trị viên mới được đổi trạng thái duyệt hóa đơn.")
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

    from src.logging_config import log_activity

    log_activity(
        "invoice_accounting_status_changed",
        user_id=actor_user_id,
        resource_type="invoice",
        resource_id=invoice_id,
        status=accounting_status,
    )


def set_invoice_payment_status(
    invoice_id: int,
    payment_status: str,
    is_admin: bool = False,
    actor_user_id: int | None = None,
) -> None:
    if not is_admin:
        raise PermissionError("Chỉ quản trị viên mới được đổi trạng thái thanh toán.")
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

    from src.logging_config import log_activity

    log_activity(
        "invoice_payment_status_changed",
        user_id=actor_user_id,
        resource_type="invoice",
        resource_id=invoice_id,
        status=payment_status,
    )


# ===================== PROCESSING JOBS (trạng thái xử lý) =====================

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


def create_job(
    file_name: str,
    source_image: str = None,
    source_hash: str = None,
    user_id: int | None = None,
) -> int:
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
        resolved_user_id = (
            user_id if user_id is not None else _configured_admin_user_id(conn)
        )
        if resolved_user_id is not None:
            conn.execute(
                text("UPDATE processing_jobs SET user_id = :user_id WHERE id = :id"),
                {"user_id": resolved_user_id, "id": result.lastrowid},
            )
        job_id = int(result.lastrowid)
    from src.logging_config import log_activity

    log_activity(
        "invoice_processing_started",
        user_id=resolved_user_id,
        resource_type="processing_job",
        resource_id=job_id,
    )
    return job_id


def get_upload_duplicate_candidates(
    source_hash: str,
    file_name: str,
    user_id: int | None = None,
    is_admin: bool = False,
) -> list[dict[str, Any]]:
    engine = _make_engine()
    _ensure_table(engine)
    _ensure_jobs_table(engine)
    ownership, params = _ownership_filter(user_id, is_admin, "j.")
    with engine.begin() as conn:
        rows = conn.execute(
            text(f"""
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
                          AND (i2.user_id = j.user_id OR :is_admin = 1)
                    )
                ) AND (i.user_id = j.user_id OR :is_admin = 1)
                WHERE (j.source_hash = :source_hash OR j.file_name = :file_name)
                  AND {ownership}
                  AND (
                      j.status IN ('success', 'duplicate')
                      OR j.invoice_id IS NOT NULL
                      OR i.id IS NOT NULL
                  )
                ORDER BY j.created_at DESC
            """),
            {
                "source_hash": source_hash,
                "file_name": file_name,
                "is_admin": int(is_admin),
                **params,
            },
        ).mappings().fetchall()
    return [dict(row) for row in rows]


def mark_job_success(job_id: int, invoice_id: int, user_id: int | None = None) -> None:
    engine = _make_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE processing_jobs
                SET status = 'success', invoice_id = :invoice_id, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND (:user_id IS NULL OR user_id = :user_id)
            """),
            {"invoice_id": invoice_id, "id": job_id, "user_id": user_id},
        )
    if result.rowcount:
        from src.logging_config import log_activity

        log_activity(
            "invoice_processing_completed",
            user_id=user_id,
            resource_type="invoice",
            resource_id=invoice_id,
            status="success",
        )


def mark_job_duplicate(job_id: int, invoice_id: int, user_id: int | None = None) -> None:
    engine = _make_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE processing_jobs
                SET status = 'duplicate', invoice_id = :invoice_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND (:user_id IS NULL OR user_id = :user_id)
            """),
            {"invoice_id": invoice_id, "id": job_id, "user_id": user_id},
        )
    if result.rowcount:
        from src.logging_config import log_activity

        log_activity(
            "invoice_upload_marked_duplicate",
            user_id=user_id,
            resource_type="invoice",
            resource_id=invoice_id,
            status="duplicate",
        )


def mark_job_failed(
    job_id: int, error_message: str, user_id: int | None = None
) -> None:
    from src.logging_config import get_app_logger

    get_app_logger().error("Invoice processing job %s failed: %s", job_id, error_message)
    engine = _make_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE processing_jobs
                SET status = 'failed', updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND (:user_id IS NULL OR user_id = :user_id)
            """),
            {"id": job_id, "user_id": user_id},
        )
    if result.rowcount:
        from src.logging_config import log_activity

        log_activity(
            "invoice_processing_failed",
            user_id=user_id,
            resource_type="processing_job",
            resource_id=job_id,
            status="failed",
        )


def get_job_counts(user_id: int | None = None, is_admin: bool = False) -> dict:
    """Đếm số job theo từng trạng thái trong phạm vi tài khoản."""
    backfill_jobs_from_invoices()
    engine = _make_engine()
    _ensure_jobs_table(engine)
    ownership, params = _ownership_filter(user_id, is_admin)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT status, COUNT(*) FROM processing_jobs "
                f"WHERE {ownership} GROUP BY status"
            ), params
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


def get_recent_jobs(
    limit: int = 5, user_id: int | None = None, is_admin: bool = False
) -> list[dict]:
    engine = _make_engine()
    _ensure_jobs_table(engine)
    ownership, params = _ownership_filter(user_id, is_admin, "processing_jobs.")
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT id, file_name, source_image, status,
                       invoice_id, source_hash, created_at
                FROM processing_jobs
                WHERE {ownership}
                ORDER BY created_at DESC
                LIMIT :limit
            """.format(ownership=ownership)),
            {"limit": limit, **params},
        ).mappings().fetchall()
    return [dict(row) for row in rows]


def get_jobs_by_ids(
    job_ids: list[int], user_id: int | None = None, is_admin: bool = False
) -> list[dict]:
    """Fetch requested jobs that belong to the signed-in account."""
    normalized_ids = sorted({int(job_id) for job_id in job_ids if job_id is not None})
    if not normalized_ids:
        return []

    from sqlalchemy import bindparam

    engine = _make_engine()
    _ensure_jobs_table(engine)
    ownership, params = _ownership_filter(user_id, is_admin, "processing_jobs.")
    query = text("""
        SELECT id, file_name, source_image, status,
               invoice_id, source_hash, created_at
        FROM processing_jobs
        WHERE id IN :ids AND {ownership}
        ORDER BY created_at DESC
    """.format(ownership=ownership)).bindparams(bindparam("ids", expanding=True))
    with engine.begin() as conn:
        rows = conn.execute(query, {"ids": normalized_ids, **params}).mappings().fetchall()
    return [dict(row) for row in rows]


def get_all_jobs(user_id: int | None = None, is_admin: bool = False) -> list[dict]:
    engine = _make_engine()
    _ensure_jobs_table(engine)
    ownership, params = _ownership_filter(user_id, is_admin, "processing_jobs.")
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT id, file_name, source_image, status,
                       invoice_id, source_hash, created_at
                FROM processing_jobs
                WHERE {ownership}
                ORDER BY created_at DESC
            """.format(ownership=ownership)), params
        ).mappings().fetchall()
    return [dict(row) for row in rows]


def get_full_history(user_id: int | None = None, is_admin: bool = False) -> list[dict]:
    """Kết hợp processing_jobs với invoices -> dùng cho trang Lịch sử hóa đơn,
    hiển thị đúng trạng thái thật (success/processing/failed), không gắn cứng."""
    backfill_jobs_from_invoices()
    engine = _make_engine()
    _ensure_table(engine)
    _ensure_jobs_table(engine)
    ownership, params = _ownership_filter(user_id, is_admin, "j.")

    with engine.begin() as conn:
        rows = conn.execute(text(f"""
            SELECT
                j.id AS job_id, j.file_name, j.source_image, j.source_hash,
                CASE
                    WHEN j.status = 'success' AND j.invoice_id IS NULL
                         AND i.id IS NOT NULL AND i.created_at < j.created_at
                        THEN 'duplicate'
                    ELSE j.status
                END AS status,
                j.created_at,
                i.ma_so_thue_ban, i.ten_cong_ty_ban, i.so_hoa_don,
                i.ngay_lap, i.tong_thanh_toan,
                CASE
                    WHEN j.created_at IS NULL OR j.created_at < uploader.created_at
                        THEN NULL
                    ELSE uploader.username
                END AS uploader_username,
                CASE
                    WHEN j.created_at IS NULL OR j.created_at < uploader.created_at
                        THEN NULL
                    ELSE uploader.full_name
                END AS uploader_full_name
            FROM processing_jobs j
            LEFT JOIN users AS uploader ON uploader.id = j.user_id
            LEFT JOIN invoices i ON i.id = COALESCE(
                j.invoice_id,
                (
                    SELECT MIN(i2.id)
                    FROM invoices i2
                    WHERE j.source_hash IS NOT NULL
                      AND i2.source_hash = j.source_hash
                      AND (i2.user_id = j.user_id OR :is_admin = 1)
                )
            ) AND (i.user_id = j.user_id OR :is_admin = 1)
            WHERE {ownership}
            ORDER BY j.created_at DESC
        """), {**params, "is_admin": int(is_admin)}).mappings().fetchall()
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


def get_duplicate_cleanup_preview(is_admin: bool = False) -> dict[str, int]:
    if not is_admin:
        raise PermissionError("Chỉ quản trị viên mới được rà soát/xóa dữ liệu trùng.")
    engine = _make_engine()
    _ensure_table(engine)
    _ensure_jobs_table(engine)
    with engine.begin() as conn:
        invoice_ids, job_ids = _duplicate_cleanup_ids(conn)
    return {"invoice_count": len(invoice_ids), "job_count": len(job_ids)}


def cleanup_duplicate_invoices(is_admin: bool = False) -> dict[str, int]:
    """Delete exact duplicate invoice data and its success/failed history jobs."""
    if not is_admin:
        raise PermissionError("Chỉ quản trị viên mới được xóa dữ liệu trùng.")
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


def reset_job_to_processing(job_id: int, user_id: int | None = None) -> None:
    """Đặt lại 1 job về trạng thái 'processing', xóa lỗi cũ -- dùng khi thử lại."""
    engine = _make_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE processing_jobs
                SET status = 'processing', updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND (:user_id IS NULL OR user_id = :user_id)
            """),
            {"id": job_id, "user_id": user_id},
        )


def delete_selected_history_jobs(
    job_ids: list[int], is_admin: bool = False, user_id: int | None = None
) -> dict[str, int]:
    """Delete selected history rows and unreferenced invoices owned by the caller."""
    if not is_admin and user_id is None:
        raise PermissionError("Cần xác định tài khoản để xóa lịch sử xử lý.")
    from sqlalchemy import bindparam

    selected_ids = sorted({int(job_id) for job_id in job_ids})
    if not selected_ids:
        return {"job_count": 0, "invoice_count": 0}

    engine = _make_engine()
    _ensure_table(engine)
    _ensure_jobs_table(engine)

    with engine.begin() as conn:
        ownership, ownership_params = _ownership_filter(user_id, is_admin, "j.")

        selected_jobs = conn.execute(
            text(f"""
                SELECT j.id, j.status, j.invoice_id
                FROM processing_jobs j
                WHERE j.id IN :ids AND {ownership}
            """).bindparams(bindparam("ids", expanding=True)),
            {
                **ownership_params,
                "ids": selected_ids,
            },
        ).mappings().fetchall()

        if len(selected_jobs) != len(selected_ids):
            raise PermissionError("Một hoặc nhiều hóa đơn không thuộc quyền truy cập của bạn.")
        if any(job["status"] == "processing" for job in selected_jobs):
            raise ValueError("Không thể xóa hóa đơn đang xử lý. Vui lòng thử lại sau.")

        invoice_ids = {
            job["invoice_id"]
            for job in selected_jobs
            if job["status"] == "success" and job["invoice_id"] is not None
        }
        if selected_ids:
            conn.execute(
                text("""
                    DELETE FROM processing_jobs
                    WHERE id IN :ids
                """).bindparams(bindparam("ids", expanding=True)),
                {"ids": selected_ids},
            )

        deleted_invoice_ids = set()
        for invoice_id in invoice_ids:
            invoice_ownership, invoice_params = _ownership_filter(
                user_id, is_admin, "i."
            )
            invoice = conn.execute(
                text(f"""
                    SELECT source_hash
                    FROM invoices i
                    WHERE i.id = :id AND {invoice_ownership}
                """),
                {"id": invoice_id, **invoice_params},
            ).mappings().first()
            if invoice is None:
                continue

            remaining_ownership, remaining_params = _ownership_filter(
                user_id, is_admin, "j."
            )
            remaining_job = conn.execute(
                text(f"""
                    SELECT 1
                    FROM processing_jobs j
                    WHERE (j.invoice_id = :invoice_id
                           OR (j.invoice_id IS NULL AND j.source_hash = :source_hash))
                      AND {remaining_ownership}
                    LIMIT 1
                """),
                {
                    "invoice_id": invoice_id,
                    "source_hash": invoice["source_hash"],
                    **remaining_params,
                },
            ).first()
            if remaining_job is None:
                delete_invoice_ownership, delete_invoice_params = _ownership_filter(
                    user_id, is_admin
                )
                conn.execute(
                    text(f"""
                        DELETE FROM invoices
                        WHERE id = :id AND {delete_invoice_ownership}
                    """),
                    {"id": invoice_id, **delete_invoice_params},
                )
                deleted_invoice_ids.add(invoice_id)

    return {
        "job_count": len(selected_jobs),
        "invoice_count": len(deleted_invoice_ids),
    }

def get_job_by_id(
    job_id: int, user_id: int | None = None, is_admin: bool = False
) -> dict | None:
    engine = _make_engine()
    _ensure_jobs_table(engine)
    ownership, params = _ownership_filter(user_id, is_admin)
    with engine.begin() as conn:
        row = conn.execute(
            text(f"SELECT * FROM processing_jobs WHERE id = :id AND {ownership}"),
            {"id": job_id, **params},
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
            text("SELECT id, source_image, created_at, user_id FROM invoices")
        ).mappings().fetchall()

        inserted = 0
        for inv in invoices:
            if inv["id"] in already_linked:
                continue
            conn.execute(
                text("""
                    INSERT INTO processing_jobs
                        (file_name, source_image, status, invoice_id, user_id, created_at, updated_at)
                    VALUES
                        (:file_name, :source_image, 'success', :invoice_id, :user_id, :created_at, :created_at)
                """),
                {
                    "file_name": inv["source_image"] or f"Hóa đơn cũ #{inv['id']}",
                    "source_image": inv["source_image"],
                    "invoice_id": inv["id"],
                    "user_id": inv["user_id"],
                    "created_at": inv["created_at"],
                },
            )
            inserted += 1

        return inserted
__all__ = [
    "initialize_database", "save_invoice_to_db", "get_processed_image_names", "get_all_invoices",
    "get_confirmed_invoices", "get_invoice_count", "set_invoice_source_image",
    "update_invoice_data", "set_invoice_accounting_status",
    "set_invoice_payment_status",
    "create_job", "get_upload_duplicate_candidates",
    "mark_job_success", "mark_job_duplicate", "mark_job_failed",
    "get_duplicate_cleanup_preview", "cleanup_duplicate_invoices",
    "get_job_counts", "get_recent_jobs", "get_jobs_by_ids", "get_all_jobs",
    "get_friendly_error_reason",
    "delete_selected_history_jobs", "describe_database",
]