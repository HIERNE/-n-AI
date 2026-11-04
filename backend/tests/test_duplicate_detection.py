import unittest

from src.structuring.duplicate_detection import find_duplicate_groups


class DuplicateDetectionTests(unittest.TestCase):
    def setUp(self):
        self.invoice = {
            "id": 1,
            "ma_so_thue_ban": "0312345678",
            "so_hoa_don": "00001234",
            "ngay_lap": "08/10/2026",
            "tong_thanh_toan": 1100,
        }

    def test_identifies_same_invoice_after_format_normalization(self):
        second_invoice = {
            **self.invoice,
            "id": 2,
            "ma_so_thue_ban": "031 234 5678",
            "so_hoa_don": "0000-1234",
            "ngay_lap": "2026-10-08",
            "tong_thanh_toan": 1100.5,
        }

        groups = find_duplicate_groups([self.invoice, second_invoice])

        self.assertEqual(len(groups), 1)
        self.assertTrue(groups[0]["exact_match"])
        self.assertEqual([invoice["id"] for invoice in groups[0]["invoices"]], [1, 2])

    def test_same_seller_and_number_with_different_date_or_total_is_suspected(self):
        second_invoice = {
            **self.invoice,
            "id": 2,
            "ngay_lap": "09/10/2026",
            "tong_thanh_toan": 1250,
        }

        groups = find_duplicate_groups([self.invoice, second_invoice])

        self.assertEqual(len(groups), 1)
        self.assertFalse(groups[0]["exact_match"])
        self.assertFalse(groups[0]["dates_match"])
        self.assertFalse(groups[0]["amounts_match"])

    def test_ignores_invoices_without_seller_tax_id_or_invoice_number(self):
        without_invoice_number = {**self.invoice, "id": 2, "so_hoa_don": None}
        without_seller_tax_id = {**self.invoice, "id": 3, "ma_so_thue_ban": ""}

        groups = find_duplicate_groups([
            self.invoice,
            without_invoice_number,
            without_seller_tax_id,
        ])

        self.assertEqual(groups, [])


if __name__ == "__main__":
    unittest.main()
