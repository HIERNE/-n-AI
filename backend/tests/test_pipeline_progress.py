import unittest
from unittest.mock import patch

from src import pipeline


class InvoicePipelineProgressTests(unittest.TestCase):
    def test_extract_invoice_reports_ocr_then_extraction_stages(self):
        stage_updates = []
        invoice = object()

        with (
            patch.object(
                pipeline,
                "run_ocr",
                side_effect=[[{"text": "invoice page one"}], [{"text": "invoice page two"}]],
            ) as run_ocr,
            patch.object(pipeline, "extract_invoice_data", return_value=invoice),
        ):
            result = pipeline.extract_invoice(
                ["page-one.jpg", "page-two.jpg"],
                stage_callback=lambda step, message: stage_updates.append((step, message)),
            )

        self.assertIs(result, invoice)
        self.assertEqual(run_ocr.call_count, 2)
        self.assertEqual([step for step, _ in stage_updates], [2, 3])
        self.assertIn("OCR", stage_updates[0][1])
        self.assertIn("trích xuất", stage_updates[1][1])


if __name__ == "__main__":
    unittest.main()
