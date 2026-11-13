import os
import sys
from threading import Lock
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
# OpenBlas in PaddlePaddle Windows binary requires OMP_NUM_THREADS=1 for thread-safety
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1" 

import glob
import re

_ocr_engine = None
_ENGINE_LOCK = Lock()


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        with _ENGINE_LOCK:
            if _ocr_engine is None:
                from paddleocr import PaddleOCR

                _ocr_engine = PaddleOCR(
                    use_angle_cls=False,
                    lang="vi",
                    show_log=False,
                )
    return _ocr_engine


from PIL import Image


def _optimize_image_for_ocr(image_path: str) -> str:
    """Nếu ảnh có độ phân giải quá cao (>2200px), resize tỉ lệ chuẩn để tối ưu tốc độ và giữ nét dấu tiếng Việt."""
    try:
        with Image.open(image_path) as img:
            w, h = img.size
            max_dim = max(w, h)
            if max_dim > 2200:
                scale = 2200.0 / max_dim
                new_size = (int(w * scale), int(h * scale))
                resized = img.resize(new_size, Image.Resampling.LANCZOS)
                p = Path(image_path)
                opt_path = p.parent / f"{p.stem}_fast_ocr.jpg"
                resized.convert("RGB").save(str(opt_path), quality=92)
                return str(opt_path)
    except Exception:
        pass
    return image_path


_VIETNAMESE_PHRASE_RULES = [
    (r"(?i)\bB[aä]n th[eé] hi[eé]n c[uú]a h[oó]a [dđ][oơ]n [dđ]i[eé]n t[uư]r?\b", "Bản thể hiện của hóa đơn điện tử"),
    (r"(?i)\bH[OÓ]A [DĐ][OƠ]N GIA TRI GIA TANG\b", "HÓA ĐƠN GIÁ TRỊ GIA TĂNG"),
    (r"(?i)\bH[OÓ]A [DĐ][OƠ]N B[AÁ]N H[AÀ]NG\b", "HÓA ĐƠN BÁN HÀNG"),
    (r"(?i)\bKy hi[eé]u\b", "Ký hiệu"),
    (r"(?i)\b(S[6oóôò]|So)\s*\(No\.?\)\s*:\s*", "Số (No.): "),
    (r"(?i)\b(S[6oóôò]|So)\s*:\s*", "Số: "),
    (r"(?i)\bM[aã]\s*s[6oóô]\s*thu[eé]\b", "Mã số thuế"),
    (r"(?i)\bM[aã]\s*c[oơ]\s*quan\s*thu[eé]\b", "Mã cơ quan thuế"),
    (r"(?i)\bDo['n\s]*vi\s*b[aá]n\s*h[aà]ng\b", "Đơn vị bán hàng"),
    (r"(?i)\bDo['n\s]*vi\s*mua\s*h[aà]ng\b", "Đơn vị mua hàng"),
    (r"(?i)\bDo['n\s]*vi\s*t[ií]nh\b", "Đơn vị tính"),
    (r"(?i)\bT[eé]n\s*do['n\s]*vi\b", "Tên đơn vị"),
    (r"(?i)\bT[eé]n\s*h[aà]ng\s*h[oó]a[,\s]*d[iị]ch\s*v[uụ]\b", "Tên hàng hóa, dịch vụ"),
    (r"(?i)\bH[oọ]\s*t[eé]n\s*ng[uư][ro]*i\s*mua\s*h[aà]ng\b", "Họ tên người mua hàng"),
    (r"(?i)\bNg[uư][ro]*i\s*b[aá]n\s*h[aà]ng\b", "Người bán hàng"),
    (r"(?i)\bNg[uư][ro]*i\s*mua\s*h[aà]ng\b", "Người mua hàng"),
    (r"(?i)\bS[6oóô]\s*lu[qg]ng\b", "Số lượng"),
    (r"(?i)\bDo['n\s]*gi[aá]\b", "Đơn giá"),
    (r"(?i)\bTh[aà]nh\s*ti[eé]n\b", "Thành tiền"),
    (r"(?i)\bC[oö]ng\s*ti[eé]n\s*h[aà]ng\b", "Cộng tiền hàng"),
    (r"(?i)\bT[oö][nñ]g\s*c[oö]ng\s*ti[eé]n\s*h[aà]ng\b", "Tổng cộng tiền hàng"),
    (r"(?i)\bThu[eé]\s*su[aá]t\s*GTGT\b", "Thuế suất GTGT"),
    (r"(?i)\bTi[eé]n\s*thu[eé]\s*GTGT\b", "Tiền thuế GTGT"),
    (r"(?i)\bT[oö][nñ]g\s*c[oö]ng\s*ti[eé]n\s*thanh\s*to[aá]n\b", "Tổng cộng tiền thanh toán"),
    (r"(?i)\bS[6oóô]\s*ti[eé]n\s*vi[eé]t\s*b[aă]ng\s*ch[uưi]r?\b", "Số tiền viết bằng chữ"),
    (r"(?i)\bH[iì]nh\s*th[uü]c\s*thanh\s*to[aá]n\b", "Hình thức thanh toán"),
    (r"(?i)\bTi[eé]n\s*m[aặ]t\s*/\s*Chuy[eé]n\b", "Tiền mặt / Chuyển khoản"),
    (r"(?i)\bS[6oóô]\s*t[aà]i\s*kho[aä]n\b", "Số tài khoản"),
    (r"(?i)\bNg[aâ]n\s*h[aà]ng\b", "Ngân hàng"),
    (r"(?i)\bTh[aà]nh\s*ph[oó]\b", "Thành phố"),
    (r"(?i)\bPh[uư][oơ]*ng\b", "Phường"),
    (r"\bQuan\b(?=\s+[A-ZĐ])", "Quận"),
    (r"(?i)\bC[oô6]ng\s*Th[uư][oơ]ng\b", "Công Thương"),
    (r"(?i)\bCh[uư]\s*k[yý]\s*[dđ]i[eé]n\s*t[uư]\b", "Chữ ký điện tử"),
    (r"(?i)\bNg[aà]y\s*k[yý]\b", "Ngày ký"),
    (r"(?i)\bDia\s*chi\b", "Địa chỉ"),
    (r"(?i)\bDien\s*thoai\b", "Điện thoại"),
    (r"(?i)\bDay\s*xit\b", "Dây xịt"),
    (r"(?i)\bv[eé]\s*sinh\b", "vệ sinh"),
    (r"(?i)\bthi[eé]t\s*bi\b", "thiết bị"),
    (r"(?i)\bmau\s*trang\s*tuy[eé]t\b", "màu trắng tuyết"),
    (r"(?i)\bba\s*chac\b", "ba chạc"),
    (r"(?i)\bren\s*ngoai\b", "ren ngoài"),
    (r"(?i)\bren\s*trong\b", "ren trong"),
    (r"(?i)\bZ[aä]cco\b", "Rắc co"),
    (r"(?i)\bong\s*dan\b", "ống dẫn"),
    (r"(?i)\bong\s*nuoc\b", "ống nước"),
    (r"(?i)\bthung\s*carton\b", "thùng carton"),
]

_VIETNAMESE_WORD_REPLACEMENTS = {
    "Dén": "Đèn", "dén": "đèn",
    "Cai": "Cái", "cai": "cái",
    "Thué": "Thuế", "thué": "thuế",
    "Tién": "Tiền", "tién": "tiền",
    "cúa": "của", "thé": "thể", "hién": "hiện",
    "dién": "điện", "tur": "tử", "dién tur": "điện tử",
    "nguroi": "người", "Nguroi": "Người",
    "báy": "bảy", "muoi": "mươi", "täm": "tám", "döng": "đồng",
    "triéu": "triệu", "tram": "trăm", "nghin": "nghìn",
    "phó": "phố", "Phó": "Phố",
    "Do'n": "Đơn", "do'n": "đơn",
    "S6": "Số",
    "Dan": "Dẫn", "dan": "dẫn",
    "xä": "xã", "Xä": "Xã",
    "khoän": "khoản", "Khoän": "Khoản",
}


def normalize_vietnamese_ocr(text: str) -> str:
    """
    Khôi phục và chuẩn hóa dấu tiếng Việt cho kết quả nhận dạng PaddleOCR.
    Xử lý siêu tốc (<1ms) các cụm từ hành chính, tiêu đề hóa đơn, chữ số tiền bằng chữ,
    và các từ chuyên ngành hàng hóa bị OCR sai lệch dấu.
    """
    if not text or not isinstance(text, str):
        return text

    result = text
    for pattern, repl in _VIETNAMESE_PHRASE_RULES:
        result = re.sub(pattern, repl, result)

    for word, repl in _VIETNAMESE_WORD_REPLACEMENTS.items():
        result = re.sub(r'\b' + re.escape(word) + r'\b', repl, result)

    # Date pattern: "Ngay ... thang ... nam ..."
    result = re.sub(r"(?i)\bNgay\s*\(date\)\s*", "Ngày (date) ", result)
    result = re.sub(r"(?i)\bthang\s*\(month\)\s*", "tháng (month) ", result)
    result = re.sub(r"(?i)\bnam\s*\(year\)\s*", "năm (year) ", result)

    # Góc độ: "90 d6" hoặc "90 dö" -> "90 độ"
    result = re.sub(r'(\d+)\s*(d6|dö|do)\b', r'\1 độ', result, flags=re.IGNORECASE)

    # Chuyển ký tự nháy đơn OCR: o' -> ơ, u' -> ư
    result = re.sub(r"([oO])'", lambda m: 'ơ' if m.group(1) == 'o' else 'Ơ', result)
    result = re.sub(r"([uU])'", lambda m: 'ư' if m.group(1) == 'u' else 'Ư', result)

    return result


def run_ocr(image_path: str):
    if not Path(image_path).is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh: {image_path}")

    ocr_target = _optimize_image_for_ocr(image_path)
    ocr_engine = _get_ocr_engine()
    result = ocr_engine.ocr(ocr_target, det=True, rec=True, cls=False)
    lines = result[0] if result and result[0] else []

    extracted = []
    for box, (text, _) in lines:
        x_min = int(min(point[0] for point in box))
        y_min = int(min(point[1] for point in box))
        clean_text = normalize_vietnamese_ocr(text)
        extracted.append({"text": clean_text, "box": box, "y": y_min, "x": x_min})

    extracted.sort(key=lambda r: (round(r["y"] / 15), r["x"]))
    return extracted


def run_ocr_on_folder(folder_path: str = "data/raw", extensions=(".jpg", ".jpeg", ".png")):
    image_paths = []
    for ext in extensions:
        image_paths.extend(glob.glob(os.path.join(folder_path, f"*{ext}")))

    print(f"Tìm thấy {len(image_paths)} ảnh trong '{folder_path}'")

    all_results = {}
    for img_path in image_paths:
        print(f"\n=== Đang xử lý: {img_path} ===")
        try:
            results = run_ocr(img_path)
            all_results[img_path] = results
            for r in results:
                print(f"  {r['text']}")
        except Exception as e:
            print(f"  Lỗi khi xử lý {img_path}: {e}")

    return all_results


if __name__ == "__main__":
    all_results = run_ocr_on_folder("data/raw")
    print(f"\n✔ Hoàn tất OCR cho {len(all_results)} ảnh.")