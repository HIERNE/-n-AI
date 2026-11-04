from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = Path(__file__).resolve().parent

folders = [
    "src/preprocessing", "src/ocr", "src/structuring",
    "src/storage", "src/evaluation",
    "app", "tests",
]

for folder in folders:
    path = BASE_DIR / folder
    path.mkdir(parents=True, exist_ok=True)
    # Tạo __init__.py cho các package trong src/
    if folder.startswith("src/") or folder == "src":
        (path / "__init__.py").touch()
(BASE_DIR / "src" / "__init__.py").touch()

for folder in ("data/raw", "data/processed", "data/ground_truth", "data/outputs"):
    path = PROJECT_ROOT / folder
    path.mkdir(parents=True, exist_ok=True)
    (path / ".gitkeep").touch()

for folder in ("notebooks", "docs"):
    (PROJECT_ROOT / folder).mkdir(parents=True, exist_ok=True)

print("Đã tạo xong cấu trúc thư mục!")