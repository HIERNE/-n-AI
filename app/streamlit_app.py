import streamlit as st
st.set_page_config(page_title="InvoiceAI", page_icon="📄", layout="wide")

import hashlib
import html
import sys
from pathlib import Path
from datetime import datetime, timedelta

import config

DATABASE_IS_SQLITE = config.DATABASE_URL.startswith("sqlite:")
LLM_API_CONFIGURED = bool(
    config.GEMINI_API_KEYS or config.XAI_API_KEY or config.DEEPSEEK_API_KEY
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocessing.pdf_converter import pdf_to_images
from src.pipeline import process_invoice_with_job_tracking
from src.storage.db_handler import (
    get_jobs_by_ids, get_job_counts, get_all_invoices, get_confirmed_invoices, create_job,
    get_upload_duplicate_candidates, mark_job_duplicate, mark_job_failed,
)
from app.components.auth import render_account_menu, require_auth

user = require_auth()
USER_ID = int(user["id"])
IS_ADMIN = user["role"] == "admin"


def prepare_image_path(saved_path: Path) -> Path:
    if saved_path.suffix.lower() == ".pdf":
        image_paths = pdf_to_images(saved_path, output_dir=saved_path.parent)
        return Path(image_paths[0])
    return saved_path


def fmt_money(value):
    """Định dạng tiền an toàn — trả về '—' nếu giá trị bị thiếu (None)."""
    return f"{value:,.0f} đ" if value is not None else "—"


def is_stuck(created_at, minutes: int = 2) -> bool:
    """Coi 1 job 'processing' là bị kẹt/gián đoạn nếu đã tạo quá N phút mà chưa xong."""
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.strip().replace("Z", "+00:00"))
        except ValueError:
            return False
    if not isinstance(created_at, datetime):
        return False

    # SQL databases may return either naive or timezone-aware datetimes.
    now = datetime.now(created_at.tzinfo) if created_at.tzinfo else datetime.now()
    return now - created_at > timedelta(minutes=minutes)


css_path = Path(__file__).parent / "style.css"
st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

from app.components.sidebar_nav import render_sidebar
render_sidebar("upload")
render_account_menu()

# --- Header ---
col_title, col_status, col_period = st.columns([3, 1, 1])
with col_title:
    st.title("Tải lên hóa đơn")
    st.caption("Nhập hóa đơn từ PDF, ảnh")
with col_status:
    st.markdown('<div class="status-badge status-done">🟢 Hệ thống hoạt động</div>', unsafe_allow_html=True)
with col_period:
    st.markdown(
        f'<div class="status-badge" style="background:#EEF2FF;color:#4F46E5;">Kỳ: T{datetime.now().month}/{datetime.now().year}</div>',
        unsafe_allow_html=True,
    )

st.write("")

if DATABASE_IS_SQLITE:
    st.warning(
        "Ứng dụng đang dùng SQLite. Trên Streamlit Community Cloud, dữ liệu SQLite "
        "trên ổ đĩa có thể mất khi ứng dụng khởi động lại. Hãy cấu hình DATABASE_URL "
        "trong Secrets để dùng cơ sở dữ liệu bền vững."
    )

if not LLM_API_CONFIGURED:
    st.error(
        "Chưa cấu hình API key cho Gemini, xAI hoặc DeepSeek. "
        "Thêm GEMINI_API_KEY (hoặc API key nhà cung cấp khác) vào Secrets của ứng dụng "
        "Streamlit Cloud để bật xử lý hóa đơn."
    )

# --- Thẻ số liệu tổng quan — đọc trực tiếp từ DB, bền vững toàn hệ thống ---
counts = get_job_counts(user_id=USER_ID, is_admin=IS_ADMIN)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Tổng hóa đơn", len(get_all_invoices(user_id=USER_ID, is_admin=IS_ADMIN)))
c2.metric("Đã xử lý", counts["success"])
c3.metric("Hạch toán", len(get_confirmed_invoices(user_id=USER_ID, is_admin=IS_ADMIN)))
c4.metric("Đang xử lý", counts["processing"])
c5.metric("Lỗi", counts["failed"])

st.write("")

uploaded_files = st.file_uploader(
    "Kéo thả hóa đơn vào đây, hoặc chọn tệp từ máy tính",
    type=["pdf", "png", "jpg", "jpeg"],
    accept_multiple_files=True,
    disabled=not LLM_API_CONFIGURED,
)

if "session_job_ids" not in st.session_state:
    st.session_state["session_job_ids"] = {}  # {tên_file:digest: job_id}
if "duplicate_upload_decisions" not in st.session_state:
    st.session_state["duplicate_upload_decisions"] = {}

for uploaded_file in uploaded_files or []:
    uploaded_bytes = uploaded_file.getvalue()
    source_hash = hashlib.sha256(uploaded_bytes).hexdigest()
    upload_name = Path(uploaded_file.name.replace("\\", "/")).name or "invoice"
    upload_key = f"{upload_name}:{source_hash}"
    if upload_key in st.session_state["session_job_ids"]:
        st.info(f"Tệp **{html.escape(upload_name)}** đã được xử lý trong phiên hiện tại.")
        continue

    duplicate_candidates = get_upload_duplicate_candidates(
        source_hash, upload_name, user_id=USER_ID, is_admin=IS_ADMIN
    )
    duplicate_matches = []
    for candidate in duplicate_candidates:
        is_same_content = candidate.get("source_hash") == source_hash
        if not is_same_content and candidate.get("file_name") == upload_name:
            previous_path = Path(candidate["source_image"]) if candidate.get("source_image") else None
            if previous_path and previous_path.is_file():
                is_same_content = hashlib.sha256(previous_path.read_bytes()).hexdigest() == source_hash
        if is_same_content:
            duplicate_matches.append(candidate)

    if duplicate_matches:
        resolved_duplicate = next(
            (
                match for match in duplicate_matches
                if match.get("invoice_id") is not None
            ),
            None,
        )
        if resolved_duplicate:
            job_id = create_job(
                upload_name,
                source_image=resolved_duplicate.get("source_image"),
                source_hash=source_hash,
                user_id=USER_ID,
            )
            mark_job_duplicate(job_id, resolved_duplicate["invoice_id"], user_id=USER_ID)
            st.session_state["session_job_ids"][upload_key] = job_id
            st.session_state["duplicate_upload_decisions"].pop(upload_key, None)
            st.info(
                f"Đã nhận diện **{html.escape(upload_name)}** trùng nội dung với hóa đơn đã trích xuất. "
                f"Không chạy OCR; lịch sử liên kết dữ liệu hóa đơn #{resolved_duplicate['invoice_id']}."
            )
            continue

        match_labels = ", ".join(
            f"job #{match['job_id']} ({match.get('status')})"
            for match in duplicate_matches
        )
        st.warning(
            f"⚠️ Tệp **{html.escape(upload_name)}** có nội dung giống hóa đơn đã tải lên trước đó "
            f"({match_labels}). Chưa chạy OCR."
        )
        decision = st.session_state["duplicate_upload_decisions"].get(upload_key)
        if decision is None:
            continue_col, skip_col = st.columns(2)
            with continue_col:
                continue_processing = st.button(
                    "Tiếp tục xử lý",
                    type="primary",
                    key=f"continue_duplicate_{upload_key}",
                    use_container_width=True,
                )
            with skip_col:
                skip_processing = st.button(
                    "Bỏ qua hóa đơn này",
                    key=f"skip_duplicate_{upload_key}",
                    use_container_width=True,
                )
            if continue_processing:
                decision = "continue"
                st.session_state["duplicate_upload_decisions"][upload_key] = decision
            elif skip_processing:
                decision = "skip"
                st.session_state["duplicate_upload_decisions"][upload_key] = decision
            else:
                continue

        if decision == "skip":
            st.info(f"Đã bỏ qua **{html.escape(upload_name)}**. OCR không được chạy.")
            continue

    save_dir = Path("data/uploads") / f"user_{USER_ID}"
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / upload_name

    if save_path.exists():
        save_path = save_dir / f"{save_path.stem}_{source_hash[:12]}{save_path.suffix}"
        if save_path.exists() and hashlib.sha256(save_path.read_bytes()).hexdigest() != source_hash:
            save_path = save_dir / f"{save_path.stem}_{source_hash}{save_path.suffix}"
    if not save_path.exists():
        save_path.write_bytes(uploaded_bytes)

    # TẠO JOB NGAY LẬP TỨC — trước khi convert PDF / OCR / gọi Gemini.
    # Dù bị bấm X ngắt ngang ngay sau dòng này, job vẫn đã nằm chắc trong DB,
    # không biến mất khi refresh trang.
    job_id = create_job(
        upload_name,
        source_image=str(save_path),
        source_hash=source_hash,
        user_id=USER_ID,
    )
    st.session_state["session_job_ids"][upload_key] = job_id

    progress = st.status(f"Đang xử lý: {upload_name}", expanded=True)
    try:
        if save_path.suffix.lower() == ".pdf":
            progress.write("📄 Đang chuyển đổi PDF sang ảnh...")
        image_path = prepare_image_path(save_path)

        progress.write("🔍 Đang nhận diện chữ (OCR)...")
        # progress.write("🤖 Đang trích xuất dữ liệu bằng AI...")

        result = process_invoice_with_job_tracking(
            str(image_path),
            file_name=upload_name,
            job_id=job_id,
            source_hash=source_hash,
            user_id=USER_ID,
        )

        if result["status"] == "success":
            extracted_duplicate_matches = result.get("duplicate_matches", [])
            if extracted_duplicate_matches:
                matched_ids = ", ".join(
                    f"#{invoice.get('id')}" for invoice in extracted_duplicate_matches
                )
                progress.write(
                    f"⚠️ Dữ liệu trích xuất trùng hoặc nghi trùng với hóa đơn {matched_ids}. "
                    "Hóa đơn vẫn được lưu để bạn kiểm tra."
                )
            progress.update(
                label=(
                    f"⚠️ Đã xử lý, cần kiểm tra trùng: {upload_name}"
                    if extracted_duplicate_matches or duplicate_matches
                    else f"✔ Đã trích xuất, chờ xác nhận: {upload_name}"
                ),
                state="complete",
                expanded=bool(extracted_duplicate_matches or duplicate_matches),
            )
        else:
            progress.update(label=f"✘ Thất bại: {upload_name}", state="error")

    except Exception as e:
        progress.update(label=f"✘ Thất bại: {upload_name}", state="error")
        mark_job_failed(job_id, error_message=str(e), user_id=USER_ID)
    finally:
        st.session_state["duplicate_upload_decisions"].pop(upload_key, None)

if st.session_state["session_job_ids"]:
    if st.button("🔄 Làm mới / tải thêm hóa đơn khác"):
        st.session_state["session_job_ids"] = {}
        st.rerun()

# --- Hóa đơn gần đây — đọc từ processing_jobs, hiển thị đủ trạng thái + nút thử lại ---
st.write("")
st.markdown("##### 📋 Hóa đơn gần đây")

recent_jobs = get_jobs_by_ids(
    list(st.session_state["session_job_ids"].values()),
    user_id=USER_ID,
    is_admin=IS_ADMIN,
)
unique_recent_jobs = []
seen_file_names = set()
for job in recent_jobs:
    file_name = str(job.get("file_name") or "").strip().casefold()
    unique_key = file_name or f"job:{job['id']}"
    if unique_key not in seen_file_names:
        seen_file_names.add(unique_key)
        unique_recent_jobs.append(job)
recent_jobs = unique_recent_jobs

if not recent_jobs:
    st.info("Phiên này chưa xử lý hóa đơn nào.")
else:
    for job in recent_jobs:
        needs_retry = job["status"] in {"failed", "processing"}

        if needs_retry:
            is_failed = job["status"] == "failed"
            is_interrupted = not is_failed and is_stuck(job["created_at"])
            label = "Lỗi" if is_failed else "Bị gián đoạn" if is_interrupted else "Chờ xử lý"
            default_reason = (
                "Quá trình xử lý bị ngắt giữa chừng (có thể do hủy tải lên)"
                if is_interrupted or is_failed
                else "Hóa đơn đang chờ xử lý. Bạn có thể thử lại nếu lần xử lý trước đã bị hủy."
            )
            reason = default_reason
            icon = "🔴" if is_failed else "🟡"
            badge_class = "status-failed" if is_failed else "status-pending"
            with st.expander(f"{icon} {label}: {job['file_name']}  —  {job['created_at']}"):
                st.markdown(f'<span class="status-badge {badge_class}">{icon} {label}</span>', unsafe_allow_html=True)
                st.markdown(f"**Lý do:** {reason}")
                if st.button("🔄 Thử lại", key=f"retry_{job['id']}"):
                    source_path = Path(job["source_image"]) if job["source_image"] else None
                    if not source_path or not source_path.exists():
                        st.error("Không tìm thấy file gốc, vui lòng tải lên lại.")
                    else:
                        try:
                            with st.spinner("Đang xử lý lại..."):
                                image_path = prepare_image_path(source_path)
                                retry_result = process_invoice_with_job_tracking(
                                    str(image_path), file_name=job["file_name"], job_id=job["id"],
                                    user_id=USER_ID,
                                )
                                if retry_result["status"] == "failed":
                                    st.error("Thử xử lý lại chưa thành công. Chi tiết đã được ghi vào file log.")
                            st.rerun()
                        except Exception as e:
                            mark_job_failed(job["id"], error_message=str(e), user_id=USER_ID)
                            st.error("Thử xử lý lại chưa thành công. Chi tiết đã được ghi vào file log.")
        else:
            status_badge = (
                '<div class="status-badge status-done">🟢 Hoàn tất</div>'
                if job["status"] == "success"
                else '<div class="status-badge status-duplicate">🔁 Trùng hóa đơn</div>'
                if job["status"] == "duplicate"
                else '<div class="status-badge status-pending">🟡 Đang xử lý</div>'
            )
            safe_file_name = html.escape(str(job["file_name"] or ""))
            st.markdown(f"""
            <div class="invoice-card">
                <div style="display:flex; align-items:center; gap:12px;">
                    <span style="font-size:20px;">📄</span>
                    <div>
                        <div class="invoice-card-name">{safe_file_name}</div>
                        <div class="invoice-card-date">{job['created_at']}</div>
                    </div>
                </div>
                {status_badge}
            </div>
            """, unsafe_allow_html=True)
