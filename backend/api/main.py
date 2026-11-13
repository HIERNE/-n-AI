import base64
import asyncio
import hashlib
import hmac
import io
import json
import os
import re
import time
import binascii
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlsplit

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from src.logging_config import log_activity
from src.storage.db_handler import (
    authenticate_user,
    change_user_password,
    cleanup_duplicate_invoices,
    create_job,
    delete_selected_history_jobs,
    get_all_invoices,
    get_confirmed_invoices,
    get_duplicate_cleanup_preview,
    get_full_history,
    get_invoice_count,
    get_job_by_id,
    get_job_counts,
    get_recent_jobs,
    get_upload_duplicate_candidates,
    get_user_by_id,
    initialize_database,
    mark_job_duplicate,
    mark_job_failed,
    mark_job_cancelled,
    reset_job_to_processing,
    register_user,
    set_invoice_accounting_status,
    set_invoice_payment_status,
    set_invoice_source_image,
    update_invoice_data,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIST = PROJECT_ROOT / "frontend" / "dist"
_JOB_PROGRESS: dict[int, dict[str, Any]] = {}
_JOB_PROGRESS_LOCK = Lock()
_OCR_JOB_LOCK = Lock()
COOKIE_NAME = "invoice_pro_session"
SESSION_SECRET = os.getenv("APP_AUTH_SECRET", "")
IS_PRODUCTION = os.getenv("APP_ENV", "").casefold() == "production"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", str(IS_PRODUCTION)).casefold() in {
    "1", "true", "yes", "on"
}
LOCAL_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
CONFIGURED_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in (
        *os.getenv("APP_ALLOWED_ORIGINS", "").split(","),
        os.getenv("RENDER_EXTERNAL_URL", ""),
    )
    if origin.strip()
}
EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$"
)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
INVOICE_FIELDS = {
    "ma_so_thue_ban",
    "ten_cong_ty_ban",
    "so_hoa_don",
    "ma_so_thue_mua",
    "ten_cong_ty_mua",
    "ngay_lap",
    "danh_sach_mat_hang",
    "tong_tien_hang",
    "thue_suat_vat",
    "tien_thue_vat",
    "tong_thanh_toan",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    if IS_PRODUCTION and len(SESSION_SECRET) < 32:
        raise RuntimeError("APP_AUTH_SECRET must be at least 32 characters in production.")
    if IS_PRODUCTION and not (
        os.getenv("DATABASE_URL") or os.getenv("MYSQL_HOST")
    ):
        raise RuntimeError("Configure DATABASE_URL or MYSQL_HOST in production.")
    if not IS_PRODUCTION and not SESSION_SECRET:
        raise RuntimeError(
            "Set APP_AUTH_SECRET before starting the React API, including locally."
        )
    await asyncio.to_thread(initialize_database)
    log_activity("react_api_started")
    yield


app = FastAPI(
    title="Invoice Pro API",
    docs_url=None if IS_PRODUCTION else "/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)
    remember_me: bool = False


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=1024)


class InvoiceUpdateRequest(BaseModel):
    fields: dict[str, Any]


class StatusUpdateRequest(BaseModel):
    status: str


class DeleteHistoryRequest(BaseModel):
    job_ids: list[int] = Field(min_length=1, max_length=500)


class CleanupConfirmationRequest(BaseModel):
    confirm: bool


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=6, max_length=1024)


class SourceImageUpdateRequest(BaseModel):
    source_image: str = Field(min_length=1, max_length=1024)


def _encode_token(user_id: int, lifetime: int) -> str:
    payload = json.dumps(
        {"sub": user_id, "exp": int(time.time()) + lifetime},
        separators=(",", ":"),
    ).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload).rstrip(b"=")
    signature = hmac.new(
        SESSION_SECRET.encode("utf-8"), encoded_payload, hashlib.sha256
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=")
    return f"{encoded_payload.decode('ascii')}.{encoded_signature.decode('ascii')}"


def _decode_token(token: str) -> int | None:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            SESSION_SECRET.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        supplied_signature = base64.urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
        if not hmac.compare_digest(expected_signature, supplied_signature):
            return None

        payload = base64.urlsafe_b64decode(
            encoded_payload + "=" * (-len(encoded_payload) % 4)
        )
        data = json.loads(payload)
        if int(data["exp"]) <= int(time.time()):
            return None
        return int(data["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, binascii.Error):
        return None


def _check_request_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    origin = origin.rstrip("/")
    allowed_origins = CONFIGURED_ORIGINS | LOCAL_ORIGINS
    if origin in allowed_origins:
        return
    if not IS_PRODUCTION:
        parsed_origin = urlsplit(origin)
        if (
            parsed_origin.scheme == "http"
            and parsed_origin.hostname in LOCAL_HOSTS
            and parsed_origin.username is None
            and parsed_origin.password is None
        ):
            return
    raise HTTPException(status_code=403, detail="Nguồn yêu cầu không được phép.")


def _set_session_cookie(response: Response, user_id: int, remember_me: bool) -> None:
    lifetime = 60 * 60 * 24 * 30 if remember_me else 60 * 60 * 12
    response.set_cookie(
        key=COOKIE_NAME,
        value=_encode_token(user_id, lifetime),
        max_age=lifetime if remember_me else None,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _public_user(user: dict) -> dict:
    return {
        "id": int(user["id"]),
        "username": user["username"],
        "full_name": user.get("full_name"),
        "email": user.get("email"),
        "role": user["role"],
    }


def _current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    user_id = _decode_token(token) if token else None
    user = get_user_by_id(user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status_code=401, detail="Vui lòng đăng nhập để tiếp tục.")
    return _public_user(user)


def _require_admin(user: dict) -> None:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Chỉ quản trị viên mới được sử dụng chức năng này.")


def _database_error_response(error: Exception) -> HTTPException:
    if isinstance(error, PermissionError):
        return HTTPException(status_code=403, detail=str(error))
    if isinstance(error, ValueError):
        return HTTPException(status_code=400, detail=str(error))
    return HTTPException(status_code=500, detail="Không thể hoàn tất yêu cầu. Kiểm tra nhật ký máy chủ.")


def _safe_upload_name(file_name: str | None) -> str:
    normalized = (file_name or "invoice").replace("\\", "/").split("/")[-1]
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", normalized).strip("._")
    return safe_name[:180] or "invoice"


def _set_job_progress(
    job_id: int,
    step: int,
    status: str,
    message: str,
    error: str | None = None,
) -> None:
    with _JOB_PROGRESS_LOCK:
        _JOB_PROGRESS[job_id] = {
            "progress_step": step,
            "progress_status": status,
            "progress_message": message,
            "progress_error": error,
        }


def _get_job_progress(job_id: int) -> dict[str, Any] | None:
    with _JOB_PROGRESS_LOCK:
        progress = _JOB_PROGRESS.get(job_id)
        return progress.copy() if progress else None


def _run_invoice_job(
    job_id: int,
    user_id: int,
    file_name: str,
    source_hash: str,
    source_path: Path,
) -> None:
    with _OCR_JOB_LOCK:
        try:
            from src.pipeline import process_invoice_with_job_tracking
            from src.preprocessing.pdf_converter import pdf_to_images

            _set_job_progress(job_id, 2, "processing", "Đang chuyển đổi tệp và nhận dạng OCR.")
            if source_path.suffix.lower() == ".pdf":
                image_paths = pdf_to_images(source_path, output_dir=source_path.parent)
            else:
                image_paths = [str(source_path)]

            # Check if cancelled before running heavy OCR / structuring
            p = _get_job_progress(job_id)
            if p and p.get("progress_status") == "cancelled":
                return

            def _stage_cb(step, message):
                current_p = _get_job_progress(job_id)
                if current_p and current_p.get("progress_status") == "cancelled":
                    raise InterruptedError("Xử lý hóa đơn đã bị người dùng hủy.")
                _set_job_progress(job_id, step, "processing", message)

            result = process_invoice_with_job_tracking(
                image_paths,
                file_name=file_name,
                job_id=job_id,
                source_hash=source_hash,
                user_id=user_id,
                source_image=str(source_path),
                stage_callback=_stage_cb,
            )
            if result["status"] == "success":
                _set_job_progress(job_id, 3, "success", "Đã xử lý hóa đơn hoàn tất.")
            elif result["status"] == "failed":
                progress = _get_job_progress(job_id)
                _set_job_progress(
                    job_id,
                    progress["progress_step"] if progress else 3,
                    "failed",
                    "Không thể xử lý hóa đơn.",
                    result.get("error"),
                )
        except InterruptedError:
            # Job was cancelled intentionally by user
            return
        except Exception as error:
            progress = _get_job_progress(job_id)
            if progress and progress.get("progress_status") == "cancelled":
                return
            _set_job_progress(
                job_id,
                progress["progress_step"] if progress else 2,
                "failed",
                "Không thể xử lý hóa đơn.",
                str(error),
            )
            mark_job_failed(job_id, error_message=str(error), user_id=user_id)


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request, response: Response):
    _check_request_origin(request)
    user = authenticate_user(payload.username, payload.password)
    if user is None:
        log_activity("login_failed")
        raise HTTPException(
            status_code=401,
            detail="Email hoặc mật khẩu không chính xác. Vui lòng kiểm tra lại.",
        )
    _set_session_cookie(response, int(user["id"]), payload.remember_me)
    log_activity("login_succeeded", user_id=int(user["id"]))
    return {"user": _public_user(user)}


@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterRequest, request: Request):
    _check_request_origin(request)
    full_name = payload.full_name.strip()
    email = payload.email.strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="Vui lòng nhập họ và tên của bạn.")
    if not EMAIL_PATTERN.fullmatch(email):
        raise HTTPException(
            status_code=400,
            detail="Vui lòng nhập định dạng email hợp lệ (ví dụ: name@gmail.com).",
        )
    try:
        register_user(email, payload.password, full_name=full_name, email=email)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"message": "Tạo tài khoản thành công. Vui lòng đăng nhập để bắt đầu."}


@app.get("/api/auth/me")
def current_user(request: Request):
    return {"user": _current_user(request)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    _check_request_origin(request)
    user = None
    token = request.cookies.get(COOKIE_NAME)
    user_id = _decode_token(token) if token else None
    if user_id is not None:
        user = get_user_by_id(user_id)
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    if user:
        log_activity("logout", user_id=int(user["id"]))
    return {"message": "Đã đăng xuất."}


@app.post("/api/auth/change-password")
def change_password(payload: ChangePasswordRequest, request: Request):
    _check_request_origin(request)
    user = _current_user(request)
    if not change_user_password(
        user["id"], payload.current_password, payload.new_password
    ):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không chính xác.")
    return {"message": "Đã đổi mật khẩu thành công."}


@app.get("/api/dashboard")
def dashboard(request: Request):
    user = _current_user(request)
    user_id = user["id"]
    is_admin = user["role"] == "admin"
    counts = get_job_counts(user_id=user_id, is_admin=is_admin)
    return {
        "user": user,
        "invoice_count": get_invoice_count(user_id=user_id, is_admin=is_admin),
        "confirmed_count": get_invoice_count(
            user_id=user_id, is_admin=is_admin, accounting_status="confirmed"
        ),
        "job_counts": counts,
        "recent_jobs": get_recent_jobs(limit=8, user_id=user_id, is_admin=is_admin),
    }


@app.get("/api/invoices")
def invoices(request: Request):
    user = _current_user(request)
    return {"invoices": get_all_invoices(user_id=user["id"], is_admin=user["role"] == "admin")}


@app.get("/api/history")
def history(request: Request):
    user = _current_user(request)
    rows = get_full_history(user_id=user["id"], is_admin=user["role"] == "admin")
    for row in rows:
        progress = _get_job_progress(row["job_id"])
        if progress:
            row.update(progress)
        elif row["status"] == "success":
            row["progress_step"] = 3
            row["progress_status"] = "success"
        elif row["status"] == "failed":
            row["progress_status"] = "failed"
            row["progress_error"] = row.get("error_message") or row.get("error_reason") or "Xử lý thất bại"
        elif row["status"] == "cancelled":
            row["progress_status"] = "cancelled"
            row["progress_error"] = row.get("error_message") or row.get("error_reason") or "Đã hủy bởi người dùng"
        elif row["status"] == "processing":
            row["progress_step"] = 2
            row["progress_status"] = "processing"

        # Ensure error details are always propagated
        if row["status"] in {"failed", "cancelled"} and not row.get("progress_error"):
            row["progress_error"] = row.get("error_message") or row.get("error_reason") or "Xử lý thất bại"
    return {"history": rows}


@app.get("/api/jobs")
def jobs(request: Request):
    user = _current_user(request)
    return {
        "jobs": get_recent_jobs(
            limit=100,
            user_id=user["id"],
            is_admin=user["role"] == "admin",
        )
    }


@app.post("/api/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: int, request: Request, background_tasks: BackgroundTasks):
    _check_request_origin(request)
    user = _current_user(request)
    job = get_job_by_id(
        job_id,
        user_id=user["id"],
        is_admin=user["role"] == "admin",
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy công việc.")
    if job["status"] not in {"failed", "processing", "cancelled"}:
        raise HTTPException(status_code=409, detail="Công việc này không cần thử lại.")
    source_path = Path(job["source_image"]) if job.get("source_image") else None
    if source_path is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp nguồn trên máy chủ.")
    if not source_path.is_absolute():
        source_path = PROJECT_ROOT / source_path
    try:
        resolved_source = source_path.resolve(strict=True)
        if user["role"] != "admin":
            try:
                resolved_source.relative_to(
                    (PROJECT_ROOT / "data" / "uploads" / f"user_{user['id']}").resolve()
                )
            except ValueError:
                # Also allow data/raw if available
                resolved_source.relative_to(PROJECT_ROOT / "data")
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp nguồn trên máy chủ.") from error

    reset_job_to_processing(job_id, user_id=user["id"])
    _set_job_progress(job_id, 1, "processing", "Đang chuẩn bị thử lại xử lý hóa đơn.")

    background_tasks.add_task(
        _run_invoice_job,
        job_id,
        user["id"],
        job["file_name"],
        job.get("source_hash") or "",
        resolved_source,
    )
    return {"job_id": job_id, "status": "processing"}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int, request: Request):
    _check_request_origin(request)
    user = _current_user(request)
    job = get_job_by_id(
        job_id,
        user_id=user["id"],
        is_admin=user["role"] == "admin",
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy công việc.")
    if job["status"] != "processing":
        raise HTTPException(status_code=400, detail="Chỉ có thể dừng công việc đang xử lý.")
    mark_job_cancelled(job_id, user_id=user["id"], is_admin=user["role"] == "admin")
    _set_job_progress(
        job_id,
        2,
        "cancelled",
        "Đã dừng xử lý theo yêu cầu của người dùng.",
        "Người dùng đã chủ động dừng xử lý hóa đơn.",
    )
    return {"job_id": job_id, "status": "cancelled", "message": "Đã dừng xử lý hóa đơn thành công."}


@app.post("/api/uploads", status_code=202)
async def upload_invoice(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    _check_request_origin(request)
    user = await asyncio.to_thread(_current_user, request)
    file_name = _safe_upload_name(file.filename)
    extension = Path(file_name).suffix.lower()
    if extension not in UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Chỉ hỗ trợ PDF, PNG, JPG hoặc JPEG.")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Tệp tải lên đang trống.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Tệp vượt quá giới hạn {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    source_hash = hashlib.sha256(content).hexdigest()
    duplicate_candidates = await asyncio.to_thread(
        get_upload_duplicate_candidates,
        source_hash,
        file_name,
        user_id=user["id"],
        is_admin=user["role"] == "admin",
    )
    resolved_duplicate = next(
        (candidate for candidate in duplicate_candidates if candidate.get("invoice_id")),
        None,
    )
    user_upload_dir = PROJECT_ROOT / "data" / "uploads" / f"user_{user['id']}"
    user_upload_dir.mkdir(parents=True, exist_ok=True)
    source_path = user_upload_dir / f"{source_hash[:16]}_{file_name}"
    if not source_path.exists():
        await asyncio.to_thread(source_path.write_bytes, content)

    job_id = await asyncio.to_thread(
        create_job,
        file_name,
        source_image=str(source_path),
        source_hash=source_hash,
        user_id=user["id"],
    )
    _set_job_progress(job_id, 1, "processing", "Đã tải tệp lên an toàn.")
    if resolved_duplicate:
        await asyncio.to_thread(
            mark_job_duplicate,
            job_id,
            resolved_duplicate["invoice_id"],
            user_id=user["id"],
        )
        _set_job_progress(job_id, 1, "duplicate", "Tệp đã trùng với hóa đơn đã xử lý.")
        return {"job_id": job_id, "status": "duplicate"}

    background_tasks.add_task(
        _run_invoice_job,
        job_id,
        user["id"],
        file_name,
        source_hash,
        source_path,
    )
    return {"job_id": job_id, "status": "processing"}


def _find_invoice_file(
    source_image: str | None,
    user_id: int,
    is_admin: bool,
    prefer_preview: bool = False,
) -> Path | None:
    if not source_image or not str(source_image).strip():
        return None

    raw_path = Path(str(source_image).strip().replace("\\", "/"))
    data_root = (PROJECT_ROOT / "data").resolve()
    upload_root = data_root / "uploads"
    user_upload_dir = upload_root / f"user_{user_id}"

    candidates: list[Path] = []

    # 1. Direct path check
    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.append(PROJECT_ROOT / raw_path)
        candidates.append(data_root / raw_path)
        candidates.append(upload_root / raw_path)
        candidates.append(user_upload_dir / raw_path)

    # 2. Filename-based candidates in standard directories
    fname = raw_path.name
    candidates.append(user_upload_dir / fname)
    candidates.append(upload_root / fname)
    candidates.append(data_root / "raw" / fname)
    candidates.append(data_root / "processed" / fname)
    candidates.append(data_root / fname)

    # If it is a PDF and preview image is requested or exists:
    if raw_path.suffix.lower() == ".pdf":
        page1_name = f"{raw_path.stem}_page1.jpg"
        if prefer_preview:
            candidates.insert(0, user_upload_dir / page1_name)
            candidates.insert(1, upload_root / page1_name)
            candidates.insert(2, data_root / "raw" / page1_name)
            candidates.insert(3, data_root / "processed" / page1_name)
        else:
            candidates.append(user_upload_dir / page1_name)
            candidates.append(upload_root / page1_name)
            candidates.append(data_root / "raw" / page1_name)
            candidates.append(data_root / "processed" / page1_name)

    # Search candidates
    for cand in candidates:
        try:
            resolved = cand.resolve(strict=True)
            if resolved.is_file():
                return resolved
        except (OSError, ValueError):
            continue

    # 3. Recursive fallback in data folder by exact filename
    if fname:
        try:
            for p in data_root.rglob(fname):
                if p.is_file():
                    return p.resolve()
        except Exception:
            pass

    # 4. If PDF, recursive fallback for any _page1.jpg
    if raw_path.suffix.lower() == ".pdf":
        try:
            for p in data_root.rglob(f"{raw_path.stem}_page1.jpg"):
                if p.is_file():
                    return p.resolve()
        except Exception:
            pass

    return None


@app.get("/api/files/invoices/{invoice_id}")
def invoice_file(invoice_id: int, request: Request, preview: bool = False):
    user = _current_user(request)
    invoices = get_all_invoices(
        user_id=user["id"],
        is_admin=user["role"] == "admin",
    )
    invoice = next((item for item in invoices if item["id"] == invoice_id), None)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy hóa đơn.")
    if not invoice.get("source_image"):
        raise HTTPException(status_code=404, detail="Hóa đơn chưa được liên kết tệp nguồn.")

    resolved_path = _find_invoice_file(
        invoice.get("source_image"),
        user_id=user["id"],
        is_admin=user["role"] == "admin",
        prefer_preview=preview,
    )
    if resolved_path is None or not resolved_path.is_file():
        fname = Path(invoice["source_image"]).name
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy tệp ảnh/PDF trên máy chủ ({fname}). Bạn có thể chọn liên kết lại tệp.",
        )

    # Path traversal safeguard
    data_root = (PROJECT_ROOT / "data").resolve()
    try:
        resolved_path.relative_to(data_root)
    except ValueError:
        try:
            resolved_path.relative_to(PROJECT_ROOT.resolve())
        except ValueError as err:
            raise HTTPException(status_code=403, detail="Không có quyền truy cập tệp ngoài thư mục dữ liệu.") from err

    suffix = resolved_path.suffix.lower()
    if suffix == ".pdf":
        media_type = "application/pdf"
    elif suffix in (".jpg", ".jpeg"):
        media_type = "image/jpeg"
    elif suffix == ".png":
        media_type = "image/png"
    elif suffix == ".webp":
        media_type = "image/webp"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        resolved_path,
        media_type=media_type,
        headers={"Content-Disposition": "inline"},
    )


@app.get("/api/files/available")
def list_available_files(request: Request):
    user = _current_user(request)
    is_admin = user["role"] == "admin"
    data_dir = (PROJECT_ROOT / "data").resolve()

    folders: list[Path] = []
    if is_admin:
        folders = [data_dir / "uploads", data_dir / "raw", data_dir / "processed"]
    else:
        folders = [data_dir / "uploads" / f"user_{user['id']}", data_dir / "uploads"]

    files = []
    seen = set()
    for folder in folders:
        if not folder.is_dir():
            continue
        for p in folder.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}:
                try:
                    rel = p.relative_to(PROJECT_ROOT).as_posix()
                except ValueError:
                    rel = p.name
                if rel not in seen:
                    seen.add(rel)
                    files.append({
                        "path": rel,
                        "name": p.name,
                        "folder": p.parent.name,
                        "size": p.stat().st_size,
                        "is_pdf": p.suffix.lower() == ".pdf",
                    })
    files.sort(key=lambda x: (x["folder"], x["name"].lower()))
    return {"files": files}


@app.put("/api/invoices/{invoice_id}/source-image")
def update_invoice_source_image(
    invoice_id: int, payload: SourceImageUpdateRequest, request: Request
):
    _check_request_origin(request)
    user = _current_user(request)
    try:
        set_invoice_source_image(
            invoice_id,
            payload.source_image.strip(),
            user_id=user["id"],
            is_admin=user["role"] == "admin",
        )
    except (ValueError, PermissionError, SQLAlchemyError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"message": "Đã lưu liên kết ảnh cho hóa đơn."}


@app.put("/api/invoices/{invoice_id}")
def update_invoice(invoice_id: int, payload: InvoiceUpdateRequest, request: Request):
    _check_request_origin(request)
    user = _current_user(request)
    fields = payload.fields
    if not fields or set(fields) - INVOICE_FIELDS:
        raise HTTPException(status_code=400, detail="Các trường hóa đơn cần cập nhật không hợp lệ.")
    try:
        update_invoice_data(
            invoice_id,
            fields,
            user_id=user["id"],
            is_admin=user["role"] == "admin",
        )
    except (PermissionError, ValueError, SQLAlchemyError) as error:
        raise _database_error_response(error) from error
    return {"message": "Đã lưu dữ liệu hóa đơn."}


@app.put("/api/invoices/{invoice_id}/accounting-status")
def update_accounting_status(
    invoice_id: int, payload: StatusUpdateRequest, request: Request
):
    _check_request_origin(request)
    user = _current_user(request)
    _require_admin(user)
    try:
        set_invoice_accounting_status(
            invoice_id,
            payload.status,
            is_admin=True,
            actor_user_id=user["id"],
        )
    except (PermissionError, ValueError, SQLAlchemyError) as error:
        raise _database_error_response(error) from error
    return {"message": "Đã cập nhật trạng thái duyệt hóa đơn."}


@app.put("/api/invoices/{invoice_id}/payment-status")
def update_payment_status(
    invoice_id: int, payload: StatusUpdateRequest, request: Request
):
    _check_request_origin(request)
    user = _current_user(request)
    _require_admin(user)
    try:
        set_invoice_payment_status(
            invoice_id,
            payload.status,
            is_admin=True,
            actor_user_id=user["id"],
        )
    except (PermissionError, ValueError, SQLAlchemyError) as error:
        raise _database_error_response(error) from error
    return {"message": "Đã cập nhật trạng thái thanh toán."}


@app.get("/api/reports")
def reports(request: Request):
    user = _current_user(request)
    _require_admin(user)
    user_id = user["id"]
    return {
        "invoices": get_all_invoices(user_id=user_id, is_admin=True),
        "recent_jobs": get_recent_jobs(
            limit=100, user_id=user_id, is_admin=True
        ),
    }


@app.get("/api/accounting")
def accounting(request: Request):
    user = _current_user(request)
    _require_admin(user)
    return {"invoices": get_confirmed_invoices(is_admin=True)}


@app.get("/api/accounting/export")
def accounting_export(
    request: Request,
    payment_status: str = "all",
    month: int | None = None,
    year: int | None = None,
):
    from datetime import datetime
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    user = _current_user(request)
    _require_admin(user)
    if payment_status not in {"all", "paid", "unpaid"}:
        raise HTTPException(status_code=400, detail="Bộ lọc thanh toán không hợp lệ.")

    rows = get_confirmed_invoices(is_admin=True)

    def _extract_my(row: dict) -> tuple[int | None, int | None]:
        raw = str(row.get("ngay_lap") or row.get("created_at") or "").strip()
        if not raw:
            return None, None
        m_vn = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", raw)
        if m_vn:
            return int(m_vn.group(2)), int(m_vn.group(3))
        m_iso = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})", raw)
        if m_iso:
            return int(m_iso.group(2)), int(m_iso.group(1))
        return None, None

    if payment_status != "all":
        rows = [
            row for row in rows
            if row.get("payment_status", "unpaid") == payment_status
        ]

    if year is not None and year > 0:
        rows = [r for r in rows if _extract_my(r)[1] == year]

    if month is not None and 1 <= month <= 12:
        rows = [r for r in rows if _extract_my(r)[0] == month]

    period_label = "TẤT CẢ CÁC KỲ"
    if month and year:
        period_label = f"THÁNG {month:02d}/{year}"
        filename = f"hach_toan_Thang_{month:02d}_{year}.xlsx"
    elif year:
        period_label = f"NĂM {year}"
        filename = f"hach_toan_Nam_{year}.xlsx"
    elif month:
        period_label = f"THÁNG {month:02d}"
        filename = f"hach_toan_Thang_{month:02d}.xlsx"
    else:
        filename = "hach_toan_toan_bo.xlsx"

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sổ Hạch Toán"

    # Title Banner Block
    worksheet.merge_cells("A1:K1")
    title_cell = worksheet["A1"]
    title_cell.value = f"SỔ TỔNG HỢP HẠCH TOÁN HÓA ĐƠN — {period_label}"
    title_cell.font = Font(size=14, bold=True, color="0F172A")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    worksheet.row_dimensions[1].height = 36

    worksheet.merge_cells("A2:K2")
    sub_cell = worksheet["A2"]
    sub_cell.value = (
        f"Kỳ báo cáo: {period_label}  |  "
        f"Trạng thái thanh toán: {'Tất cả' if payment_status == 'all' else ('Đã thanh toán' if payment_status == 'paid' else 'Chưa thanh toán')}  |  "
        f"Số lượng: {len(rows)} hóa đơn  |  "
        f"Ngày trích xuất: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    sub_cell.font = Font(size=9.5, italic=True, color="64748B")
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    worksheet.row_dimensions[2].height = 20

    headers = [
        "STT", "Mã HĐ (ID)", "Ngày lập", "Nhà cung cấp (Bên bán)", "Mã số thuế bán",
        "Đơn vị mua", "Số hóa đơn", "Tiền hàng (VNĐ)", "Tiền VAT (VNĐ)",
        "Tổng thanh toán (VNĐ)", "Trạng thái thanh toán",
    ]
    worksheet.append([])  # Row 3 blank spacer
    worksheet.append(headers)  # Row 4
    worksheet.row_dimensions[4].height = 28

    header_font = Font(bold=True, color="FFFFFF", size=10)
    header_fill = PatternFill(fill_type="solid", fgColor="1E293B")
    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    for col_idx in range(1, len(headers) + 1):
        cell = worksheet.cell(row=4, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    total_goods = 0.0
    total_vat = 0.0
    total_payment = 0.0

    for idx, row in enumerate(rows, start=1):
        goods = float(row.get("tong_tien_hang") or 0)
        vat = float(row.get("tien_thue_vat") or 0)
        payment = float(row.get("tong_thanh_toan") or 0)
        total_goods += goods
        total_vat += vat
        total_payment += payment

        p_status = "Đã thanh toán" if row.get("payment_status") == "paid" else "Chưa thanh toán"

        worksheet.append([
            idx,
            f"#{row.get('id', 0):04d}",
            row.get("ngay_lap") or "",
            row.get("ten_cong_ty_ban") or "",
            row.get("ma_so_thue_ban") or "",
            row.get("ten_cong_ty_mua") or "",
            row.get("so_hoa_don") or "",
            goods,
            vat,
            payment,
            p_status,
        ])
        curr_row = worksheet.max_row
        worksheet.row_dimensions[curr_row].height = 22
        for col_idx in range(1, len(headers) + 1):
            cell = worksheet.cell(row=curr_row, column=col_idx)
            cell.border = thin_border
            if col_idx in (8, 9, 10):
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in (1, 2, 3, 5, 7, 11):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    if rows:
        summary_row = worksheet.max_row + 1
        worksheet.cell(row=summary_row, column=1, value="TỔNG CỘNG").font = Font(bold=True, size=10)
        worksheet.cell(row=summary_row, column=8, value=total_goods).number_format = "#,##0"
        worksheet.cell(row=summary_row, column=9, value=total_vat).number_format = "#,##0"
        worksheet.cell(row=summary_row, column=10, value=total_payment).number_format = "#,##0"
        for c in range(1, len(headers) + 1):
            cell = worksheet.cell(row=summary_row, column=c)
            cell.font = Font(bold=True, size=10, color="0F172A")
            cell.fill = PatternFill(fill_type="solid", fgColor="F1F5F9")
            cell.border = thin_border
        worksheet.row_dimensions[summary_row].height = 25

    worksheet.freeze_panes = "A5"
    worksheet.auto_filter.ref = f"A4:K{worksheet.max_row}"

    for col in worksheet.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            if cell.row in (1, 2):
                continue
            if cell.value is not None:
                max_len = max(max_len, len(str(cell.value)))
        worksheet.column_dimensions[col_letter].width = max(max_len + 3, 10)

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/admin/history/cleanup-preview")
def admin_cleanup_preview(request: Request):
    user = _current_user(request)
    _require_admin(user)
    return get_duplicate_cleanup_preview(is_admin=True)


@app.post("/api/admin/history/cleanup")
def admin_cleanup(payload: CleanupConfirmationRequest, request: Request):
    _check_request_origin(request)
    user = _current_user(request)
    _require_admin(user)
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Cần xác nhận trước khi dọn dữ liệu.")
    return cleanup_duplicate_invoices(is_admin=True)


@app.delete("/api/admin/history")
def admin_delete_history(payload: DeleteHistoryRequest, request: Request):
    _check_request_origin(request)
    user = _current_user(request)
    _require_admin(user)
    try:
        return delete_selected_history_jobs(payload.job_ids, is_admin=True)
    except (PermissionError, ValueError, SQLAlchemyError) as error:
        raise _database_error_response(error) from error


if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
