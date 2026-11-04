from src.storage.db_handler import backfill_jobs_from_invoices

count = backfill_jobs_from_invoices()
print(f"Đã đắp lại {count} bản ghi lịch sử vào processing_jobs.")