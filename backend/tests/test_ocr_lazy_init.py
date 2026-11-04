import unittest

from src.ocr import ocr_pipeline


class OCRLazyInitializationTests(unittest.TestCase):
    def test_import_does_not_initialize_ocr_models(self):
        self.assertIsNone(ocr_pipeline._detector_engine)
        self.assertIsNone(ocr_pipeline._recognizer)


if __name__ == "__main__":
    unittest.main()
