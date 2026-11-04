import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text

from scripts.migrate_sqlite_to_mysql import _copy_table, _merge_users, migrate


class SQLiteToMySQLMigrationTests(unittest.TestCase):
    def test_merge_users_adds_missing_accounts_without_overwriting_admin(self):
        source = sqlite3.connect(":memory:")
        source.row_factory = sqlite3.Row
        source.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                password_hash TEXT,
                full_name TEXT,
                email TEXT,
                role TEXT,
                created_at TEXT
            )
        """)
        source.executemany(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (1, "admin", "source-admin-hash", None, None, "admin", "2026-01-01"),
                (2, "person@gmail.com", "user-hash", "Person", "person@gmail.com", "user", "2026-01-02"),
                (3, "other-admin", "other-hash", "Other", None, "admin", "2026-01-03"),
            ],
        )
        target_engine = create_engine("sqlite://")
        try:
            with target_engine.begin() as target:
                target.execute(text("""
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        full_name TEXT,
                        email TEXT,
                        role TEXT NOT NULL,
                        created_at TEXT
                    )
                """))
                target.execute(text("""
                    INSERT INTO users (username, password_hash, role)
                    VALUES ('admin', 'configured-admin-hash', 'admin')
                """))
                result = _merge_users(
                    source, target, configured_admin_username="admin"
                )
                rows = target.execute(text("""
                    SELECT username, password_hash, role
                    FROM users ORDER BY id
                """)).all()

            self.assertEqual(result, {
                "source_users": 3,
                "imported_users": 2,
                "skipped_users": 1,
            })
            self.assertEqual(rows[0], ("admin", "configured-admin-hash", "admin"))
            self.assertEqual(rows[1], ("person@gmail.com", "user-hash", "user"))
            self.assertEqual(rows[2], ("other-admin", "other-hash", "user"))
        finally:
            target_engine.dispose()
            source.close()

    def test_copy_table_preserves_users_and_invoice_ownership(self):
        source = sqlite3.connect(":memory:")
        source.row_factory = sqlite3.Row
        source.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                password_hash TEXT,
                full_name TEXT,
                email TEXT,
                role TEXT,
                created_at TEXT
            )
        """)
        source.execute("""
            INSERT INTO users VALUES
                (3, 'person@gmail.com', 'pbkdf2_hash', 'Person', 'person@gmail.com', 'user', '2026-10-01')
        """)
        source.execute("""
            CREATE TABLE invoices (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                accounting_status TEXT
            )
        """)
        source.execute("INSERT INTO invoices VALUES (17, 3, 'confirmed')")

        try:
            with tempfile.TemporaryDirectory() as directory:
                target_engine = create_engine(
                    f"sqlite:///{Path(directory) / 'target.db'}"
                )
                try:
                    with target_engine.begin() as target:
                        target.execute(text("""
                            CREATE TABLE users (
                                id INTEGER PRIMARY KEY,
                                username TEXT,
                                password_hash TEXT,
                                full_name TEXT,
                                email TEXT,
                                role TEXT,
                                created_at TEXT
                            )
                        """))
                        target.execute(text("""
                            CREATE TABLE invoices (
                                id INTEGER PRIMARY KEY,
                                user_id INTEGER,
                                accounting_status TEXT
                            )
                        """))
                        copied_users = _copy_table(source, target, "users")
                        copied_invoices = _copy_table(source, target, "invoices")
                        owner = target.execute(
                            text("SELECT username FROM users WHERE id = 3")
                        ).scalar_one()
                        invoice = target.execute(
                            text("SELECT user_id, accounting_status FROM invoices WHERE id = 17")
                        ).one()

                    self.assertEqual(copied_users, 1)
                    self.assertEqual(copied_invoices, 1)
                    self.assertEqual(owner, "person@gmail.com")
                    self.assertEqual(invoice, (3, "confirmed"))
                finally:
                    target_engine.dispose()
        finally:
            source.close()

    def test_copy_table_preserves_invoice_data_and_ids(self):
        source = sqlite3.connect(":memory:")
        source.row_factory = sqlite3.Row
        source.execute("""
            CREATE TABLE invoices (
                id INTEGER PRIMARY KEY,
                source_image TEXT,
                ma_so_thue_ban TEXT,
                danh_sach_mat_hang TEXT,
                accounting_status TEXT,
                payment_status TEXT
            )
        """)
        source.execute(
            """
            INSERT INTO invoices VALUES
                (17, 'invoice.jpg', '0312345678', '[{"ten_hang":"A"}]', 'confirmed', 'paid')
            """
        )

        try:
            with tempfile.TemporaryDirectory() as directory:
                target_path = Path(directory) / "target.db"
                target_engine = create_engine(f"sqlite:///{target_path}")
                try:
                    with target_engine.begin() as target:
                        target.execute(text("""
                            CREATE TABLE invoices (
                                id INTEGER PRIMARY KEY,
                                source_image TEXT,
                                ma_so_thue_ban TEXT,
                                danh_sach_mat_hang TEXT,
                                accounting_status TEXT,
                                payment_status TEXT
                            )
                        """))
                        copied = _copy_table(source, target, "invoices")
                        row = target.execute(
                            text("SELECT * FROM invoices WHERE id = 17")
                        ).mappings().one()

                    self.assertEqual(copied, 1)
                    self.assertEqual(row["accounting_status"], "confirmed")
                    self.assertEqual(row["payment_status"], "paid")
                    self.assertEqual(row["danh_sach_mat_hang"], '[{"ten_hang":"A"}]')
                finally:
                    target_engine.dispose()
        finally:
            source.close()

    def test_migration_rejects_sqlite_destination_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.db"
            target_path = Path(directory) / "target.db"
            source_engine = create_engine(f"sqlite:///{source_path}")
            with source_engine.begin() as connection:
                connection.execute(text(
                    "CREATE TABLE invoices (id INTEGER PRIMARY KEY, accounting_status TEXT)"
                ))
                connection.execute(text(
                    "INSERT INTO invoices VALUES (1, 'pending')"
                ))
            source_engine.dispose()

            with self.assertRaisesRegex(ValueError, "Destination must be MySQL"):
                migrate(
                    source_path,
                    f"sqlite:///{target_path}",
                    apply=True,
                )

            verification_engine = create_engine(f"sqlite:///{source_path}")
            try:
                with verification_engine.connect() as connection:
                    self.assertEqual(
                        connection.execute(text("SELECT COUNT(*) FROM invoices")).scalar_one(),
                        1,
                    )
            finally:
                verification_engine.dispose()
            self.assertFalse(target_path.exists())


if __name__ == "__main__":
    unittest.main()
