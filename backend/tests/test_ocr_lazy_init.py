import tempfile
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.ocr import ocr_pipeline


class OCRLazyInitializationTests(unittest.TestCase):
    def test_import_does_not_initialize_ocr_models(self):
        self.assertIsNone(ocr_pipeline._ocr_engine)

    def test_engine_uses_paddle_vietnamese_recognition_without_torch(self):
        paddle_engine = Mock()
        paddle_module = SimpleNamespace(PaddleOCR=Mock(return_value=paddle_engine))
        with patch.dict(sys.modules, {"paddleocr": paddle_module}):
            with patch.object(ocr_pipeline, "_ocr_engine", None):
                result = ocr_pipeline._get_ocr_engine()

        self.assertIs(result, paddle_engine)
        paddle_module.PaddleOCR.assert_called_once_with(
            use_angle_cls=False,
            lang="vi",
            show_log=False,
        )

    def test_run_ocr_uses_vietnamese_paddle_result_shape(self):
        box = [[10, 20], [80, 20], [80, 40], [10, 40]]
        engine = Mock()
        engine.ocr.return_value = [[[box, ("Hóa đơn", 0.99)]]]
        with (
            tempfile.NamedTemporaryFile(suffix=".jpg") as image,
            patch.object(ocr_pipeline, "_get_ocr_engine", return_value=engine),
        ):
            result = ocr_pipeline.run_ocr(image.name)

        self.assertEqual(
            result,
            [{"text": "Hóa đơn", "box": box, "y": 20, "x": 10}],
        )
        engine.ocr.assert_called_once_with(image.name, det=True, rec=True, cls=False)

if __name__ == "__main__":
    unittest.main()
