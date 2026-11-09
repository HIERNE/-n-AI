import os
import sys
from threading import Lock
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import glob

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


def run_ocr(image_path: str):
    if not Path(image_path).is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh: {image_path}")

    ocr_engine = _get_ocr_engine()
    result = ocr_engine.ocr(image_path, det=True, rec=True, cls=False)
    lines = result[0] if result and result[0] else []

    extracted = []
    for box, (text, _) in lines:
        x_min = int(min(point[0] for point in box))
        y_min = int(min(point[1] for point in box))
        extracted.append({"text": text, "box": box, "y": y_min, "x": x_min})

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