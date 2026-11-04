from base64 import b64encode
from pathlib import Path

LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "invoiceai_logo.png"


def logo_data_uri() -> str:
    encoded_logo = b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded_logo}"
