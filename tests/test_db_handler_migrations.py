import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text

from src.storage import db_handler
from src.structuring.schemas import Invoice


class InvoiceDatabaseMigrationTests(unittest.TestCase):
    def setUp(self):
        self.activity_logger_patcher = patch("src.logging_config.log_activity")
        self.activity_logger_patcher.start()
        self.database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.database_file.close()
        self.engine = create_engine(f"sqlite:///{self.database_file.name}")

        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ma_so_thue_ban TEXT,
                    ten_cong_ty_ban TEXT,
                    ma_so_thue_mua TEXT,
                    ten_cong_ty_mua TEXT,
                    ngay_lap TEXT,
                    danh_sach_mat_hang TEXT,
                    tong_tien_hang REAL,
                    thue_suat_vat TEXT,
                    tien_thue_vat REAL,
                    tong_thanh_toan REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    accounting_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    payment_status VARCHAR(20) NOT NULL DEFAULT 'unpaid',
                    so_hoa_don VARCHAR(100),
                    source_hash VARCHAR(64)
                )
            """))
            conn.execute(text("""
                INSERT INTO invoices (
                    ma_so_thue_ban, ten_cong_ty_ban, so_hoa_don,
                    ngay_lap, tong_thanh_toan, accounting_status, created_at
                ) VALUES (
                    '0312345678', 'Công ty cũ', 'HD-001',
                    '2026-10-08', 1100, 'confirmed', '2020-01-01 00:00:00'
                )
            """))

    def tearDown(self):
        self.engine.dispose()
        Path(self.database_file.name).unlink(missing_ok=True)
        self.activity_logger_patcher.stop()

    def test_startup_initialization_creates_auth_and_application_tables(self):
        with patch.object(db_handler, "_make_engine", return_value=self.engine), patch.object(
            db_handler, "ADMIN_USERNAME", "startup-admin"
        ), patch.object(db_handler, "ADMIN_PASSWORD", "a-very-strong-password"):
            db_handler.initialize_database()

            tables = set(inspect(self.engine).get_table_names())
            admin = db_handler.authenticate_user(
                "startup-admin", "a-very-strong-password"
            )

        self.assertTrue({"users", "invoices", "processing_jobs"}.issubset(tables))
        self.assertEqual(admin["role"], "admin")

    def test_old_schema_is_migrated_for_invoice_queries_and_uploads(self):
        with patch.object(db_handler, "_make_engine", return_value=self.engine), patch.object(
            db_handler, "ADMIN_USERNAME", "legacy-admin"
        ), patch.object(db_handler, "ADMIN_PASSWORD", "a-very-strong-password"):
            admin = db_handler.authenticate_user("legacy-admin", "a-very-strong-password")
            confirmed = db_handler.get_confirmed_invoices(user_id=admin["id"])

            self.assertEqual(len(confirmed), 1)
            self.assertEqual(confirmed[0]["ten_cong_ty_ban"], "Công ty cũ")
            self.assertIsNone(confirmed[0]["uploader_username"])
            self.assertIsNone(confirmed[0]["source_image"])

            invoice = Invoice(
                ma_so_thue_ban="0312345678",
                ten_cong_ty_ban="Công ty mới",
                ngay_lap="2026-10-09",
                tong_tien_hang=1000,
                thue_suat_vat="10%",
                tien_thue_vat=100,
                tong_thanh_toan=1100,
            )
            invoice_id = db_handler.save_invoice_to_db(
                invoice,
                source_image="D:/uploads/invoice.jpg",
                source_hash="a" * 64,
            )
            counts = db_handler.get_job_counts(user_id=admin["id"])
            db_handler.set_invoice_source_image(
                1, "data/raw/legacy_invoice.jpg", user_id=admin["id"]
            )
            invoices = db_handler.get_all_invoices(user_id=admin["id"])
            history = db_handler.get_full_history(user_id=admin["id"])

        uploaded = next(item for item in invoices if item["id"] == invoice_id)
        legacy_invoice = next(item for item in invoices if item["id"] == 1)
        self.assertEqual(uploaded["source_image"], "D:/uploads/invoice.jpg")
        self.assertEqual(uploaded["source_hash"], "a" * 64)
        self.assertEqual(uploaded["uploader_username"], "legacy-admin")
        self.assertIsNone(legacy_invoice["uploader_username"])
        self.assertEqual(counts["success"], 2)
        self.assertEqual(legacy_invoice["source_image"], "data/raw/legacy_invoice.jpg")
        self.assertEqual(len(history), 2)
        legacy_history = next(
            item for item in history if item["file_name"] == "Hóa đơn cũ #1"
        )
        self.assertEqual(legacy_history["file_name"], "Hóa đơn cũ #1")
        self.assertEqual(legacy_history["status"], "success")

    def test_invoice_visibility_and_status_changes_are_role_scoped(self):
        with patch.object(db_handler, "_make_engine", return_value=self.engine):
            alice = db_handler.register_user("alice", "a-strong-password")
            bob = db_handler.register_user("bob", "another-strong-password")
            authenticated_alice = db_handler.authenticate_user(
                "alice", "a-strong-password"
            )
            invoice = Invoice(
                ma_so_thue_ban="0312345678",
                ten_cong_ty_ban="Hóa đơn riêng",
                ngay_lap="2026-10-10",
                tong_tien_hang=1000,
                thue_suat_vat="10%",
                tien_thue_vat=100,
                tong_thanh_toan=1100,
            )
            invoice_id = db_handler.save_invoice_to_db(
                invoice, "alice.jpg", user_id=alice["id"]
            )
            alice_job_id = db_handler.create_job(
                "shared.pdf", source_hash="shared-hash", user_id=alice["id"]
            )
            bob_job_id = db_handler.create_job(
                "shared.pdf", source_hash="shared-hash", user_id=bob["id"]
            )
            db_handler.mark_job_success(
                alice_job_id, invoice_id, user_id=alice["id"]
            )

            alice_invoices = db_handler.get_all_invoices(user_id=alice["id"])
            bob_invoices = db_handler.get_all_invoices(user_id=bob["id"])
            all_invoices = db_handler.get_all_invoices(is_admin=True)
            alice_jobs = db_handler.get_jobs_by_ids(
                [alice_job_id, bob_job_id], user_id=alice["id"]
            )
            alice_duplicates = db_handler.get_upload_duplicate_candidates(
                "shared-hash", "shared.pdf", user_id=alice["id"]
            )
            bob_duplicates = db_handler.get_upload_duplicate_candidates(
                "shared-hash", "shared.pdf", user_id=bob["id"]
            )

            with self.assertRaises(PermissionError):
                db_handler.set_invoice_accounting_status(invoice_id, "confirmed")
            db_handler.update_invoice_data(
                invoice_id,
                {"ten_cong_ty_ban": "Đã chỉnh sửa"},
                user_id=alice["id"],
            )
            db_handler.set_invoice_accounting_status(
                invoice_id, "confirmed", is_admin=True
            )
            with self.assertRaisesRegex(ValueError, "không có quyền truy cập"):
                db_handler.update_invoice_data(
                    invoice_id,
                    {"ten_cong_ty_ban": "Không được sửa sau khi duyệt"},
                    user_id=alice["id"],
                )

        self.assertEqual([row["id"] for row in alice_invoices], [invoice_id])
        self.assertEqual(alice_invoices[0]["uploader_username"], "alice")
        self.assertEqual(bob_invoices, [])
        self.assertEqual(len(all_invoices), 2)
        admin_invoice = next(row for row in all_invoices if row["id"] == invoice_id)
        self.assertEqual(admin_invoice["uploader_username"], "alice")
        self.assertEqual([job["id"] for job in alice_jobs], [alice_job_id])
        self.assertEqual([job["job_id"] for job in alice_duplicates], [alice_job_id])
        self.assertEqual(bob_duplicates, [])
        self.assertEqual(authenticated_alice["role"], "user")
        self.assertIsNone(db_handler.authenticate_user("alice", "wrong-password"))

    def test_user_can_delete_owned_history_and_unreferenced_invoice(self):
        with patch.object(db_handler, "_make_engine", return_value=self.engine):
            user = db_handler.register_user("delete-user", "a-strong-password")
            invoice_id = db_handler.save_invoice_to_db(
                Invoice(
                    ma_so_thue_ban="0312345678",
                    ten_cong_ty_ban="Công ty cần xóa",
                    ngay_lap="2026-10-10",
                    tong_tien_hang=1000,
                    thue_suat_vat="10%",
                    tien_thue_vat=100,
                    tong_thanh_toan=1100,
                ),
                "delete.jpg",
                user_id=user["id"],
            )
            job_id = db_handler.create_job("delete.jpg", user_id=user["id"])
            db_handler.mark_job_success(job_id, invoice_id, user_id=user["id"])

            deleted = db_handler.delete_selected_history_jobs(
                [job_id], user_id=user["id"]
            )
            with self.engine.connect() as connection:
                remaining_job = connection.execute(
                    text("SELECT id FROM processing_jobs WHERE id = :id"),
                    {"id": job_id},
                ).first()
                remaining_invoice = connection.execute(
                    text("SELECT id FROM invoices WHERE id = :id"),
                    {"id": invoice_id},
                ).first()

        self.assertEqual(deleted, {"job_count": 1, "invoice_count": 1})
        self.assertIsNone(remaining_job)
        self.assertIsNone(remaining_invoice)

    def test_user_cannot_delete_another_users_history(self):
        with patch.object(db_handler, "_make_engine", return_value=self.engine):
            alice = db_handler.register_user("alice-delete", "a-strong-password")
            bob = db_handler.register_user("bob-delete", "another-strong-password")
            bob_job_id = db_handler.create_job("bob.pdf", user_id=bob["id"])

            with self.assertRaises(PermissionError):
                db_handler.delete_selected_history_jobs(
                    [bob_job_id], user_id=alice["id"]
                )

            with self.engine.connect() as connection:
                remaining_job = connection.execute(
                    text("SELECT id FROM processing_jobs WHERE id = :id"),
                    {"id": bob_job_id},
                ).scalar_one()

        self.assertEqual(remaining_job, bob_job_id)

    def test_delete_keeps_invoice_used_by_another_history_job(self):
        with patch.object(db_handler, "_make_engine", return_value=self.engine):
            user = db_handler.register_user("shared-delete", "a-strong-password")
            invoice_id = db_handler.save_invoice_to_db(
                Invoice(
                    ma_so_thue_ban="0312345678",
                    ten_cong_ty_ban="Công ty dùng chung",
                    ngay_lap="2026-10-10",
                    tong_tien_hang=1000,
                    thue_suat_vat="10%",
                    tien_thue_vat=100,
                    tong_thanh_toan=1100,
                ),
                "shared.jpg",
                user_id=user["id"],
            )
            first_job_id = db_handler.create_job("shared-1.jpg", user_id=user["id"])
            second_job_id = db_handler.create_job("shared-2.jpg", user_id=user["id"])
            db_handler.mark_job_success(first_job_id, invoice_id, user_id=user["id"])
            db_handler.mark_job_success(second_job_id, invoice_id, user_id=user["id"])

            deleted = db_handler.delete_selected_history_jobs(
                [first_job_id], user_id=user["id"]
            )
            with self.engine.connect() as connection:
                remaining_invoice = connection.execute(
                    text("SELECT id FROM invoices WHERE id = :id"),
                    {"id": invoice_id},
                ).scalar_one()

        self.assertEqual(deleted, {"job_count": 1, "invoice_count": 0})
        self.assertEqual(remaining_invoice, invoice_id)

    def test_deleting_duplicate_history_does_not_delete_original_invoice(self):
        with patch.object(db_handler, "_make_engine", return_value=self.engine):
            user = db_handler.register_user("duplicate-delete", "a-strong-password")
            invoice_id = db_handler.save_invoice_to_db(
                Invoice(
                    ma_so_thue_ban="0312345678",
                    ten_cong_ty_ban="Hóa đơn gốc",
                    ngay_lap="2026-10-10",
                    tong_tien_hang=1000,
                    thue_suat_vat="10%",
                    tien_thue_vat=100,
                    tong_thanh_toan=1100,
                ),
                "original.jpg",
                user_id=user["id"],
            )
            original_job_id = db_handler.create_job(
                "original.jpg", user_id=user["id"]
            )
            duplicate_job_id = db_handler.create_job(
                "duplicate.jpg", user_id=user["id"]
            )
            db_handler.mark_job_success(
                original_job_id, invoice_id, user_id=user["id"]
            )
            db_handler.mark_job_duplicate(
                duplicate_job_id, invoice_id, user_id=user["id"]
            )

            deleted = db_handler.delete_selected_history_jobs(
                [duplicate_job_id], user_id=user["id"]
            )
            with self.engine.connect() as connection:
                remaining_invoice = connection.execute(
                    text("SELECT id FROM invoices WHERE id = :id"),
                    {"id": invoice_id},
                ).scalar_one()
                remaining_original_job = connection.execute(
                    text("SELECT id FROM processing_jobs WHERE id = :id"),
                    {"id": original_job_id},
                ).scalar_one()

        self.assertEqual(deleted, {"job_count": 1, "invoice_count": 0})
        self.assertEqual(remaining_invoice, invoice_id)
        self.assertEqual(remaining_original_job, original_job_id)

    def test_registration_accepts_six_character_password_only(self):
        with patch.object(db_handler, "_make_engine", return_value=self.engine):
            with self.assertRaisesRegex(ValueError, "ít nhất 6 ký tự"):
                db_handler.register_user("shortpass", "12345")

            user = db_handler.register_user("sixcharpass", "123456")
            authenticated_user = db_handler.authenticate_user(
                "sixcharpass", "123456"
            )

        self.assertEqual(user, authenticated_user)
        self.assertEqual(user["role"], "user")

    def test_registration_stores_name_and_email_and_email_login_is_case_insensitive(self):
        with patch.object(db_handler, "_make_engine", return_value=self.engine):
            user = db_handler.register_user(
                "person@gmail.com",
                "123456",
                full_name="Nguyễn Văn A",
                email="Person@Gmail.com",
            )
            authenticated_user = db_handler.authenticate_user(
                "PERSON@GMAIL.COM", "123456"
            )

        self.assertEqual(user["username"], "person@gmail.com")
        self.assertEqual(user["email"], "person@gmail.com")
        self.assertEqual(user["full_name"], "Nguyễn Văn A")
        self.assertEqual(authenticated_user, user)

    def test_registration_rejects_non_gmail_email(self):
        with patch.object(db_handler, "_make_engine", return_value=self.engine):
            with self.assertRaisesRegex(ValueError, "email Gmail hợp lệ"):
                db_handler.register_user(
                    "person@example.com",
                    "123456",
                    full_name="Nguyễn Văn A",
                    email="person@example.com",
                )

    def test_new_processing_jobs_do_not_store_error_details_in_database(self):
        with patch.object(db_handler, "_make_engine", return_value=self.engine), patch(
            "src.logging_config.get_app_logger"
        ) as logger:
            job_id = db_handler.create_job("broken.pdf")
            db_handler.mark_job_failed(job_id, "private technical traceback")

            columns = {
                column["name"]
                for column in inspect(self.engine).get_columns("processing_jobs")
            }
            with self.engine.connect() as connection:
                status = connection.execute(
                    text("SELECT status FROM processing_jobs WHERE id = :id"),
                    {"id": job_id},
                ).scalar_one()

        logger.return_value.error.assert_called_once()
        self.assertNotIn("error_message", columns)
        self.assertNotIn("error_reason", columns)
        self.assertEqual(status, "failed")

    def test_legacy_job_error_details_are_cleared_during_schema_migration(self):
        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE processing_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_name TEXT,
                    source_image TEXT,
                    source_hash TEXT,
                    status TEXT,
                    error_message TEXT,
                    error_reason TEXT,
                    invoice_id INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )
            """))
            connection.execute(text("""
                INSERT INTO processing_jobs (
                    file_name, status, error_message, error_reason
                ) VALUES (
                    'failed.pdf', 'failed', 'private traceback', 'private reason'
                )
            """))

        with patch.object(db_handler, "_make_engine", return_value=self.engine), patch.object(
            db_handler, "ADMIN_USERNAME", "legacy-admin"
        ), patch.object(
            db_handler, "ADMIN_PASSWORD", "a-very-strong-password"
        ):
            jobs = db_handler.get_all_jobs(is_admin=True)
            with self.engine.connect() as connection:
                legacy_details = connection.execute(text("""
                    SELECT error_message, error_reason, user_id
                    FROM processing_jobs WHERE id = 1
                """)).one()

        self.assertNotIn("error_message", jobs[0])
        self.assertEqual(legacy_details, (None, None, 1))

    def test_database_engine_errors_are_not_hidden_by_sqlite_fallback(self):
        with patch.object(
            db_handler,
            "create_engine",
            side_effect=RuntimeError("Configured database is unavailable"),
        ) as create_engine:
            with self.assertRaisesRegex(RuntimeError, "Configured database is unavailable"):
                db_handler._make_engine()

        create_engine.assert_called_once()
        self.assertEqual(create_engine.call_args.kwargs, {"pool_pre_ping": True})


if __name__ == "__main__":
    unittest.main()
