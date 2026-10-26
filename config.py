import os
import re
from pathlib import Path
from sqlalchemy.engine import URL
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

        secret_files = st.config.get_option("secrets.files")
        if not any(Path(path).is_file() for path in secret_files):
            return {}
        return dict(st.secrets)
    except FileNotFoundError:
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
LLM_API_CONFIGURED = bool(GEMINI_API_KEYS or XAI_API_KEY or DEEPSEEK_API_KEY)

# --- Account bootstrap ---
ADMIN_USERNAME = _setting("ADMIN_USERNAME")
ADMIN_PASSWORD = _setting("ADMIN_PASSWORD")

# --- Cấu hình OCR ---
OCR_LANG = "vi"
USE_GPU = False  # Đặt True nếu máy có GPU hỗ trợ CUDA

# --- Cấu hình database ---
DB_PATH = OUTPUT_DIR / "invoices.db"

# MYSQL_HOST = _setting("MYSQL_HOST")
# MYSQL_PORT = int(_setting("MYSQL_PORT", "3306"))
# MYSQL_USER = _setting("MYSQL_USER", "root")
# MYSQL_PASSWORD = _setting("MYSQL_PASSWORD", "")
# MYSQL_DATABASE = _setting("MYSQL_DATABASE", "invoice_parser")

MYSQL_HOST = _setting("MYSQL_HOST")
MYSQL_PORT = int(_setting("MYSQL_PORT", "4000"))
MYSQL_USER = _setting("MYSQL_USER", "root")
MYSQL_PASSWORD = _setting("MYSQL_PASSWORD", "")
MYSQL_DATABASE = _setting("MYSQL_DATABASE", "invoice_parser_host")

DATABASE_URL = _setting("DATABASE_URL")
if not DATABASE_URL:
    if MYSQL_HOST:
        DATABASE_URL = URL.create(
            "mysql+pymysql",
            username=MYSQL_USER,
            password=MYSQL_PASSWORD,
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            database=MYSQL_DATABASE,
        ).render_as_string(hide_password=False)
    else:
        # SQLite is convenient locally but is ephemeral on Streamlit Cloud.
        DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

DATABASE_IS_SQLITE = DATABASE_URL.startswith("sqlite:")

# --- Cấu hình đánh giá ---
EVAL_SAMPLE_SIZE = 15  # Số lượng hóa đơn dùng để đánh giá độ chính xác
