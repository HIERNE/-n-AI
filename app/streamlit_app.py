import hashlib
import html
import sys
from pathlib import Path
from datetime import datetime, timedelta
import streamlit as st

st.set_page_config(page_title="InvoiceAI", page_icon="📄", layout="wide")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

import invoice_parser_config as config

DATABASE_IS_SQLITE = config.DATABASE_URL.startswith("sqlite:")
LLM_API_CONFIGURED = bool(
    config.GEMINI_API_KEYS or config.XAI_API_KEY or config.DEEPSEEK_API_KEY
)

from app.components.auth import render_account_menu, require_auth
user = require_auth()
USER_ID = int(user["id"])
IS_ADMIN = user["role"] == "admin"

from src.preprocessing.pdf_converter import pdf_to_images
from src.pipeline import process_invoice_with_job_tracking
from src.storage.db_handler import (
    get_jobs_by_ids, get_job_counts, get_all_invoices, get_confirmed_invoices, create_job,
    get_upload_duplicate_candidates, mark_job_duplicate, mark_job_failed,
)

# --- Nạp style.css chuẩn hệ thống ---
css_path = Path(__file__).parent / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

from app.components.sidebar_nav import render_sidebar
render_sidebar("upload")
render_account_menu()

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

    now = datetime.now(created_at.tzinfo) if created_at.tzinfo else datetime.now()
    return now - created_at > timedelta(minutes=minutes)

# --- Header Banner Kỹ thuật (Chuẩn style.css) ---
current_month_year = f"T{datetime.now().month}/{datetime.now().year}"
status_html = ('<span style="color:#22C55E;font-size:12px;">●</span> Hệ thống hoạt động' if LLM_API_CONFIGURED 
               else '<span style="color:#EF4444;font-size:12px;">●</span> Chưa cấu hình API')

st.markdown(f"""
<div class="page-header">
    <div class="page-header-left">
        <div class="page-header-badge"><span>⚡</span> Nền tảng trích xuất thông minh</div>
        <h1>Tải lên hóa đơn</h1>
        <p>Hỗ trợ nhập liệu tự động hóa đơn từ định dạng PDF và hình ảnh (PNG, JPG, JPEG).</p>
    </div>
    <div style="display:flex; align-items:center; gap:12px; z-index:1;">
        <div style="background:rgba(255,255,255,0.15); padding:6px 14px; border-radius:10px; font-size:12.5px; color:#FFFFFF; font-weight:600; border:1px solid rgba(255,255,255,0.2);">
            {status_html}
        </div>
        <div class="header-period-pill">
            <span>Kỳ kế toán</span>
            {current_month_year}
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

if DATABASE_IS_SQLITE:
    st.markdown("""
    <div class="warn-notice">
        <span>⚠️</span> 
        <span>Ứng dụng đang dùng SQLite. Trên Streamlit Community Cloud, dữ liệu trên ổ đĩa có thể mất khi khởi động lại. Hãy cấu hình <code>DATABASE_URL</code> trong Secrets để dùng cơ sở dữ liệu bền vững.</span>
    </div>
    """, unsafe_allow_html=True)

if not LLM_API_CONFIGURED:
    st.markdown("""
    <div class="warn-notice" style="background:#FEE2E2; border-color:#F87171; color:#991B1B;">
        <span>❌</span> 
        <span>Chưa cấu hình API key cho Gemini, xAI hoặc DeepSeek. Thêm <code>GEMINI_API_KEY</code> vào Secrets của ứng dụng Streamlit Cloud để bật xử lý hóa đơn.</span>
    </div>
    """, unsafe_allow_html=True)

# --- Thẻ số liệu tổng quan (Metric Grid chuẩn CSS) ---
counts = get_job_counts(user_id=USER_ID, is_admin=IS_ADMIN)
total_invoices_count = len(get_all_invoices(user_id=USER_ID, is_admin=IS_ADMIN))
success_count = counts["success"]
confirmed_count = len(get_confirmed_invoices(user_id=USER_ID, is_admin=IS_ADMIN))
processing_count = counts["processing"]
failed_count = counts["failed"]

st.markdown(f"""
<div class="metric-grid">
    <div class="metric-card blue" data-icon="📊">
        <div class="metric-label">Tổng hóa đơn</div>
        <div class="metric-value">{total_invoices_count}</div>
        <div class="metric-sub">Đã lưu trữ trong hệ thống</div>
    </div>
    <div class="metric-card green" data-icon="🟢">
        <div class="metric-label">Đã xử lý thành công</div>
        <div class="metric-value">{success_count}</div>
        <div class="metric-sub">Sẵn sàng kiểm tra & hạch toán</div>
    </div>
    <div class="metric-card purple" data-icon="✅">
        <div class="metric-label">Đã hạch toán</div>
        <div class="metric-value">{confirmed_count}</div>
        <div class="metric-sub">Hoàn tất quy trình kế toán</div>
    </div>
    <div class="metric-card orange" data-icon="⏳">
        <div class="metric-label">Đang xử lý / Lỗi</div>
        <div class="metric-value">{processing_count} / {failed_count}</div>
        <div class="metric-sub">Hàng đợi & tiến trình AI</div>
    </div>
</div>
""", unsafe_allow_html=True)

# --- Dropzone Tải lên ---
uploaded_files = st.file_uploader(
    "Kéo thả hóa đơn vào đây, hoặc chọn tệp từ máy tính",
    type=["pdf", "png", "jpg", "jpeg"],
    accept_multiple_files=True,
    disabled=not LLM_API_CONFIGURED,
)

if "session_job_ids" not in st.session_state:
    st.session_state["session_job_ids"] = {} 
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
            st.markdown(f"""
            <div class="info-bar">
                <span>🔁</span> Đã nhận diện <b>{html.escape(upload_name)}</b> trùng nội dung với hóa đơn #{resolved_duplicate['invoice_id']}. Bỏ qua OCR.
            </div>
            """, unsafe_allow_html=True)
            continue

        match_labels = ", ".join(
            f"job #{match['job_id']} ({match.get('status')})"
            for match in duplicate_matches
        )
        st.warning(f"⚠️ Tệp **{html.escape(upload_name)}** có nội dung giống hóa đơn đã tải lên trước đó ({match_labels}).")
        
        decision = st.session_state["duplicate_upload_decisions"].get(upload_key)
        if decision is None:
            c_col, s_col = st.columns(2)
            with c_col:
                continue_processing = st.button("Tiếp tục xử lý", type="primary", key=f"continue_dup_{upload_key}", use_container_width=True)
            with s_col:
                skip_processing = st.button("Bỏ qua hóa đơn này", key=f"skip_dup_{upload_key}", use_container_width=True)
            
            if continue_processing:
                decision = "continue"
                st.session_state["duplicate_upload_decisions"][upload_key] = decision
            elif skip_processing:
                decision = "skip"
                st.session_state["duplicate_upload_decisions"][upload_key] = decision
            else:
                continue

        if decision == "skip":
            st.info(f"Đã bỏ qua **{html.escape(upload_name)}**.")
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
            progress.write("📄 Đang chuyển đổi PDF sang ảnh tài liệu...")
        image_path = prepare_image_path(save_path)

        progress.write("🔍 Đang nhận diện cấu trúc hóa đơn và AI trích xuất dữ liệu...")

        result = process_invoice_with_job_tracking(
            str(image_path),
            file_name=upload_name,
            job_id=job_id,
            source_hash=source_hash,
            user_id=USER_ID,
        )

        if result["status"] == "success":
            progress.update(
                label=f"✔ Hoàn tất trích xuất: {upload_name}",
                state="complete",
                expanded=False,
            )
        else:
            progress.update(label=f"✘ Xử lý thất bại: {upload_name}", state="error")

    except Exception as e:
        progress.update(label=f"✘ Lỗi hệ thống: {upload_name}", state="error")
        mark_job_failed(job_id, error_message=str(e), user_id=USER_ID)
    finally:
        st.session_state["duplicate_upload_decisions"].pop(upload_key, None)

if st.session_state["session_job_ids"]:
    if st.button("🔄 Làm mới phiên làm việc / Tải thêm hóa đơn"):
        st.session_state["session_job_ids"] = {}
        st.rerun()

# --- Hóa đơn gần đây ---
st.markdown("### 📋 Tiến trình hóa đơn gần đây")

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
    st.markdown("""
    <div class="empty-state">
        <div class="empty-state-icon">📄</div>
        <h3>Chưa có hóa đơn nào trong phiên này</h3>
        <p>Hãy tải lên tài liệu hóa đơn phía trên để hệ thống bắt đầu tự động trích xuất thông tin.</p>
    </div>
    """, unsafe_allow_html=True)
else:
    for job in recent_jobs:
        needs_retry = job["status"] in {"failed", "processing"}

        if needs_retry:
            is_failed = job["status"] == "failed"
            is_interrupted = not is_failed and is_stuck(job["created_at"])
            label = "Lỗi xử lý" if is_failed else "Bị gián đoạn" if is_interrupted else "Đang chờ hàng đợi"
            icon = "🔴" if is_failed else "🟡"
            badge_class = "badge-failed" if is_failed else "badge-processing"
            
            with st.expander(f"{icon} [{job['id']}] {job['file_name']} — {job['created_at']}"):
                st.markdown(f'<span class="badge {badge_class}"><span class="badge-dot"></span> {label}</span>', unsafe_allow_html=True)
                st.write(f"**Thời gian:** {job['created_at']}")
                if st.button("🔄 Thử lại trích xuất", key=f"retry_job_{job['id']}", type="primary"):
                    source_path = Path(job["source_image"]) if job["source_image"] else None
                    if not source_path or not source_path.exists():
                        st.error("Không tìm thấy file nguồn gốc trên hệ thống, vui lòng tải lên lại từ đầu.")
                    else:
                        try:
                            with st.spinner("Đang thực hiện lại quy trình OCR & AI..."):
                                image_path = prepare_image_path(source_path)
                                retry_result = process_invoice_with_job_tracking(
                                    str(image_path), file_name=job["file_name"], job_id=job["id"],
                                    user_id=USER_ID,
                                )
                                if retry_result["status"] == "failed":
                                    st.error("Thử lại chưa thành công. Vui lòng kiểm tra lại định dạng tệp tin.")
                                st.rerun()
                        except Exception as e:
                            mark_job_failed(job["id"], error_message=str(e), user_id=USER_ID)
                            st.error(f"Lỗi: {e}")
        else:
            status_map = {
                "success": ("badge-success", "Hoàn tất trích xuất", "🟢"),
                "duplicate": ("badge-duplicate", "Trùng lặp hóa đơn", "🔁")
            }
            b_class, b_text, b_icon = status_map.get(job["status"], ("badge-processing", "Đang xử lý", "🟡"))
            
            st.markdown(f"""
            <div class="tech-card" style="padding: 14px 18px; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <span style="font-size: 22px;">📄</span>
                    <div>
                        <div style="font-weight: 700; color: #0F172A; font-size: 14px;">{html.escape(str(job['file_name']))}</div>
                        <div style="font-size: 11.5px; color: #64748B;">Khởi tạo lúc: {job['created_at']}</div>
                    </div>
                </div>
                <div>
                    <span class="badge {b_class}"><span class="badge-dot"></span> {b_text}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)