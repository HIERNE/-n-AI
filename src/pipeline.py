import sys
import glob
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from invoice_parser_config import RAW_DIR
from src.ocr.ocr_pipeline import run_ocr
from src.structuring.llm_extractor import extract_invoice_data
from src.structuring.duplicate_detection import find_duplicate_groups
from src.storage.db_handler import (
    save_invoice_to_db,
    get_processed_image_names,
    get_all_invoices,
    get_job_by_id,
    create_job,
    mark_job_success,
    mark_job_failed,
    reset_job_to_processing,
)


def extract_invoice(image_path: str):
    """Chỉ trích xuất (OCR + LLM), CHƯA lưu DB."""
    ocr_results = run_ocr(image_path)
    full_text = "\n".join(r["text"] for r in ocr_results)
    invoice = extract_invoice_data(full_text)
    return invoice


def process_invoice(image_path: str, user_id: int | None = None):
    """Pipeline cơ bản: ảnh -> OCR -> text -> LLM -> Invoice -> lưu MySQL. Không theo dõi job."""
    invoice = extract_invoice(image_path)
    record_id = save_invoice_to_db(invoice, source_image=image_path, user_id=user_id)
    return record_id


def process_invoice_with_job_tracking(
    image_path: str,
    file_name: str = None,
    job_id: int = None,
    source_hash: str = None,
    user_id: int | None = None,
):
    """
    Giống process_invoice() nhưng ghi lại trạng thái job bền vững vào DB
    (processing -> success/failed), dùng cho giao diện Streamlit.

    - Nếu job_id chưa truyền vào: tự tạo job mới.
    - Nếu job_id đã có (trường hợp bấm "Thử lại"): reset job đó về 'processing',
      không tạo thêm bản ghi lịch sử trùng lặp.
    """
    file_name = file_name or Path(image_path).name

    if job_id is None:
        job_id = create_job(
            file_name, source_image=image_path, source_hash=source_hash, user_id=user_id
        )
    else:
        existing_job = get_job_by_id(
            job_id, user_id=user_id, is_admin=user_id is None
        )
        if existing_job is None:
            raise ValueError(f"Không tìm thấy job #{job_id} hoặc bạn không có quyền truy cập.")
        if source_hash is None and existing_job:
            source_hash = existing_job.get("source_hash")
        reset_job_to_processing(job_id, user_id=user_id)

    try:
        invoice = extract_invoice(image_path)
        duplicate_candidate = invoice.model_dump()
        duplicate_groups = find_duplicate_groups([
            *get_all_invoices(user_id=user_id, is_admin=user_id is None),
            duplicate_candidate,
        ])
        duplicate_matches = next(
            (
                [
                    existing_invoice
                    for existing_invoice in group["invoices"]
                    if existing_invoice is not duplicate_candidate
                ]
                for group in duplicate_groups
                if duplicate_candidate in group["invoices"]
            ),
            [],
        )
        invoice_id = save_invoice_to_db(
            invoice,
            source_image=image_path,
            source_hash=source_hash,
            user_id=user_id,
        )
        mark_job_success(job_id, invoice_id, user_id=user_id)
        return {
            "status": "success",
            "invoice": invoice,
            "job_id": job_id,
            "duplicate_matches": duplicate_matches,
        }
    except Exception as e:
        mark_job_failed(job_id, error_message=str(e), user_id=user_id)
        return {"status": "failed", "error": str(e), "job_id": job_id}


def run_pipeline_on_folder(folder_path=RAW_DIR, extensions=(".jpg", ".jpeg", ".png")):
    folder_path = Path(folder_path)
    print(f"Đang quét thư mục: {folder_path.resolve()}")

    if not folder_path.exists():
        print(f"CẢNH BÁO: Thư mục không tồn tại: {folder_path.resolve()}")
        return []

    image_paths = []
    for ext in extensions:
        image_paths.extend(glob.glob(str(folder_path / f"*{ext}")))

    already_processed = get_processed_image_names(is_admin=True)
    new_images = [p for p in image_paths if Path(p).name not in already_processed]

    print(f"Tổng số ảnh khớp định dạng: {len(image_paths)}")
    print(f"Đã xử lý từ trước (bỏ qua): {len(image_paths) - len(new_images)}")
    print(f"Ảnh mới cần xử lý: {len(new_images)}")

    if not new_images:
        print("Không có ảnh mới nào cần xử lý.")
        return []

    results = []
    for img_path in new_images:
        try:
            record_id = process_invoice(img_path)
            results.append({"image": img_path, "status": "success", "db_id": record_id, "error": None})
        except Exception:
            error_detail = traceback.format_exc()
            results.append({"image": img_path, "status": "failed", "db_id": None, "error": error_detail})

    return results


if __name__ == "__main__":
    results = run_pipeline_on_folder()

    if results:
        print("\n===== TỔNG KẾT =====")
        for r in results:
            icon = "✔" if r["status"] == "success" else "✘"
            print(f"{icon} {r['image']} -> {r['status']}")

        failed_results = [r for r in results if r["status"] == "failed"]
        if failed_results:
            print(f"\n===== CHI TIẾT {len(failed_results)} LỖI =====")
            for r in failed_results:
                print(f"\n--- {r['image']} ---")
                print(r["error"])