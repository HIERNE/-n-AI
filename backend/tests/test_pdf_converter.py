import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.preprocessing import pdf_converter


class PdfConverterTests(unittest.TestCase):
    def test_pdf_pages_render_at_reduced_dpi(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "invoice.pdf"
            output_dir = Path(temp_dir) / "pages"
            pdf_path.write_bytes(b"test")

            pixmap = Mock()
            page = Mock()
            page.get_pixmap.return_value = pixmap
            document = Mock()
            document.needs_pass = False
            document.page_count = 1
            document.__enter__ = Mock(return_value=document)
            document.__exit__ = Mock(return_value=False)
            document.__iter__ = Mock(return_value=iter([page]))

            with (
                patch.object(pdf_converter.fitz, "open", return_value=document),
                patch.object(pdf_converter.fitz, "Matrix") as matrix,
            ):
                paths = pdf_converter.pdf_to_images(pdf_path, output_dir)

            matrix.assert_called_once_with(150 / 72, 150 / 72)
            page.get_pixmap.assert_called_once_with(
                matrix=matrix.return_value,
                alpha=False,
            )
            pixmap.save.assert_called_once_with(
                str(output_dir / "invoice_page1.jpg"),
                jpg_quality=90,
            )
            self.assertEqual(paths, [str(output_dir / "invoice_page1.jpg")])


if __name__ == "__main__":
    unittest.main()
