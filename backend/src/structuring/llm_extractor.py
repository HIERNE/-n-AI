import logging
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from google import genai
from invoice_parser_config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL_NAME,
    GEMINI_API_KEYS,
    GEMINI_MODEL_NAME,
    XAI_API_KEY,
    XAI_MODEL_NAME,
)
from src.structuring.schemas import Invoice

XAI_API_URL = "https://api.x.ai/v1/chat/completions"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
LOGGER = logging.getLogger(__name__)

PROMPT_TEMPLATE = """
Từ đoạn text OCR sau (trích từ hóa đơn GTGT tiếng Việt), hãy trích xuất
thành JSON đúng theo cấu trúc sau, không thêm giải thích, không thêm markdown:

{{
  "ma_so_thue_ban": "...",
  "ten_cong_ty_ban": "...",
  "so_hoa_don": null,
  "ma_so_thue_mua": "...",
  "ten_cong_ty_mua": "...",
  "ngay_lap": "...",
  "danh_sach_mat_hang": [
    {{"ten_hang": "...", "so_luong": 0, "don_gia": 0, "thanh_tien": 0}}
  ],
  "tong_tien_hang": 0,
  "thue_suat_vat": "...",
  "tien_thue_vat": 0,
  "tong_thanh_toan": 0
}}

Nếu không đọc được số hóa đơn trong OCR, hãy dùng null; không tự suy đoán số hóa đơn và số tiền.

QUY TẮC BẮT BUỘC VỀ DẤU TIẾNG VIỆT VÀ CHÍNH TẢ:
1. Bạn phải khôi phục đầy đủ và chính xác 100% dấu tiếng Việt chuẩn ngữ pháp và ngữ cảnh cho:
   - "ten_cong_ty_ban", "ten_cong_ty_mua"
   - Tên từng mặt hàng trong "danh_sach_mat_hang" ("ten_hang")
2. Tuyệt đối KHÔNG giữ lại các từ thiếu dấu hoặc sai dấu do lỗi OCR (ví dụ: 'thé hién' -> 'thể hiện', 'vé sinh' -> 'vệ sinh', 'thiét bi' -> 'thiết bị', 'mau trang tuyét' -> 'màu trắng tuyết', 'chac' -> 'chạc', 'd6' -> 'độ', 'Zäcco' -> 'Rắc co' / 'Zắc co').
   Phải chuẩn hóa thành tiếng Việt có dấu hoàn chỉnh: 'Dây xịt vệ sinh', 'Mặt BS 3 thiết bị - màu trắng tuyết', 'Ba chạc 90 độ CB phun', v.v.
3. Giữ nguyên các mã thông số kỹ thuật, kích thước bằng số/chữ tiếng Anh đi kèm (ví dụ: DN 25-3/4", PN 20, 149385V, D42, E27).
4. Đảm bảo toàn bộ mặt hàng được trích xuất đầy đủ, chính xác số lượng, đơn giá và thành tiền tương ứng.

Lưu ý: Các đoạn "=== TRANG n/t ===" thuộc cùng một hóa đơn nhiều trang. Hãy hợp nhất
thông tin và toàn bộ mặt hàng từ tất cả các trang thành một hóa đơn duy nhất. Bỏ qua
phần đầu trang lặp lại; nếu trang sau tiếp tục bảng hàng hóa thì vẫn phải lấy các dòng đó.
Ưu tiên tổng tiền ở phần tổng kết hóa đơn, không cộng lặp lại các tổng phụ xuất hiện ở nhiều trang.

Text OCR:
{ocr_text}
"""


def _clean_json_string(raw_text: str) -> str:
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not match:
        raise ValueError("Không tìm thấy JSON hợp lệ trong phản hồi của dịch vụ xử lý")
    return match.group(0)


def _generate_xai_content(prompt: str) -> str:
    if not XAI_API_KEY:
        raise RuntimeError("Chưa cấu hình XAI_API_KEY cho nhà cung cấp dự phòng.")

    request_body = json.dumps({
        "model": XAI_MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_completion_tokens": 4096,
    }).encode("utf-8")
    request = Request(
        XAI_API_URL,
        data=request_body,
        headers={
            "Authorization": f"Bearer {XAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"xAI API trả về HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Không thể kết nối tới xAI API: {error.reason}") from error

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("Phản hồi từ xAI API không có nội dung hợp lệ.") from error
    if not isinstance(content, str) or not content.strip():
        raise ValueError("xAI API trả về nội dung rỗng.")
    return content


def _generate_deepseek_content(prompt: str) -> str:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("Chưa cấu hình DEEPSEEK hoặc DEEPSEEK_API_KEY trong file .env.")

    request_body = json.dumps({
        "model": DEEPSEEK_MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 4096,
    }).encode("utf-8")
    request = Request(
        DEEPSEEK_API_URL,
        data=request_body,
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek API trả về HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Không thể kết nối tới DeepSeek API: {error.reason}") from error

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("Phản hồi từ DeepSeek API không có nội dung hợp lệ.") from error
    if not isinstance(content, str) or not content.strip():
        raise ValueError("DeepSeek API trả về nội dung rỗng.")
    return content


def _generate_content(prompt: str) -> str:
    gemini_error = None
    for attempt, api_key in enumerate(GEMINI_API_KEYS, start=1):
        provider_started = time.perf_counter()
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=prompt,
            )
            if not response.text:
                raise ValueError("Gemini trả về nội dung rỗng.")
            LOGGER.info(
                "invoice_pipeline stage=llm_provider provider=gemini attempt=%d status=success duration_seconds=%.2f",
                attempt,
                time.perf_counter() - provider_started,
            )
            return response.text
        except Exception as error:
            gemini_error = error
            LOGGER.warning(
                "invoice_pipeline stage=llm_provider provider=gemini attempt=%d status=error error_type=%s duration_seconds=%.2f",
                attempt,
                type(error).__name__,
                time.perf_counter() - provider_started,
            )

    provider_started = time.perf_counter()
    try:
        content = _generate_xai_content(prompt)
        LOGGER.info(
            "invoice_pipeline stage=llm_provider provider=xai status=success duration_seconds=%.2f",
            time.perf_counter() - provider_started,
        )
        return content
    except Exception as xai_error:
        LOGGER.warning(
            "invoice_pipeline stage=llm_provider provider=xai status=error error_type=%s duration_seconds=%.2f",
            type(xai_error).__name__,
            time.perf_counter() - provider_started,
        )
        provider_started = time.perf_counter()
        try:
            content = _generate_deepseek_content(prompt)
            LOGGER.info(
                "invoice_pipeline stage=llm_provider provider=deepseek status=success duration_seconds=%.2f",
                time.perf_counter() - provider_started,
            )
            return content
        except Exception as deepseek_error:
            LOGGER.warning(
                "invoice_pipeline stage=llm_provider provider=deepseek status=error error_type=%s duration_seconds=%.2f",
                type(deepseek_error).__name__,
                time.perf_counter() - provider_started,
            )
            errors = (
                f"Lỗi Gemini: {gemini_error}. "
                f"Lỗi xAI: {xai_error}. "
                f"Lỗi DeepSeek: {deepseek_error}"
            )
            if gemini_error is None:
                raise RuntimeError(
                    f"Không gọi được xAI hoặc DeepSeek API. {errors}"
                ) from deepseek_error
            raise RuntimeError(
                "Gemini không khả dụng; xAI và DeepSeek dự phòng cũng thất bại. "
                f"{errors}"
            ) from deepseek_error


def extract_invoice_data(ocr_text: str) -> Invoice:
    prompt = PROMPT_TEMPLATE.format(ocr_text=ocr_text)

    json_str = _clean_json_string(_generate_content(prompt))
    data_dict = json.loads(json_str)
    invoice = Invoice.model_validate(data_dict)
    return invoice


if __name__ == "__main__":
    from src.ocr.ocr_pipeline import run_ocr

    sample_image = "data/raw/0402130721-1C26MDN-0000052_page1.jpg"
    ocr_results = run_ocr(sample_image)
    ocr_text = "\n".join(r["text"] for r in ocr_results)

    result = extract_invoice_data(ocr_text)
    print(result.model_dump_json(indent=2))
