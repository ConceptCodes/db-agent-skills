#!/usr/bin/env python3
"""Emit a deterministic, read-only audit summary for a Chinook SQLite file."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_DATABASE = Path(__file__).resolve().parents[3] / "data" / "chinook.db"

EXPECTED_TABLES = (
    "Album",
    "Artist",
    "Customer",
    "Employee",
    "Genre",
    "Invoice",
    "InvoiceLine",
    "MediaType",
    "Playlist",
    "PlaylistTrack",
    "Track",
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


def count_rows(connection: sqlite3.Connection, table_name: str) -> int:
    sql = f"SELECT COUNT(*) FROM {quote_identifier(table_name)}"
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
            raise ValueError(f"not the expected Chinook schema; missing: {missing}")

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
                "views": connection.execute(
                    "SELECT COUNT(*) FROM sqlite_schema WHERE type = 'view'"
                ).fetchone()[0],
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
            "invoices": fetch_row(
                connection,
                """
                SELECT
                    COUNT(*) AS count,
                    COUNT(DISTINCT CustomerId) AS customers,
                    MIN(InvoiceDate) AS first_invoice_at,
                    MAX(InvoiceDate) AS last_invoice_at,
                    ROUND(SUM(Total), 2) AS total
                FROM Invoice
                """,
            ),
            "invoice_lines": fetch_row(
                connection,
                """
                SELECT
                    COUNT(*) AS count,
                    COUNT(DISTINCT InvoiceId) AS invoices,
                    COUNT(DISTINCT TrackId) AS tracks_sold,
                    MIN(Quantity) AS minimum_quantity,
                    MAX(Quantity) AS maximum_quantity,
                    MIN(UnitPrice) AS minimum_unit_price,
                    MAX(UnitPrice) AS maximum_unit_price,
                    ROUND(SUM(UnitPrice * Quantity), 2) AS revenue
                FROM InvoiceLine
                """,
            ),
            "invoice_reconciliation": fetch_row(
                connection,
                """
                WITH line_totals AS (
                    SELECT
                        InvoiceId,
                        ROUND(SUM(UnitPrice * Quantity), 2) AS line_total
                    FROM InvoiceLine
                    GROUP BY InvoiceId
                )
                SELECT
                    SUM(ABS(i.Total - lt.line_total) > 0.000001)
                        AS mismatched_invoices,
                    MAX(ABS(i.Total - lt.line_total)) AS maximum_difference
                FROM Invoice AS i
                JOIN line_totals AS lt ON lt.InvoiceId = i.InvoiceId
                """,
            ),
            "catalog": fetch_row(
                connection,
                """
                SELECT
                    COUNT(*) AS tracks,
                    SUM(AlbumId IS NULL) AS tracks_without_album,
                    SUM(GenreId IS NULL) AS tracks_without_genre,
                    SUM(Composer IS NULL OR trim(Composer) = '')
                        AS tracks_without_composer,
                    SUM(Bytes IS NULL) AS tracks_without_bytes,
                    SUM(Milliseconds <= 0) AS nonpositive_duration,
                    SUM(UnitPrice < 0) AS negative_price,
                    (
                        SELECT COUNT(*)
                        FROM Track AS unsold
                        LEFT JOIN InvoiceLine AS il
                            ON il.TrackId = unsold.TrackId
                        WHERE il.TrackId IS NULL
                    ) AS tracks_never_sold
                FROM Track
                """,
            ),
            "labels": fetch_row(
                connection,
                """
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM (
                            SELECT Name
                            FROM Track
                            GROUP BY Name
                            HAVING COUNT(*) > 1
                        )
                    ) AS duplicate_track_name_groups,
                    (
                        SELECT COUNT(*)
                        FROM Playlist
                    ) AS playlists,
                    (
                        SELECT COUNT(DISTINCT Name)
                        FROM Playlist
                    ) AS distinct_playlist_names
                """,
            ),
            "data_quality": fetch_row(
                connection,
                """
                SELECT
                    SUM(Company IS NULL OR trim(Company) = '')
                        AS customers_without_company,
                    SUM(State IS NULL OR trim(State) = '')
                        AS customers_without_state,
                    SUM(SupportRepId IS NULL) AS customers_without_support_rep
                FROM Customer
                """,
            ),
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"Chinook SQLite file (default: {DEFAULT_DATABASE})",
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
