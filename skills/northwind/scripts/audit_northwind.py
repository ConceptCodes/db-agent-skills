#!/usr/bin/env python3
"""Emit a deterministic, read-only audit summary for a Northwind SQLite file."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_DATABASE = Path(__file__).resolve().parents[3] / "data" / "northwind.db"

EXPECTED_TABLES = (
    "Categories",
    "CustomerCustomerDemo",
    "CustomerDemographics",
    "Customers",
    "EmployeeTerritories",
    "Employees",
    "Order Details",
    "Orders",
    "Products",
    "Regions",
    "Shippers",
    "Suppliers",
    "Territories",
)

LEGACY_1997_VIEWS = (
    "Category Sales for 1997",
    "Product Sales for 1997",
    "Quarterly Orders",
    "Sales Totals by Amount",
    "Sales by Category",
)


def quote_identifier(identifier: str) -> str:
    """Quote a trusted schema identifier using SQLite's identifier rules."""
    return '"' + identifier.replace('"', '""') + '"'


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as database_file:
        for chunk in iter(lambda: database_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_row(connection: sqlite3.Connection, sql: str) -> dict[str, Any]:
    row = connection.execute(sql).fetchone()
    if row is None:
        return {}
    return dict(row)


def count_rows(connection: sqlite3.Connection, object_name: str) -> int:
    sql = f"SELECT COUNT(*) FROM {quote_identifier(object_name)}"
    return int(connection.execute(sql).fetchone()[0])


def audit(database_path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")

    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        missing_tables = sorted(set(EXPECTED_TABLES) - tables)
        if missing_tables:
            missing = ", ".join(missing_tables)
            raise ValueError(f"not the expected Northwind schema; missing: {missing}")

        views = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'view'"
            )
        }
        foreign_key_violations = [
            list(row) for row in connection.execute("PRAGMA foreign_key_check")
        ]

        return {
            "database": str(database_path),
            "size_bytes": database_path.stat().st_size,
            "sha256": sha256_file(database_path),
            "integrity_check": [
                row[0] for row in connection.execute("PRAGMA integrity_check")
            ],
            "foreign_keys_enabled": bool(
                connection.execute("PRAGMA foreign_keys").fetchone()[0]
            ),
            "foreign_key_violations": foreign_key_violations,
            "objects": {
                "tables": len(tables),
                "views": len(views),
                "triggers": connection.execute(
                    "SELECT COUNT(*) FROM sqlite_schema WHERE type = 'trigger'"
                ).fetchone()[0],
                "explicit_indexes": connection.execute(
                    "SELECT COUNT(*) FROM sqlite_schema "
                    "WHERE type = 'index' AND sql IS NOT NULL"
                ).fetchone()[0],
            },
            "table_rows": {
                table: count_rows(connection, table) for table in EXPECTED_TABLES
            },
            "orders": fetch_row(
                connection,
                """
                SELECT
                    COUNT(*) AS count,
                    MIN(OrderID) AS first_id,
                    MAX(OrderID) AS last_id,
                    MIN(OrderDate) AS first_order_at,
                    MAX(OrderDate) AS last_order_at,
                    MIN(ShippedDate) AS first_shipped_at,
                    MAX(ShippedDate) AS last_shipped_at,
                    SUM(ShippedDate IS NULL) AS unshipped,
                    SUM(
                        datetime(ShippedDate) > datetime(RequiredDate)
                    ) AS shipped_late
                FROM Orders
                """,
            ),
            "order_details": fetch_row(
                connection,
                """
                SELECT
                    COUNT(*) AS count,
                    COUNT(DISTINCT OrderID) AS orders,
                    COUNT(DISTINCT ProductID) AS products,
                    MIN(Quantity) AS minimum_quantity,
                    MAX(Quantity) AS maximum_quantity,
                    ROUND(AVG(Quantity), 2) AS average_quantity,
                    ROUND(
                        SUM(UnitPrice * Quantity * (1 - Discount)),
                        2
                    ) AS net_sales
                FROM "Order Details"
                """,
            ),
            "data_quality": fetch_row(
                connection,
                """
                SELECT
                    SUM(Address IS NULL OR trim(Address) = '')
                        AS customers_without_address,
                    SUM(City IS NULL OR trim(City) = '')
                        AS customers_without_city,
                    SUM(Country IS NULL OR trim(Country) = '')
                        AS customers_without_country
                FROM Customers
                """,
            ),
            "invoice_salesperson": fetch_row(
                connection,
                """
                SELECT
                    COUNT(DISTINCT Salesperson) AS distinct_values,
                    MIN(Salesperson) AS minimum_value,
                    MAX(Salesperson) AS maximum_value,
                    typeof(Salesperson) AS storage_type
                FROM Invoices
                """,
            ),
            "legacy_1997_view_rows": {
                view: count_rows(connection, view)
                for view in LEGACY_1997_VIEWS
                if view in views
            },
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"Northwind SQLite file (default: {DEFAULT_DATABASE})",
    )
    args = parser.parse_args()
    database_path = args.database.expanduser().resolve()

    if not database_path.is_file():
        parser.error(f"database file does not exist: {database_path}")

    try:
        result = audit(database_path)
    except (sqlite3.DatabaseError, ValueError) as error:
        parser.error(str(error))

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
