from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

folders = [
    "data/raw", "data/processed", "data/ground_truth", "data/outputs",
    "src/preprocessing", "src/ocr", "src/structuring",
    "src/storage", "src/evaluation",
    "app", "notebooks", "tests", "docs",
]

for folder in folders:
    path = BASE_DIR / folder
    path.mkdir(parents=True, exist_ok=True)
    # Tạo __init__.py cho các package trong src/
    if folder.startswith("src/") or folder == "src":
        (path / "__init__.py").touch()
    # Giữ thư mục data rỗng trên git
    if folder.startswith("data/"):
        (path / ".gitkeep").touch()

(BASE_DIR / "src" / "__init__.py").touch()

print("Đã tạo xong cấu trúc thư mục!")