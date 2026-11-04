import os
import sys
from threading import Lock
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import glob

_detector_engine = None
_recognizer = None
_ENGINE_LOCK = Lock()


def _get_ocr_engines():
    global _detector_engine, _recognizer
    if _detector_engine is None or _recognizer is None:
        with _ENGINE_LOCK:
            if _detector_engine is None or _recognizer is None:
                from paddleocr import PaddleOCR
                from vietocr.tool.config import Cfg
                from vietocr.tool.predictor import Predictor

                detector = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
                config = Cfg.load_config_from_file(
                    str(ROOT_DIR / "vietocr_config.yml")
                )
                config["device"] = "cpu"
                recognizer = Predictor(config)
                _detector_engine = detector
                _recognizer = recognizer
    return _detector_engine, _recognizer


def crop_box(image, box):
    import numpy as np

    box = np.array(box, dtype=np.float32)
    x_min, x_max = int(np.min(box[:, 0])), int(np.max(box[:, 0]))
    y_min, y_max = int(np.min(box[:, 1])), int(np.max(box[:, 1]))
    return image[y_min:y_max, x_min:x_max], y_min, x_min


def run_ocr(image_path: str):
    import cv2
    from PIL import Image

    detector_engine, recognizer = _get_ocr_engines()
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Không đọc được ảnh: {image_path}")

    det_result = detector_engine.ocr(image_path, det=True, rec=False, cls=False)
    boxes = det_result[0]

    extracted = []
    for box in boxes:
        cropped, y_min, x_min = crop_box(image, box)
        if cropped.size == 0:
            continue
        cropped_pil = Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))
        text = recognizer.predict(cropped_pil)
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