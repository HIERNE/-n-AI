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


def _read_streamlit_secrets() -> dict:
    """Read deployment secrets when running on Streamlit Cloud."""
    try:
        import streamlit as st

        return dict(st.secrets)
    except Exception:
        return {}


_streamlit_secrets = _read_streamlit_secrets()


def _setting(name: str, default=None):
    """Prefer environment/.env values, then Streamlit Cloud secrets."""
    value = os.getenv(name)
    if value is not None and str(value).strip():
        return value
    value = _streamlit_secrets.get(name, default)
    return value if value is not None else default

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
GEMINI_API_KEY = _setting("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError(
        "Missing GEMINI_API_KEY. Add it to the local .env file or to "
        "Secrets in your Streamlit Cloud app settings."
    )

_numbered_api_keys = sorted(
    (
        (int(match.group(1)), value.strip())
        for name, value in {**_streamlit_secrets, **os.environ}.items()
        if (match := re.fullmatch(r"GEMINI_API_KEY_(\d+)", name)) and value.strip()
    ),
    key=lambda item: item[0],
)
_configured_api_keys = [GEMINI_API_KEY, *_dotenv_api_keys]
_configured_api_keys.extend(value for _, value in _numbered_api_keys)
_configured_api_keys.extend(
    value.strip() for value in str(_setting("GEMINI_API_KEYS", "")).split(",")
)
GEMINI_API_KEYS = tuple(dict.fromkeys(key for key in _configured_api_keys if key))

# Gemini 2.0 đã bị gỡ bỏ; dùng model đang được hỗ trợ
GEMINI_MODEL_NAME = "gemini-3.6-flash"
# GEMINI_MODEL_NAME = "gemini-3.5 flash-lite"

# --- xAI fallback ---
XAI_API_KEY = _setting("XAI_API_KEY")
XAI_MODEL_NAME = _setting("XAI_MODEL_NAME", "grok-4.7")

# --- DeepSeek fallback ---
DEEPSEEK_API_KEY = _setting("DEEPSEEK_API_KEY") or _setting("DEEPSEEK")
DEEPSEEK_MODEL_NAME = _setting("DEEPSEEK_MODEL_NAME", "deepseek-chat")

# --- Cấu hình OCR ---
OCR_LANG = "vi"
USE_GPU = False  # Đặt True nếu máy có GPU hỗ trợ CUDA

# --- Cấu hình database ---
DB_PATH = OUTPUT_DIR / "invoices.db"

MYSQL_HOST = _setting("MYSQL_HOST")
MYSQL_PORT = _setting("MYSQL_PORT", "3306")
MYSQL_USER = _setting("MYSQL_USER", "root")
MYSQL_PASSWORD = _setting("MYSQL_PASSWORD", "")
MYSQL_DATABASE = _setting("MYSQL_DATABASE", "invoice_parser")

DATABASE_URL = _setting("DATABASE_URL")
if not DATABASE_URL:
    if MYSQL_HOST:
        DATABASE_URL = (
            f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
            f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
        )
    else:
        # A local SQLite database is suitable for a temporary public demo.
        DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

# --- Cấu hình đánh giá ---
EVAL_SAMPLE_SIZE = 15  # Số lượng hóa đơn dùng để đánh giá độ chính xác
