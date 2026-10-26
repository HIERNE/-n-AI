"""Safely migrate local SQLite invoice data to an empty configured MySQL database."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from config import DATABASE_URL, DB_PATH
from src.storage.db_handler import (
    _ensure_auth_table,
    _ensure_jobs_table,
    _ensure_table,
)


TABLE_COLUMNS = {
    "users": (
        "id",
        "username",
        "password_hash",
        "full_name",
        "email",
        "role",
        "created_at",
    ),
    "invoices": (
        "id",
        "source_image",
        "source_hash",
        "ma_so_thue_ban",
        "ten_cong_ty_ban",
        "so_hoa_don",
        "ma_so_thue_mua",
        "ten_cong_ty_mua",
        "ngay_lap",
        "danh_sach_mat_hang",
        "tong_tien_hang",
        "thue_suat_vat",
        "tien_thue_vat",
        "tong_thanh_toan",
        "accounting_status",
        "payment_status",
        "user_id",
        "created_at",
    ),
    "processing_jobs": (
        "id",
        "file_name",
        "source_image",
        "source_hash",
        "status",
        "invoice_id",
        "user_id",
        "created_at",
        "updated_at",
    ),
}


def _source_count(source: sqlite3.Connection, table: str) -> int:
    if table not in {
        row[0]
        for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }:
        return 0
    return int(source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _destination_count(connection, table: str) -> int:
    if table not in inspect(connection).get_table_names():
        return 0
    return int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())


def _copy_table(source: sqlite3.Connection, destination, table: str) -> int:
    source_columns = {
        row[1] for row in source.execute(f"PRAGMA table_info({table})").fetchall()
    }
    destination_columns = {
        column["name"] for column in inspect(destination).get_columns(table)
    }
    columns = [
        name
        for name in TABLE_COLUMNS[table]
        if name in source_columns and name in destination_columns
    ]
    if not columns:
        return 0

    column_sql = ", ".join(columns)
    parameter_sql = ", ".join(f":{name}" for name in columns)
    rows = source.execute(
        f"SELECT {column_sql} FROM {table} ORDER BY id"
    ).fetchall()
    if not rows:
        return 0

    destination.execute(
        text(f"INSERT INTO {table} ({column_sql}) VALUES ({parameter_sql})"),
        [{name: row[name] for name in columns} for row in rows],
    )
    return len(rows)


def _merge_users(
    source: sqlite3.Connection,
    destination,
    configured_admin_username: str | None = None,
) -> dict[str, int]:
    source_tables = {
        row[0]
        for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if "users" not in source_tables:
        raise ValueError("SQLite source has no users table.")

    source_columns = {
        row[1] for row in source.execute("PRAGMA table_info(users)").fetchall()
    }
    required_columns = {"username", "password_hash", "role"}
    if not required_columns.issubset(source_columns):
        raise ValueError("SQLite users table is missing required account columns.")

    optional_columns = ("full_name", "email", "created_at")
    selected_columns = [
        "username",
        "password_hash",
        "role",
        *(column for column in optional_columns if column in source_columns),
    ]
    rows = source.execute(
        f"SELECT {', '.join(selected_columns)} FROM users ORDER BY id"
    ).fetchall()
    imported = 0
    skipped = 0
    seen_usernames: set[str] = set()

    for row in rows:
        username = row["username"]
        normalized_username = username.casefold()
        if normalized_username in seen_usernames:
            raise ValueError(
                "SQLite users contains duplicate usernames ignoring case; "
                "resolve them before importing."
            )
        seen_usernames.add(normalized_username)

        existing = destination.execute(
            text("SELECT id FROM users WHERE LOWER(username) = :username"),
            {"username": normalized_username},
        ).first()
        if existing:
            skipped += 1
            continue

        user_data = {
            column: row[column]
            for column in selected_columns
            if column != "role"
        }
        user_data["role"] = (
            "admin"
            if configured_admin_username
            and normalized_username == configured_admin_username.casefold()
            else "user"
        )
        columns_sql = ", ".join(user_data)
        values_sql = ", ".join(f":{column}" for column in user_data)
        destination.execute(
            text(f"INSERT INTO users ({columns_sql}) VALUES ({values_sql})"),
            user_data,
        )
        imported += 1

    return {"source_users": len(rows), "imported_users": imported, "skipped_users": skipped}


def migrate_users(
    source_path: Path,
    destination_url: str,
    configured_admin_username: str | None = None,
) -> dict[str, int]:
    source_path = source_path.expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite source database not found: {source_path}")

    destination_engine = create_engine(destination_url, pool_pre_ping=True)
    if destination_engine.dialect.name != "mysql":
        destination_engine.dispose()
        raise ValueError("Destination must be MySQL.")

    try:
        _ensure_auth_table(destination_engine, bootstrap_admin=False)
        source_uri = f"{source_path.as_uri()}?mode=ro"
        with closing(sqlite3.connect(source_uri, uri=True)) as source:
            source.row_factory = sqlite3.Row
            with destination_engine.begin() as destination:
                return _merge_users(
                    source,
                    destination,
                    configured_admin_username=configured_admin_username,
                )
    finally:
        destination_engine.dispose()


def migrate(source_path: Path, destination_url: str, apply: bool) -> dict[str, int]:
    source_path = source_path.expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite source database not found: {source_path}")

    destination_engine = create_engine(destination_url, pool_pre_ping=True)
    if destination_engine.dialect.name != "mysql":
        destination_engine.dispose()
        raise ValueError(
            "Destination must be MySQL; SQLite is not a persistent Cloud restore target."
        )

    try:
        source_uri = f"{source_path.as_uri()}?mode=ro"
        with closing(sqlite3.connect(source_uri, uri=True)) as source:
            source.row_factory = sqlite3.Row
            if "invoices" not in {
                row[0]
                for row in source.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }:
                raise ValueError("SQLite source has no invoices table.")

            source_counts = {
                table: _source_count(source, table)
                for table in TABLE_COLUMNS
            }

            with destination_engine.connect() as connection:
                destination_counts = {
                    table: _destination_count(connection, table)
                    for table in TABLE_COLUMNS
                }

            if any(destination_counts.values()):
                raise RuntimeError(
                    "MySQL destination is not empty "
                    f"(users={destination_counts['users']}, "
                    f"invoices={destination_counts['invoices']}, "
                    f"processing_jobs={destination_counts['processing_jobs']}); "
                    "aborting to prevent overwriting or duplicating records."
                )

            if not apply:
                return {
                    "source_invoices": source_counts["invoices"],
                    "source_jobs": source_counts["processing_jobs"],
                    "source_users": source_counts["users"],
                    "migrated_invoices": 0,
                    "migrated_jobs": 0,
                    "migrated_users": 0,
                }

            _ensure_table(destination_engine, bootstrap_admin=False)
            _ensure_jobs_table(destination_engine, bootstrap_admin=False)
            with destination_engine.begin() as destination:
                current_counts = {
                    table: _destination_count(destination, table)
                    for table in TABLE_COLUMNS
                }
                if any(current_counts.values()):
                    raise RuntimeError(
                        "Destination received data during preflight; aborting to prevent conflicts."
                    )
                migrated_counts = {
                    table: _copy_table(source, destination, table)
                    for table in TABLE_COLUMNS
                }

            if migrated_counts != source_counts:
                raise RuntimeError(
                    "Migrated row counts do not match source: "
                    f"source={source_counts}, migrated={migrated_counts}."
                )

            return {
                "source_invoices": source_counts["invoices"],
                "source_jobs": source_counts["processing_jobs"],
                "source_users": source_counts["users"],
                "migrated_invoices": migrated_counts["invoices"],
                "migrated_jobs": migrated_counts["processing_jobs"],
                "migrated_users": migrated_counts["users"],
            }
    finally:
        destination_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Preview or migrate invoice records and processing history from local "
            "SQLite to the MySQL database configured by DATABASE_URL."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DB_PATH,
        help="Path to the source SQLite file (default: data/outputs/invoices.db).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration; default is a read-only preview.",
    )
    parser.add_argument(
        "--users-only",
        action="store_true",
        help="Merge missing SQLite accounts into MySQL without importing invoices or jobs.",
    )
    args = parser.parse_args()

    if args.users_only:
        from config import ADMIN_USERNAME

        result = migrate_users(
            args.source,
            DATABASE_URL,
            configured_admin_username=ADMIN_USERNAME,
        )
        print(
            f"Users-only import: {result['imported_users']} imported, "
            f"{result['skipped_users']} already existed, "
            f"{result['source_users']} source accounts."
        )
        return

    result = migrate(args.source, DATABASE_URL, apply=args.apply)
    mode = "Migrated" if args.apply else "Preview"
    print(
        f"{mode}: {result['source_users']} users, "
        f"{result['source_invoices']} invoices, "
        f"{result['source_jobs']} processing jobs."
    )
    if not args.apply:
        print("No data was written. Use --apply after verifying the destination database.")
    else:
        print(
            f"Imported {result['migrated_users']} users, "
            f"{result['migrated_invoices']} invoices and "
            f"{result['migrated_jobs']} processing jobs. The SQLite source was not changed."
        )


if __name__ == "__main__":
    main()
