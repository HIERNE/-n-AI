import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine

os.environ.setdefault("APP_AUTH_SECRET", "react-auth-test-secret-0123456789abcdef")

from fastapi.testclient import TestClient

from api import main as auth_api
from src.storage import db_handler


class ReactAuthenticationApiTests(unittest.TestCase):
    def setUp(self):
        self.user = {
            "id": 0,
            "username": "person@gmail.com",
            "full_name": "Invoice User",
            "email": "person@gmail.com",
            "role": "user",
        }
        self.database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.database_file.close()
        self.engine = create_engine(
            f"sqlite:///{self.database_file.name}",
            connect_args={"check_same_thread": False},
        )
        self.engine_patcher = patch.object(
            db_handler, "_make_engine", return_value=self.engine
        )
        self.admin_username_patcher = patch.object(db_handler, "ADMIN_USERNAME", None)
        self.admin_password_patcher = patch.object(db_handler, "ADMIN_PASSWORD", None)
        self.activity_patcher = patch.object(auth_api, "log_activity")
        self.engine_patcher.start()
        self.admin_username_patcher.start()
        self.admin_password_patcher.start()
        self.activity_patcher.start()
        self.client = TestClient(auth_api.app)
        self.client.__enter__()
        created_user = db_handler.register_user(
            self.user["username"],
            "test-password",
            full_name=self.user["full_name"],
            email=self.user["email"],
        )
        self.user["id"] = created_user["id"]

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.engine_patcher.stop()
        self.admin_username_patcher.stop()
        self.admin_password_patcher.stop()
        self.activity_patcher.stop()
        self.engine.dispose()
        Path(self.database_file.name).unlink(missing_ok=True)

    def test_login_sets_http_only_cookie_and_me_returns_current_database_user(self):
        login_response = self.client.post(
            "/api/auth/login",
            json={
                "username": "person@gmail.com",
                "password": "test-password",
                "remember_me": False,
            },
        )
        current_response = self.client.get("/api/auth/me")

        self.assertEqual(login_response.status_code, 200)
        self.assertIn("httponly", login_response.headers["set-cookie"].lower())
        self.assertEqual(current_response.json()["user"]["id"], self.user["id"])
        self.assertNotIn("password_hash", current_response.json()["user"])

    def test_login_rejects_username_with_different_letter_case(self):
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": "PERSON@GMAIL.COM",
                "password": "test-password",
            },
        )

        self.assertEqual(response.status_code, 401)

    def test_login_rejects_an_untrusted_browser_origin(self):
        response = self.client.post(
            "/api/auth/login",
            headers={"origin": "https://attacker.example"},
            json={"username": "person@gmail.com", "password": "test-password"},
        )

        self.assertEqual(response.status_code, 403)

    def test_local_development_origin_can_use_vite_fallback_port(self):
        response = self.client.post(
            "/api/auth/login",
            headers={"origin": "http://127.0.0.1:5174"},
            json={"username": "person@gmail.com", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 401)

    def test_password_change_rejects_an_untrusted_browser_origin(self):
        response = self.client.post(
            "/api/auth/change-password",
            headers={"origin": "https://attacker.example"},
            json={
                "current_password": "test-password",
                "new_password": "another-password",
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_dashboard_uses_database_counts_instead_of_loading_invoice_rows(self):
        self.client.post(
            "/api/auth/login",
            json={"username": "person@gmail.com", "password": "test-password"},
        )
        with (
            patch.object(auth_api, "get_invoice_count", side_effect=[12, 4]) as count,
            patch.object(auth_api, "get_job_counts", return_value={"processing": 2}),
            patch.object(auth_api, "get_recent_jobs", return_value=[]),
            patch.object(auth_api, "get_all_invoices", side_effect=AssertionError),
        ):
            response = self.client.get("/api/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["invoice_count"], 12)
        self.assertEqual(response.json()["confirmed_count"], 4)
        self.assertEqual(count.call_count, 2)

    def test_history_includes_live_processing_progress(self):
        self.client.post(
            "/api/auth/login",
            json={"username": "person@gmail.com", "password": "test-password"},
        )
        with (
            patch.object(
                auth_api,
                "get_full_history",
                return_value=[{"job_id": 456, "status": "processing"}],
            ),
            patch.dict(
                auth_api._JOB_PROGRESS,
                {
                    456: {
                        "progress_step": 2,
                        "progress_status": "processing",
                        "progress_message": "Đang nhận dạng OCR.",
                        "progress_error": None,
                    }
                },
            ),
        ):
            response = self.client.get("/api/history")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["history"][0]["progress_step"], 2)
        self.assertEqual(
            response.json()["history"][0]["progress_message"],
            "Đang nhận dạng OCR.",
        )

    def test_reports_are_only_available_to_admins(self):
        self.client.post(
            "/api/auth/login",
            json={"username": "person@gmail.com", "password": "test-password"},
        )

        response = self.client.get("/api/reports")

        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_reports_for_all_users(self):
        admin = {**self.user, "id": 1, "role": "admin"}
        with (
            patch.object(auth_api, "_current_user", return_value=admin),
            patch.object(auth_api, "get_all_invoices", return_value=[]) as invoices,
            patch.object(auth_api, "get_recent_jobs", return_value=[]) as jobs,
        ):
            response = self.client.get("/api/reports")

        self.assertEqual(response.status_code, 200)
        invoices.assert_called_once_with(user_id=admin["id"], is_admin=True)
        jobs.assert_called_once_with(limit=100, user_id=admin["id"], is_admin=True)

    def test_accounting_export_returns_an_excel_workbook(self):
        self.client.post(
            "/api/auth/login",
            json={"username": "person@gmail.com", "password": "test-password"},
        )
        with (
            patch.object(auth_api, "_require_admin"),
            patch.object(
                auth_api,
                "get_confirmed_invoices",
                return_value=[{
                    "id": 7,
                    "ngay_lap": "2026-11-04",
                    "ten_cong_ty_ban": "Công ty thử nghiệm",
                    "tong_thanh_toan": 12345,
                    "payment_status": "paid",
                }],
            ),
        ):
            response = self.client.get("/api/accounting/export")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            response.headers["content-type"],
        )
        self.assertIn("invoices-accounting.xlsx", response.headers["content-disposition"])

        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(response.content), read_only=True)
        worksheet = workbook["Hạch toán"]
        self.assertEqual(worksheet["A1"].value, "ID")
        self.assertEqual(worksheet["A2"].value, 7)
        self.assertEqual(worksheet["C2"].value, "Công ty thử nghiệm")
        workbook.close()

    def test_api_serves_built_react_entrypoint(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Invoice Pro", response.text)

    def test_registration_and_logout_are_backed_by_existing_user_table(self):
        registration_response = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Second User",
                "email": "second@gmail.com",
                "password": "test-password",
            },
        )
        login_response = self.client.post(
            "/api/auth/login",
            json={
                "username": "second@gmail.com",
                "password": "test-password",
                "remember_me": True,
            },
        )
        logout_response = self.client.post("/api/auth/logout")

        self.assertEqual(registration_response.status_code, 201)
        self.assertEqual(login_response.status_code, 200)
        self.assertIn("max-age=2592000", login_response.headers["set-cookie"].lower())
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_tampered_session_token_is_rejected(self):
        token = auth_api._encode_token(self.user["id"], 60)
        payload, signature = token.split(".", 1)
        changed_signature = ("A" if signature[0] != "A" else "B") + signature[1:]

        self.assertIsNone(auth_api._decode_token(f"{payload}.{changed_signature}"))
        self.assertEqual(auth_api._decode_token(token), self.user["id"])


if __name__ == "__main__":
    unittest.main()
