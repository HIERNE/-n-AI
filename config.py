import os
import re
from pathlib import Path
from dotenv import find_dotenv, load_dotenv
from dotenv.main import DotEnv

_dotenv_path = find_dotenv()
_dotenv_api_keys = []
if _dotenv_path:
    _dotenv_api_keys = [
        value.strip()
        for name, value in DotEnv(_dotenv_path, encoding="utf-8").parse()
        if name == "GEMINI_API_KEY" and value and value.strip()
    ]
load_dotenv(_dotenv_path or None)

# --- Đường dẫn gốc dự án ---
BASE_DIR = Path(__file__).resolve().parent

# --- Đường dẫn dữ liệu ---
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
GROUND_TRUTH_DIR = DATA_DIR / "ground_truth"
OUTPUT_DIR = DATA_DIR / "outputs"

# Tự động tạo thư mục nếu chưa tồn tại
for d in [RAW_DIR, PROCESSED_DIR, GROUND_TRUTH_DIR, OUTPUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# --- API Key ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Chưa cấu hình GEMINI_API_KEY trong file .env")

_numbered_api_keys = sorted(
    (
        (int(match.group(1)), value.strip())
        for name, value in os.environ.items()
        if (match := re.fullmatch(r"GEMINI_API_KEY_(\d+)", name)) and value.strip()
    ),
    key=lambda item: item[0],
)
_configured_api_keys = [GEMINI_API_KEY, *_dotenv_api_keys]
_configured_api_keys.extend(value for _, value in _numbered_api_keys)
_configured_api_keys.extend(
    value.strip() for value in os.getenv("GEMINI_API_KEYS", "").split(",")
)
GEMINI_API_KEYS = tuple(dict.fromkeys(key for key in _configured_api_keys if key))

# Gemini 2.0 đã bị gỡ bỏ; dùng model đang được hỗ trợ
GEMINI_MODEL_NAME = "gemini-3.6-flash"
# GEMINI_MODEL_NAME = "gemini-3.5 flash-lite"

# --- xAI fallback ---
XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_MODEL_NAME = os.getenv("XAI_MODEL_NAME", "grok-4.7")

# --- Cấu hình OCR ---
OCR_LANG = "vi"
USE_GPU = False  # Đặt True nếu máy có GPU hỗ trợ CUDA

# --- Cấu hình database ---
DB_PATH = OUTPUT_DIR / "invoices.db"

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "SaH1703!")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "invoice_parser")

DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
)

# --- Cấu hình đánh giá ---
EVAL_SAMPLE_SIZE = 15  # Số lượng hóa đơn dùng để đánh giá độ chính xác
