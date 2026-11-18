import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.database.db import get_migration_connection, initialize_database

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "backend" / "database" / "expenses.db"
TABLE_COLUMNS = {
    "expenses": (
        "id",
        "title",
        "amount",
        "category",
        "expense_date",
        "notes",
        "created_at",
    ),
    "recurring_income": (
        "id",
        "person",
        "source",
        "amount",
        "frequency",
        "income_date",
        "created_at",
    ),
    "recurring_bills": (
        "id",
        "title",
        "amount",
        "category",
        "due_day",
        "created_at",
    ),
    "bill_payments": (
        "id",
        "bill_id",
        "period",
        "amount",
        "expense_id",
        "paid_on",
    ),
}


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value is not None else None


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _load_sqlite_rows(sqlite_path: Path) -> dict[str, list[dict[str, Any]]]:
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")

    connection = sqlite3.connect(
        f"{sqlite_path.resolve().as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        existing_tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        missing_tables = set(TABLE_COLUMNS) - existing_tables
        if missing_tables:
            raise ValueError(
                "SQLite database is missing required tables: "
                + ", ".join(sorted(missing_tables))
            )

        result = {}
        for table, columns in TABLE_COLUMNS.items():
            selected_columns = ", ".join(f'"{column}"' for column in columns)
            rows = connection.execute(
                f'SELECT {selected_columns} FROM "{table}" ORDER BY id'
            ).fetchall()
            result[table] = [dict(row) for row in rows]
        return result
    finally:
        connection.close()


def _postgres_values(table: str, row: dict[str, Any]) -> tuple[Any, ...]:
    values = dict(row)
    values["amount"] = Decimal(str(values["amount"]))

    if table == "expenses":
        values["expense_date"] = _date(values["expense_date"])
    elif table == "recurring_income":
        values["income_date"] = _date(values["income_date"])
    elif table == "bill_payments":
        values["paid_on"] = _date(values["paid_on"])

    values["created_at"] = (
        _timestamp(values["created_at"]) if "created_at" in values else None
    )
    return tuple(values[column] for column in TABLE_COLUMNS[table])


def _source_digest(rows: dict[str, list[dict[str, Any]]]) -> str:
    serialized = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _target_row_matches(
    table: str,
    source_row: dict[str, Any],
    target_row: dict[str, Any],
) -> bool:
    expected_values = _postgres_values(table, source_row)
    return all(
        expected == target_row[column]
        for column, expected in zip(TABLE_COLUMNS[table], expected_values)
    )


def neon_postgres(sqlite_path: Path) -> dict[str, Any]:
    """Import a SQLite snapshot into an empty PostgreSQL schema, repeat-safely."""
    source_rows = _load_sqlite_rows(sqlite_path)
    counts = {table: len(rows) for table, rows in source_rows.items()}
    digest = _source_digest(source_rows)

    initialize_database()

    with get_migration_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS expense_tracker_sqlite_migrations (
                source_digest TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                table_counts JSONB NOT NULL,
                imported_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        prior_import = connection.execute(
            """
            SELECT table_counts
            FROM expense_tracker_sqlite_migrations
            WHERE source_digest = %s
            """,
            (digest,),
        ).fetchone()

        if prior_import is not None:
            for table, rows in source_rows.items():
                for source_row in rows:
                    target_row = connection.execute(
                        f'SELECT * FROM "{table}" WHERE id = %s',
                        (source_row["id"],),
                    ).fetchone()
                    if target_row is None or not _target_row_matches(
                        table, source_row, target_row
                    ):
                        raise ValueError(
                            "The source was previously imported, but its target "
                            f"record no longer matches ({table}, id={source_row['id']})."
                        )

            return {
                "status": "already_imported",
                "source": sqlite_path.name,
                "counts": counts,
            }

        existing_counts = {
            table: connection.execute(
                f'SELECT COUNT(*) AS count FROM "{table}"'
            ).fetchone()["count"]
            for table in TABLE_COLUMNS
        }
        if any(existing_counts.values()):
            raise ValueError(
                "The PostgreSQL application tables are not empty and this SQLite "
                "snapshot has no matching migration record. Refusing to import "
                "into an existing database."
            )

        for table, columns in TABLE_COLUMNS.items():
            if not source_rows[table]:
                continue
            column_list = ", ".join(f'"{column}"' for column in columns)
            placeholders = ", ".join("%s" for _ in columns)
            statement = (
                f'INSERT INTO "{table}" ({column_list}) '
                f"VALUES ({placeholders})"
            )
            with connection.cursor() as cursor:
                cursor.executemany(
                    statement,
                    (_postgres_values(table, row) for row in source_rows[table]),
                )

        verified_counts = {
            table: connection.execute(
                f'SELECT COUNT(*) AS count FROM "{table}"'
            ).fetchone()["count"]
            for table in TABLE_COLUMNS
        }
        if verified_counts != counts:
            raise ValueError(
                f"Post-import counts did not match the SQLite source: "
                f"expected {counts}, received {verified_counts}."
            )

        for table in TABLE_COLUMNS:
            connection.execute(
                f"""
                SELECT setval(
                    pg_get_serial_sequence(%s, 'id'),
                    COALESCE(MAX(id), 1),
                    MAX(id) IS NOT NULL
                )
                FROM "{table}"
                """,
                (table,),
            )

        connection.execute(
            """
            INSERT INTO expense_tracker_sqlite_migrations
                (source_digest, source_name, table_counts)
            VALUES (%s, %s, %s)
            """,
            (digest, sqlite_path.name, json.dumps(counts)),
        )

    return {
        "status": "imported",
        "source": sqlite_path.name,
        "counts": counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read a SQLite backup and import it into Neon PostgreSQL."
    )
    parser.add_argument(
        "sqlite_path",
        nargs="?",
        type=Path,
        default=DEFAULT_SQLITE_PATH,
        help=f"SQLite database path (default: {DEFAULT_SQLITE_PATH})",
    )
    args = parser.parse_args()

    try:
        report = neon_postgres(args.sqlite_path)
    except Exception as error:
        print(
            f"Migration failed ({type(error).__name__}): {error}",
            file=sys.stderr,
        )
        print("The source SQLite database was opened read-only.", file=sys.stderr)
        return 1

    print(f"Migration {report['status']}: {report['source']}")
    for table, count in report["counts"].items():
        print(f"  {table}: {count} records verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
