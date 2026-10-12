import sys
from pathlib import Path

# Tự động thêm thư mục gốc dự án vào sys.path, bất kể đang chạy từ đâu
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # lùi 2 cấp: preprocessing -> src -> gốc
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pdf2image import convert_from_path
from config import RAW_DIR  # giờ chắc chắn lấy đúng file config.py của bạn, không lấy nhầm package pip
def pdf_to_images(pdf_path: Path, output_dir: Path = RAW_DIR):
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    if not pdf_path.exists():
        raise FileNotFoundError(f"Không tồn tại: {pdf_path.resolve()}")

    pages = convert_from_path(str(pdf_path), dpi=200)  # giảm từ 300 xuống 200
    pdf_name = pdf_path.stem

    saved_paths = []
    for i, page in enumerate(pages):
        img_path = output_dir / f"{pdf_name}_page{i+1}.jpg"
        page.save(img_path, "JPEG")
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