import sys
from pathlib import Path

# Tự động thêm thư mục gốc dự án vào sys.path, bất kể đang chạy từ đâu
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # lùi 2 cấp: preprocessing -> src -> gốc
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import fitz  # PyMuPDF: PDF rendering without a system Poppler installation.
from invoice_parser_config import RAW_DIR


def pdf_to_images(pdf_path: Path, output_dir: Path = RAW_DIR):
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    if not pdf_path.exists():
        raise FileNotFoundError(f"Không tồn tại: {pdf_path.resolve()}")

    pdf_name = pdf_path.stem
    saved_paths = []
    output_dir.mkdir(parents=True, exist_ok=True)

    # pdf2image requires Poppler (pdfinfo/pdftoppm) to be installed separately
    # on every machine running the web app. PyMuPDF is already a Python
    # dependency, so render locally without relying on a host-specific PATH.
    with fitz.open(pdf_path) as document:
        if document.needs_pass:
            raise ValueError("PDF được bảo vệ bằng mật khẩu, không thể đọc.")
        if document.page_count == 0:
            raise ValueError("PDF không có trang nào để xử lý.")

        scale = 200 / 72  # preserve the previous 200 DPI output resolution
        matrix = fitz.Matrix(scale, scale)
        for i, page in enumerate(document):
            img_path = output_dir / f"{pdf_name}_page{i + 1}.jpg"
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            pixmap.save(str(img_path), jpg_quality=90)
            saved_paths.append(str(img_path))

    return saved_paths


def find_pdf_files(folder_path: Path = RAW_DIR):
    folder_path = Path(folder_path)
    if not folder_path.exists():
        raise FileNotFoundError(f"Thư mục không tồn tại: {folder_path.resolve()}")
    return [f for f in folder_path.iterdir() if f.suffix.lower() == ".pdf"]


if __name__ == "__main__":
    print(f"Đang quét thư mục: {RAW_DIR.resolve()}")

    all_files = list(RAW_DIR.iterdir())
    print(f"Tổng số file/thư mục con tìm thấy: {len(all_files)}")
    for f in all_files:
        print(f"  - {f.name}")

    pdf_files = find_pdf_files(RAW_DIR)
    print(f"\nTìm thấy {len(pdf_files)} file PDF")

    for pdf_file in pdf_files:
        print(f"\nĐang xử lý: {pdf_file.name}")
        try:
            paths = pdf_to_images(pdf_file)
            print(f"  -> Đã tạo: {paths}")
        except Exception as e:
            print(f"  -> LỖI: {e}")
